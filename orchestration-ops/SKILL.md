---
name: orchestration-ops
description: "编排纪律与 orca-coordinator 外挂（dispatch/wait/ack/settle/usage + 每次编排成本账单）。当协调 Orca worker、处理 ws: 任务派发、监督 DAG、收尾 dispatch、或需要某次编排的 token/成本账单时使用。命令语法一律以 `orca skills get orchestration` 和 `orca COMMAND --help` 实时输出为准（每个 Orca 版本首次使用时重读一次），本 skill 只装增量纪律。"
---

# Orchestration Ops（overlay，不克隆官方指南）

官方编排指南是版本匹配二进制分发的：**命令语法、flags、恢复流程一律实时查
`orca skills get orchestration` / `orca <cmd> --help`**，不要凭记忆或本文件猜。
本文件只装官方指南之外的增量纪律与外挂工具。

## 编排纪律（五条，2026-09-20 定版）

1. 调查类 worker 的 spec 直接授权「用仓库内凭据做只读实测探针」，探针不进协调者会话。
2. 用户连续迭代期 `worker-retain` 实施 worker，增量任务用 `--terminal <handle>` 复用原终端；
   确认不再迭代才 release。
3. 编辑 worker 写过的文件前必先 re-read 目标行，不靠记忆猜 oldText。
4. spec 长文一律 write 落文件 + 读文件传入（env-read-guard 拦命令串里的字面 dotenv 文件名）。
5. worker_done 后处理整批 Delivery 的每条消息再 ack；question 必回，release 前校验
   taskId+dispatchId。

<memory category="core-rules">
- `worker-start --spec` 可不建 task 直接派发，但前提是发起终端已绑定 Run；未绑定时派发失败、
  不建 run（事后表现为 run 列表没有新 run）。直派顺序固定为：建 Run → 绑定终端 → worker-start。
  排障时看派发输出的头部报错，tail 截断会漏掉。
</memory>

## orca-coordinator 外挂

脚本：`<skill 目录>/orca_coordinator.py`（Python 单文件，stdlib）。

```bash
python <skill目录>/orca_coordinator.py dispatch --worktree "path:D:\work\..." --spec-file <spec.txt> [--agent pi|codex] [--terminal term_x | --task task_x --retry-of ctx_x] [--run run_x]
python <skill目录>/orca_coordinator.py wait [--timeout-ms 900000]   # 滤心跳、整批原文、不自动 ack
python <skill目录>/orca_coordinator.py ack <deliveryId>              # 整批处理完后显式 ack
python <skill目录>/orca_coordinator.py settle <ctx_x> --mode reuse|retain|release [--force]
python <skill目录>/orca_coordinator.py usage <run_id> [--objective "..."] [--coordinator-session <path>]
```

- `dispatch` 只启动不阻塞（扇出：先全部 dispatch 再统一 wait）；receipt 与 spec 存
  `~/.orca-coordinator/runs/<run_id>/`。
- `wait` 输出整批 Delivery 原文；批次里每条消息处理完才 `ack`。
- `settle` 先查 worker-list 确认非 in_progress；迭代期默认 `--mode retain`。
- `usage` 按 session 内容中的 task_/ctx_ id 归因（slug+时间窗仅候选过滤，歧义报 unknown）；
  产出 markdown 账单 + `~/.orca-coordinator/bills/<run_id>.json` + 追加 `bills.jsonl` 趋势；
  cost 仅 pi 侧实测，codex 无 cost 记录标「未计」；codex 命中率 = cached/input（input 含 cached）。
- 日志：每次调用追加 `~/.orca-coordinator/logs/YYYYMMDD.log`（命令、耗时、rc、心跳计数）。

## 汇报约定

每次编排收尾向用户汇报时附 `usage` 账单（workers + coordinator + 合计），让用户对成本可见、
可迭代。
