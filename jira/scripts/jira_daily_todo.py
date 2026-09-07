#!/usr/bin/env python3
"""Cache-first Jira/BigPicture daily task snapshotter.

The script is intentionally read-only toward Jira. It writes a local JSON snapshot
under this skill's assets/cache directory and can update a local daily plan without
performing another Jira request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = SKILL_ROOT / "assets" / "cache"
BOX_RE = re.compile(r"/box/([A-Za-z0-9_-]+)(?:/|$)", re.IGNORECASE)
VALID_BOX_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def now_local() -> datetime:
    return datetime.now().astimezone()


def unique(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in items:
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def find_env_file(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"env file does not exist: {path}")
        return path

    checked: set[Path] = set()
    for start in (Path.cwd().resolve(), SKILL_ROOT.resolve()):
        for parent in (start, *start.parents):
            candidate = parent / ".env"
            if candidate in checked:
                continue
            checked.add(candidate)
            if candidate.is_file():
                return candidate
    return None


def origin_and_box(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return None, None
    match = BOX_RE.search(url)
    box = match.group(1) if match else None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, box

    # Keep an optional Jira context path, but discard plugin/page routes.
    path = parsed.path.rstrip("/")
    for marker in ("/plugins/", "/rest/", "/browse/", "/secure/"):
        if marker in path:
            path = path.split(marker, 1)[0]
            break
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/"), box


def api_error_summary(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip().replace("\n", " ")[:500]
    messages: list[str] = []
    for item in payload.get("errorMessages", []) if isinstance(payload, dict) else []:
        messages.append(str(item))
    errors = payload.get("errors", {}) if isinstance(payload, dict) else {}
    if isinstance(errors, dict):
        messages.extend(f"{key}: {value}" for key, value in errors.items())
    return "; ".join(messages)[:500] or "Jira returned an error response"


class JiraClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "jira-daily-todo-skill/1",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Jira HTTP {exc.code} for {method} {path}: {api_error_summary(raw)}"
            ) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Jira connection failed for {method} {path}: {exc.reason}") from None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload)


def find_field_id(
    fields: list[dict[str, Any]],
    preferred_id: str,
    names: Iterable[str],
    custom_hint: str | None = None,
) -> str | None:
    by_id = {str(field.get("id")): field for field in fields}
    if preferred_id in by_id:
        return preferred_id

    wanted = {name.casefold() for name in names}
    for field in fields:
        if str(field.get("name", "")).casefold() in wanted:
            return str(field.get("id"))

    if custom_hint:
        hint = custom_hint.casefold()
        for field in fields:
            schema = field.get("schema") or {}
            if hint in str(schema.get("custom", "")).casefold():
                return str(field.get("id"))
    return None


def parse_sprint(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "state": str(raw.get("state", "")).upper() or None,
            "start_date": raw.get("startDate"),
            "end_date": raw.get("endDate"),
            "complete_date": raw.get("completeDate"),
        }

    text = str(raw)
    parsed: dict[str, Any] = {}
    keys = {
        "id": "id",
        "name": "name",
        "state": "state",
        "startDate": "start_date",
        "endDate": "end_date",
        "completeDate": "complete_date",
    }
    for source, target in keys.items():
        match = re.search(rf"(?:\[|,){re.escape(source)}=([^,\]]*)", text)
        if match:
            value: Any = match.group(1).strip()
            if value in {"", "<null>", "null"}:
                value = None
            elif source == "id":
                try:
                    value = int(value)
                except ValueError:
                    pass
            elif source == "state" and value:
                value = str(value).upper()
            parsed[target] = value
    return parsed


def sprint_identity(sprint: dict[str, Any]) -> str:
    return str(sprint.get("id") or sprint.get("name") or "")


def account_name(user: Any) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("name") or user.get("key") or user.get("accountId")


def display_name(user: Any) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("displayName") or account_name(user)


def is_system_account(name: str | None, shown_name: str | None = None) -> bool:
    system_names = {"jira", "jira automation", "automation", "project automation"}
    values = {str(value).strip().casefold() for value in (name, shown_name) if value}
    return bool(values & system_names)


def status_info(status: Any) -> dict[str, Any]:
    if not isinstance(status, dict):
        return {"name": None, "category": None, "category_name": None, "done": False}
    category = status.get("statusCategory") or {}
    category_key = category.get("key")
    return {
        "name": status.get("name"),
        "category": category_key,
        "category_name": category.get("name"),
        "done": category_key == "done",
    }


def parse_comments(comment_field: Any) -> list[dict[str, Any]]:
    if not isinstance(comment_field, dict):
        return []
    comments = comment_field.get("comments") or []
    result: list[dict[str, Any]] = []
    for comment in comments[-10:]:
        result.append(
            {
                "id": comment.get("id"),
                "author": account_name(comment.get("author")),
                "author_display": display_name(comment.get("author")),
                "created": comment.get("created"),
                "updated": comment.get("updated"),
                "body": comment.get("body"),
            }
        )
    return result


def parse_linked_issue(issue: Any) -> dict[str, Any] | None:
    if not isinstance(issue, dict):
        return None
    fields = issue.get("fields") or {}
    status = status_info(fields.get("status"))
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": status["name"],
        "done": status["done"],
    }


def parse_links(raw_links: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_links, list):
        return []
    result: list[dict[str, Any]] = []
    for link in raw_links:
        link_type = link.get("type") or {}
        if link.get("outwardIssue"):
            issue = parse_linked_issue(link.get("outwardIssue"))
            direction = link_type.get("outward")
        else:
            issue = parse_linked_issue(link.get("inwardIssue"))
            direction = link_type.get("inward")
        if issue:
            result.append({"relation": direction, **issue})
    return result


def parse_subtasks(raw_subtasks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_subtasks, list):
        return []
    return [item for item in (parse_linked_issue(raw) for raw in raw_subtasks) if item]


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    if seconds == 0:
        return "0m"
    remaining = max(0, int(seconds))
    units = (("w", 5 * 8 * 3600), ("d", 8 * 3600), ("h", 3600), ("m", 60))
    parts: list[str] = []
    for suffix, size in units:
        value, remaining = divmod(remaining, size)
        if value:
            parts.append(f"{value}{suffix}")
    return " ".join(parts) or "<1m"


def issue_to_record(
    issue: dict[str, Any],
    custom: dict[str, str | None],
    current_user: str | None,
    current_sprint_id: str | None,
    display_order: int,
) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    status = status_info(fields.get("status"))
    timetracking = fields.get("timetracking") or {}
    remaining_seconds = timetracking.get("remainingEstimateSeconds", fields.get("timeestimate"))
    original_seconds = timetracking.get("originalEstimateSeconds", fields.get("timeoriginalestimate"))
    spent_seconds = timetracking.get("timeSpentSeconds", fields.get("timespent"))

    sprint_values = fields.get(custom["sprint"]) if custom.get("sprint") else []
    if sprint_values is None:
        sprint_values = []
    if not isinstance(sprint_values, list):
        sprint_values = [sprint_values]
    sprints = [parsed for parsed in (parse_sprint(raw) for raw in sprint_values) if parsed]
    deduped: list[dict[str, Any]] = []
    seen_sprints: set[str] = set()
    for sprint in sprints:
        identity = sprint_identity(sprint)
        if identity and identity not in seen_sprints:
            seen_sprints.add(identity)
            deduped.append(sprint)
    sprints = deduped

    if current_sprint_id:
        carryover_count = sum(1 for sprint in sprints if sprint_identity(sprint) != current_sprint_id)
    else:
        carryover_count = max(0, len(sprints) - 1)

    comments = parse_comments(fields.get("comment"))
    reporter = account_name(fields.get("reporter"))
    links = parse_links(fields.get("issuelinks"))
    subtasks = parse_subtasks(fields.get("subtasks"))
    external_commenters = unique(
        comment["author_display"] or comment["author"] or ""
        for comment in comments
        if comment.get("author")
        and comment.get("author") != current_user
        and not is_system_account(comment.get("author"), comment.get("author_display"))
    )

    collaboration_evidence = {
        "reporter_is_other": bool(reporter and current_user and reporter != current_user),
        "reporter": display_name(fields.get("reporter")),
        "external_commenters": external_commenters,
        "open_linked_issues": [link for link in links if not link.get("done")],
        "open_subtasks": [subtask for subtask in subtasks if not subtask.get("done")],
    }

    priority = fields.get("priority") or {}
    issue_type = fields.get("issuetype") or {}
    parent = parse_linked_issue(fields.get("parent"))
    return {
        "display_order": display_order,
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "issue_type": issue_type.get("name"),
        "status": status,
        "priority": priority.get("name"),
        "assignee": display_name(fields.get("assignee")),
        "reporter": display_name(fields.get("reporter")),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "start_date": fields.get(custom["start"]) if custom.get("start") else None,
        "end_date": fields.get(custom["end"]) if custom.get("end") else None,
        "due_date": fields.get("duedate"),
        "original_estimate_seconds": original_seconds,
        "remaining_estimate_seconds": remaining_seconds,
        "time_spent_seconds": spent_seconds,
        "original_estimate": format_duration(original_seconds),
        "remaining_estimate": format_duration(remaining_seconds),
        "time_spent": format_duration(spent_seconds),
        "rank": fields.get(custom["rank"]) if custom.get("rank") else None,
        "sprints": sprints,
        "carryover_count": carryover_count,
        "description": fields.get("description"),
        "labels": fields.get("labels") or [],
        "components": [item.get("name") for item in fields.get("components") or []],
        "fix_versions": [item.get("name") for item in fields.get("fixVersions") or []],
        "comments": comments,
        "parent": parent,
        "subtasks": subtasks,
        "issue_links": links,
        "collaboration_evidence": collaboration_evidence,
    }


def fetch_all_issues(
    client: JiraClient, jql: str, fields: list[str], page_size: int = 100
) -> list[dict[str, Any]]:
    start_at = 0
    issues: list[dict[str, Any]] = []
    while True:
        response = client.post(
            "/rest/api/2/search",
            {
                "jql": jql,
                "startAt": start_at,
                "maxResults": page_size,
                "fields": fields,
            },
        )
        page = response.get("issues") or []
        issues.extend(page)
        total = int(response.get("total", len(issues)))
        if not page or len(issues) >= total:
            return issues
        start_at += len(page)


def choose_current_sprint(raw_issues: list[dict[str, Any]], sprint_field: str | None) -> dict[str, Any] | None:
    if not sprint_field:
        return None
    candidates: dict[str, dict[str, Any]] = {}
    for issue in raw_issues:
        values = (issue.get("fields") or {}).get(sprint_field) or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            sprint = parse_sprint(value)
            identity = sprint_identity(sprint)
            if identity:
                candidates[identity] = sprint
    active = [sprint for sprint in candidates.values() if sprint.get("state") == "ACTIVE"]
    pool = active or list(candidates.values())
    if not pool:
        return None
    return sorted(pool, key=lambda item: str(item.get("id") or ""))[-1]


def build_snapshot(client: JiraClient, base_url: str, box_id: str) -> dict[str, Any]:
    myself = client.get("/rest/api/2/myself")
    all_fields = client.get("/rest/api/2/field")
    if not isinstance(all_fields, list):
        raise RuntimeError("Jira field discovery returned an unexpected response")

    custom = {
        "sprint": find_field_id(
            all_fields, "customfield_10105", ("Sprint",), "gh-sprint"
        ),
        "rank": find_field_id(
            all_fields, "customfield_10106", ("Rank",), "gh-lexo-rank"
        ),
        "start": find_field_id(
            all_fields, "customfield_10309", ("Start date", "Start Date")
        ),
        "end": find_field_id(
            all_fields, "customfield_10302", ("End date", "End Date")
        ),
    }
    order = f"cf[{custom['rank'].split('_')[-1]}] ASC" if custom.get("rank") else "updated DESC"
    jql = f'issue in box("{box_id}") AND assignee = currentUser() ORDER BY {order}'
    standard_fields = [
        "summary",
        "issuetype",
        "status",
        "priority",
        "assignee",
        "reporter",
        "created",
        "updated",
        "duedate",
        "timeoriginalestimate",
        "timeestimate",
        "timespent",
        "timetracking",
        "description",
        "labels",
        "components",
        "fixVersions",
        "comment",
        "parent",
        "subtasks",
        "issuelinks",
    ]
    search_fields = unique(standard_fields + [value for value in custom.values() if value])
    raw_issues = fetch_all_issues(client, jql, search_fields)
    current_sprint = choose_current_sprint(raw_issues, custom.get("sprint"))
    current_sprint_id = sprint_identity(current_sprint or {}) or None
    current_user = account_name(myself)
    issues = [
        issue_to_record(issue, custom, current_user, current_sprint_id, index)
        for index, issue in enumerate(raw_issues, start=1)
    ]

    pending = [issue for issue in issues if not issue["status"]["done"]]
    completed = [issue for issue in issues if issue["status"]["done"]]
    known_remaining = [
        int(issue["remaining_estimate_seconds"])
        for issue in pending
        if issue.get("remaining_estimate_seconds") is not None
    ]
    missing_dates = [
        issue["key"]
        for issue in pending
        if not (issue.get("start_date") or issue.get("end_date") or issue.get("due_date"))
    ]
    missing_descriptions = [issue["key"] for issue in pending if not issue.get("description")]

    fetched_at = now_local()
    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "cache_date": fetched_at.date().isoformat(),
        "jira": {"base_url": base_url, "box_id": box_id, "jql": jql},
        "user": {
            "name": current_user,
            "display_name": display_name(myself),
            "time_zone": myself.get("timeZone"),
        },
        "field_ids": custom,
        "current_sprint": current_sprint,
        "summary": {
            "total": len(issues),
            "completed": len(completed),
            "pending": len(pending),
            "remaining_seconds": sum(known_remaining),
            "remaining": format_duration(sum(known_remaining)),
            "missing_remaining_count": len(pending) - len(known_remaining),
            "missing_date_keys": missing_dates,
            "missing_description_keys": missing_descriptions,
        },
        "issues": issues,
        "daily_plan": None,
    }


def cache_scope(base_url: str, box_id: str, token: str) -> str:
    digest = hashlib.sha256(f"{base_url}\0{box_id}\0{token}".encode("utf-8")).hexdigest()
    return digest[:12]


def cache_path(cache_dir: Path, base_url: str, box_id: str, token: str) -> Path:
    safe_box = re.sub(r"[^A-Za-z0-9_-]", "_", box_id)
    return cache_dir / f"{now_local().date().isoformat()}__{safe_box}__{cache_scope(base_url, box_id, token)}.json"


def read_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    if data.get("cache_date") != now_local().date().isoformat():
        return None
    return data


def write_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def preserve_plan(snapshot: dict[str, Any], old_plan: Any) -> None:
    if not isinstance(old_plan, dict):
        return
    valid_keys = {issue.get("key") for issue in snapshot.get("issues", [])}
    focus = [key for key in old_plan.get("focus", []) if key in valid_keys]
    assist = [key for key in old_plan.get("assist", []) if key in valid_keys and key not in focus]
    if focus or assist or old_plan.get("note"):
        snapshot["daily_plan"] = {**old_plan, "focus": focus, "assist": assist}


def update_plan(
    snapshot: dict[str, Any],
    focus_arg: list[str] | None,
    assist_arg: list[str] | None,
    note_arg: str | None,
    clear: bool,
) -> bool:
    if clear:
        snapshot["daily_plan"] = None
        return True
    if focus_arg is None and assist_arg is None and note_arg is None:
        return False

    old = snapshot.get("daily_plan") or {}
    focus = unique(key.upper() for key in (focus_arg if focus_arg is not None else old.get("focus", [])))
    assist = unique(key.upper() for key in (assist_arg if assist_arg is not None else old.get("assist", [])))
    valid_keys = {str(issue.get("key", "")).upper() for issue in snapshot.get("issues", [])}
    unknown = [key for key in focus + assist if key not in valid_keys]
    if unknown:
        raise RuntimeError(f"plan contains issue keys outside this snapshot: {', '.join(unique(unknown))}")
    assist = [key for key in assist if key not in focus]
    snapshot["daily_plan"] = {
        "focus": focus,
        "assist": assist,
        "note": note_arg if note_arg is not None else old.get("note"),
        "updated_at": now_local().isoformat(timespec="seconds"),
    }
    return True


def print_summary(snapshot: dict[str, Any], source: str, path: Path) -> None:
    summary = snapshot.get("summary") or {}
    sprint = snapshot.get("current_sprint") or {}
    user = snapshot.get("user") or {}
    print(f"source={source}")
    print(f"cache={path.resolve()}")
    print(f"fetched_at={snapshot.get('fetched_at')}")
    print(f"user={user.get('display_name') or user.get('name')}")
    print(f"box={snapshot.get('jira', {}).get('box_id')}")
    print(f"sprint={sprint.get('name') or '-'} ({sprint.get('state') or '-'})")
    print(
        "tasks="
        f"{summary.get('total', 0)} total, {summary.get('completed', 0)} done, "
        f"{summary.get('pending', 0)} pending, {summary.get('remaining', '?')} remaining"
    )
    pending_issues = [
        issue for issue in snapshot.get("issues", []) if not issue.get("status", {}).get("done")
    ]
    for index, issue in enumerate(pending_issues, start=1):
        print(
            f"{index}. {issue.get('key')} | {issue.get('status', {}).get('name')} "
            f"| {issue.get('remaining_estimate')} | {issue.get('summary')}"
        )
    plan = snapshot.get("daily_plan")
    if plan:
        print(f"plan_focus={','.join(plan.get('focus') or []) or '-'}")
        print(f"plan_assist={','.join(plan.get('assist') or []) or '-'}")
        if plan.get("note"):
            print(f"plan_note={plan['note']}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="BigPicture URL; used to extract the Box ID")
    parser.add_argument("--base-url", help="Explicit Jira base URL (highest priority)")
    parser.add_argument("--box", help="BigPicture Box ID, for example ITER-33")
    parser.add_argument("--env-file", help="Explicit .env path")
    parser.add_argument("--cache-dir", help="Override local cache directory")
    parser.add_argument("--refresh", action="store_true", help="Replace today's cached snapshot")
    parser.add_argument("--offline", action="store_true", help="Never access Jira; require today's cache")
    parser.add_argument("--focus", nargs="+", metavar="KEY", help="Record today's primary issue keys")
    parser.add_argument("--assist", nargs="+", metavar="KEY", help="Record issue keys to inspect/assist")
    parser.add_argument("--note", help="Optional daily plan note")
    parser.add_argument("--clear-plan", action="store_true", help="Clear the local daily plan")
    parser.add_argument("--json", action="store_true", help="Print the complete snapshot as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        env_path = find_env_file(args.env_file)
        file_env = parse_dotenv(env_path) if env_path else {}
        token = os.environ.get("JIRA_TOKEN") or file_env.get("JIRA_TOKEN")
        env_base = os.environ.get("JIRA_BASE_URL") or file_env.get("JIRA_BASE_URL")
        env_box = os.environ.get("JIRA_BOX_ID") or file_env.get("JIRA_BOX_ID")
        url_base, url_box = origin_and_box(args.url)
        base_url = (args.base_url or env_base or url_base or "").rstrip("/")
        box_id = args.box or url_box or env_box

        if not token:
            raise RuntimeError("JIRA_TOKEN is missing; configure it in the project .env")
        if not base_url:
            raise RuntimeError("JIRA_BASE_URL is missing and no Jira URL was provided")
        parsed_base = urllib.parse.urlsplit(base_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise RuntimeError("JIRA_BASE_URL must be an absolute http(s) URL")
        if not box_id:
            raise RuntimeError("JIRA_BOX_ID is missing and no /box/<ID>/ URL was provided")
        if not VALID_BOX_RE.fullmatch(box_id):
            raise RuntimeError(f"invalid BigPicture Box ID: {box_id!r}")
        if args.refresh and args.offline:
            raise RuntimeError("--refresh and --offline cannot be used together")

        cache_dir = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else DEFAULT_CACHE_DIR
        path = cache_path(cache_dir, base_url, box_id, token)
        previous = read_cache(path)
        snapshot = None if args.refresh else previous
        source = "cache"
        if snapshot is None:
            if args.offline:
                raise RuntimeError(f"today's cache does not exist or is invalid: {path}")
            client = JiraClient(base_url, token)
            snapshot = build_snapshot(client, base_url, box_id)
            preserve_plan(snapshot, (previous or {}).get("daily_plan"))
            write_cache(path, snapshot)
            source = "network"

        if update_plan(snapshot, args.focus, args.assist, args.note, args.clear_plan):
            write_cache(path, snapshot)

        if args.json:
            print(
                json.dumps(
                    {"source": source, "cache_path": str(path.resolve()), "data": snapshot},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print_summary(snapshot, source, path)
        return 0
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
