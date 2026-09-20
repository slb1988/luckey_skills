#!/usr/bin/env python3
"""按组交错 + 等 indexed 的批量批准驱动（同组串行门禁）。

每轮：rescan 取新 token -> 每组取一条 pending 决策 apply -> 轮询本批 memory_status 至 indexed。
apply 失败/超时按未知处理：rescan 核实 review 状态，已 approved 的转入 indexed 等待，否则留待下轮。

DECISIONS 用完整 review_id：8 字符前缀已实测撞车（同批 01a0ba00/01a0b9f8/01a0b9f4 各两条）。
"""
import importlib.util
import json
import os
import subprocess
import sys
import time

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
RQ = os.path.join(SKILL_DIR, "review_queue.py")

spec = importlib.util.spec_from_file_location("review_queue", RQ)
rq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rq)

# (full_review_id, project/group, content_mode, rationale)
DECISIONS = [
    # ---- round-robin: obsidianvault / admin / memory-hub / auto-server ----
    ("01a0ba3c-6cf7-7e09-86d7-0f831cf57f5d", "obsidianvault", "original",
     "auto-review: 薄预览（1 实体 0 边），正文含门禁节奏固化为 drive_approvals.py 与 32/35 零失败复验等长期事实，按 original 保留蒸馏文；novelty=evolution"),
    ("01a0ba2e-82b5-7614-a0a0-659062dbecb6", "admin_sun_depot_7184", "curated",
     "auto-review: 视图外文件容忍逐 hunk 移植 IMPLEMENTS 边有正文支撑（6 文件明细+142 测试）；ai-review 挂已有 canonical；novelty=evolution"),
    ("01a0ba2b-21f5-7898-bd74-3e635b73d131", "memory-hub", "curated",
     "auto-review: fcntl 归因 APPLIES_TO 边有正文支撑（cli→agent_integration→fcntl 导入链，非 faaf5dc 回归证据）；novelty=evolution"),
    ("01a0ba2f-e6f7-76f9-bba5-25b8404881f3", "auto-server", "original",
     "auto-review: 3 实体 0 边薄预览，正文有 09-16/09-18 蒸馏产出与选料教训等实质价值，按 original 批准；novelty=evolution(SUPERSEDES 进度状态)"),

    ("01a0ba28-524d-7dee-8107-2b9e72ca7ace", "obsidianvault", "curated",
     "auto-review: kid-star-review-switch APPLIES_TO 边如实标注仅评审未实施（1P1+2P2）；两实体均挂已有 canonical；novelty=evolution"),
    ("01a0ba2d-8ce2-7953-aa12-f08e35780197", "admin_sun_depot_7184", "curated",
     "auto-review: $dst: 驱动器限定变量插值根因与修复边有正文支撑（versioned settings 自动提交 change 1784）；teamcity casefold 归并 Teamcity；novelty=novel"),
    ("01a0ba23-8861-79b7-a084-0debb82e7f77", "memory-hub", "curated",
     "auto-review: search-v2 503 根因边有正文支撑（injection_text 345>320 parser 上限，未热修未回滚如实标注）；novelty=evolution"),

    ("01a0ba27-7103-7552-9547-d25132c9aa8a", "obsidianvault", "original",
     "auto-review: preview_attempts=3 到限；正文有实质长期价值（ChatHub 四处验收缺口修正 92/92、skills 提交哈希、模板初始化≠记忆迁移边界），按 original 跳预览批准；novelty=evolution"),
    ("01a0ba29-3cbd-7e2b-a719-9af2859dd537", "admin_sun_depot_7184", "original",
     "auto-review: 空预览但正文有实质价值（SUPERSEDES 修复已交付结论：探针/DSL 检查/Flow20803 未通过验收，阶段收口未应用）；novelty=evolution"),
    ("01a0ba21-cafa-70ad-8405-a317116d9002", "memory-hub", "original",
     "auto-review: 薄预览（1 实体 0 边），正文含 v1.1 全量测试精确数字+fcntl 导入链+根治建议，按 original 批准；novelty=evolution"),

    ("01a0ba26-486b-72f9-ad60-060a11129b23", "obsidianvault", "curated",
     "auto-review: k3 评审两条 APPLIES_TO 边有正文支撑（过度设计删减点、保障降级如实标注未授权）；chat-hub 挂已有 canonical；novelty=evolution"),
    ("01a0ba24-95f7-7182-ba4a-2b61a61a4ce3", "admin_sun_depot_7184", "curated",
     "auto-review: 404 根因五边均有正文支撑（job55 调用链、rev#18 归属、Patch A/B 如实标注未确认）；P4Adapter 挂已有 canonical；novelty=evolution"),

    ("01a0ba20-ff14-7de8-9d5b-58a857c35b72", "obsidianvault", "curated",
     "auto-review: Windows 迁移决策 APPLIES_TO 边如实标注编排未结算、无实施确认；teamcity-pln 挂已有 canonical；novelty=evolution"),
    ("01a0ba23-1fd4-7de4-b1e4-f6b6afbc4fe5", "admin_sun_depot_7184", "original",
     "auto-review: 空预览但正文有边界价值（1615/1616 CONFIRMS+剩余边界=DSL 拉取/部署/smoke 需授权），按 original 批准；novelty=evolution"),

    ("01a0ba1e-d853-783c-bf15-0b8176915e73", "admin_sun_depot_7184", "curated",
     "auto-review: AI Review 会话延续研究 PART_OF/PROPOSED_FOR 边有正文支撑（三表设计为助手建议如实标注）；两个 suspected 实体由批准重验归并 canonical；novelty=novel"),
]

GROUP_ORDER = ["obsidianvault", "admin_sun_depot_7184", "memory-hub", "auto-server"]
POLL_INTERVAL = 20
POLL_TIMEOUT = 15 * 60


class Args:
    base_url = None
    agent_id = None
    project_id = None


client = rq.make_client(Args())


def fetch_open_details():
    queue = client.get("/review/extraction?status=open&limit=200")
    out = {}
    for it in queue.get("items", []):
        rid = it["review_id"]
        d = client.get(f"/review/extraction/{rid}")
        out[rid] = d
    return out


def get_memory_status(review_id):
    try:
        d = client.get(f"/review/extraction/{review_id}")
        return d.get("memory_status"), d.get("status")
    except Exception as exc:
        return None, f"error:{exc}"


def main():
    pending = {}
    for rid, group, mode, rationale in DECISIONS:
        pending.setdefault(group, []).append(
            {"rid": rid, "mode": mode, "rationale": rationale})
    in_flight = {}  # group -> review_id
    done, skipped = [], []

    round_no = 0
    while True:
        active_groups = [g for g in GROUP_ORDER if pending.get(g) or g in in_flight]
        if not active_groups:
            break
        round_no += 1
        print(f"\n===== round {round_no} =====", flush=True)

        # 1) 等 in-flight  indexed
        for g in list(in_flight):
            rid = in_flight[g]
            deadline = time.time() + POLL_TIMEOUT
            while True:
                ms, rs = get_memory_status(rid)
                print(f"  poll {rid[:8]} group={g} memory_status={ms} review_status={rs}", flush=True)
                if ms == "indexed":
                    done.append(rid)
                    del in_flight[g]
                    break
                if isinstance(rs, str) and rs.startswith("error:"):
                    print(f"  !! detail 读取异常，按未知处理暂停本组：{rs}", flush=True)
                if time.time() > deadline:
                    print(f"  !! 等待 indexed 超时（{POLL_TIMEOUT}s），停止本轮后续批准：{rid}", flush=True)
                    return 2
                time.sleep(POLL_INTERVAL)

        # 2) rescan 取新 token
        try:
            details = fetch_open_details()
        except Exception as exc:
            print(f"rescan 失败：{exc}；30s 后重试", flush=True)
            time.sleep(30)
            continue
        by_prefix = {}
        for rid, d in details.items():
            by_prefix[rid] = d

        batch = []
        for g in GROUP_ORDER:
            if g in in_flight or not pending.get(g):
                continue
            item = pending[g][0]
            hit = by_prefix.get(item["rid"])
            if not hit:
                print(f"  skip {item['rid'][:8]}（已不在 open 队列，并发处理或状态变化）", flush=True)
                skipped.append(item["rid"][:8])
                pending[g].pop(0)
                continue
            d = hit
            rid = item["rid"]
            st = d.get("status")
            if st in ("preview_pending",):
                print(f"  skip {item['rid'][:8]} 本轮 status={st}，等预览", flush=True)
                continue
            item["review_id"] = rid
            item["token"] = d.get("snapshot_token")
            batch.append((g, item))

        if not batch:
            if not in_flight:
                print("本轮无可批条目且无 in-flight，结束。", flush=True)
                break
            continue

        decisions = {"removals": [], "rejections": [], "approvals": [
            {"review_id": it["review_id"], "content_mode": it["mode"],
             "snapshot_token": it["token"], "rationale": it["rationale"]}
            for _, it in batch]}
        path = os.path.join(SKILL_DIR, "decisions_round.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(decisions, fh, ensure_ascii=False, indent=1)
        print(f"  apply {len(batch)} 条：" + ", ".join(f"{it['rid'][:8]}({g},{it['mode']})" for g, it in batch), flush=True)

        proc = subprocess.run(
            [sys.executable, RQ, "apply", path],
            capture_output=True, text=True, cwd=SKILL_DIR, timeout=600)
        out = (proc.stdout or "") + (proc.stderr or "")
        print(out, flush=True)

        for g, it in batch:
            rid = it["review_id"]
            line_ok = f"APPROVE {rid[:8]} -> approved" in out or f"-> already_processed" in out
            if line_ok:
                if "already_processed" in out and f"APPROVE {rid[:8]} -> already_processed" in out:
                    skipped.append(it["rid"][:8])
                    pending[g].pop(0)
                    continue
                pending[g].pop(0)
                in_flight[g] = rid
            else:
                # 失败/超时/review_changed：按未知处理，核实当前状态
                ms, rs = get_memory_status(rid)
                print(f"  verify-after-fail {rid[:8]}: memory_status={ms} review_status={rs}", flush=True)
                if rs == "approved":
                    pending[g].pop(0)
                    in_flight[g] = rid
                # 否则留在 pending，下轮 rescan 取新 token 重试

    print("\n===== 汇总 =====")
    print(f"approved+indexed: {len(done)}")
    for r in done:
        print(f"  {r[:8]}")
    print(f"skipped(并发/消失): {skipped}")
    leftover = [it["rid"][:8] for g in GROUP_ORDER for it in pending.get(g, [])]
    print(f"未批准剩余: {leftover}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
