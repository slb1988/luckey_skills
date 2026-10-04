---
name: add-github-submodule
title: Add GitHub Submodule
description: Adds a GitHub repository as a git submodule to the luckey_skills repo root, then commits the result. Use this skill whenever the user provides a GitHub URL and asks to add it as a submodule, clone it into the repo, or reference it as a sub-repo. Triggers on phrases like "添加子仓库", "添加 github 子仓库引用", "add submodule", "git clone into repo", "add this GitHub repo", or any GitHub URL accompanied by an intent to track it in this repo.
tags: [git, submodule, github, workflow]
---

# Add GitHub Submodule

> Layer: Tier 2 (Workflow Skill)

## Purpose

Adds a GitHub repo as a tracked git submodule at the root of `luckey_skills`, keeps `.gitmodules` and `submodules.md` in sync, and commits atomically.

---

## When to Use

- User pastes a GitHub URL and says to add / clone / reference it
- Phrases: "添加子仓库", "添加 github 子仓库引用", "add submodule", "add this repo"

---

## Workflow

### Step 1 — Derive local name

Extract the repo name from the URL: last path segment, strip `.git` suffix if present.

```
https://github.com/EA-Studio-SHARK/ai-morning-brief  →  ai-morning-brief
https://github.com/foo/bar.git                        →  bar
```

### Step 2 — Check for conflicts

```bash
ls <repo-name>
```

If the directory already exists as a stale leftover, full cleanup is required — three layers must be removed:

```bash
git submodule deinit <repo-name>                    # may error if not registered — that's fine
git rm <repo-name>                                  # remove from index
rm -rf .git/modules/<repo-name>                     # CRITICAL: remove cached module metadata
rm -rf <repo-name>                                  # remove working tree
```

**Why all four steps matter:** If `.git/modules/<repo-name>` still exists from a prior failed attempt, `git submodule add` will refuse with "found a local git directory" and `--force` alone won't help. The cached module entry must be deleted explicitly.

### Step 3 — Add submodule

```bash
git submodule add <url> <repo-name>
```

Git uses the proxy configured in `~/.gitconfig` (`http.proxy`). Do not rely on `HTTPS_PROXY` / `HTTP_PROXY` env vars alone — git reads its own config, not the shell environment.

**If clone fails with `curl 18 transfer closed`:** this is a network instability error (not a git config error). Check `~/.gitconfig` for the correct proxy port before retrying.

```bash
# Verify active proxy port in gitconfig:
git config --global http.proxy
# Compare with system proxy (macOS):
networksetup -getsecurewebproxy Wi-Fi
```

The system proxy port (set in System Settings) and the git proxy port (`http.proxy` in `~/.gitconfig`) may differ — e.g., system shows 7897 but git is still on 7890. Use the port git is actually configured with, or update gitconfig to match.

### Step 4 — Verify staging

```bash
git status
```

Confirm `.gitmodules` and `<repo-name>` both appear under "Changes to be committed".

### Step 5 — Update submodules.md (if it exists)

If `submodules.md` exists at repo root, append a row to the table:

```
| `<repo-name>` | <url> |
```

If the file doesn't exist, skip this step — do not create it.

### Step 6 — Commit

```bash
git commit -m "$(cat <<'EOF'
add <repo-name> submodule

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Rules

- **Root only**: always add to the repo root unless the user explicitly specifies a different path. Never use `.claude/skills/` or any subdirectory by default.
- **Sync submodules.md**: update the table in `submodules.md` in the same commit only if the file already exists.
- **One commit**: stage `.gitmodules`, `<repo-name>`, and `submodules.md` (if updated) together before committing.
- **Co-author footer**: always include the `Co-Authored-By` line in the commit message.

## Proxy configuration

| Layer | How to check | How to set |
|---|---|---|
| git (used by `git clone`) | `git config --global http.proxy` | `git config --global http.proxy http://127.0.0.1:<port>` |
| system (macOS) | `networksetup -getsecurewebproxy Wi-Fi` | System Settings → Network → Proxies |
| shell env (NOT used by git) | `echo $HTTPS_PROXY` | not reliable for git — use gitconfig instead |

When user says "use port XXXX proxy", update gitconfig if it differs, or pass `-c http.proxy=http://127.0.0.1:XXXX` inline.

---

## Example

User says:
> 添加 github 子仓库引用 git clone https://github.com/EA-Studio-SHARK/ai-morning-brief

Steps executed:
```bash
git submodule add https://github.com/EA-Studio-SHARK/ai-morning-brief ai-morning-brief
git commit -m "add ai-morning-brief submodule

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```
