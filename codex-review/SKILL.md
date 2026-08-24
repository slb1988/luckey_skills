---
name: codex-review
description: Codex 评审迭代工作流——用 codex exec review 评审未提交改动，逐轮修复/复审直到零发现后才入库。【显式触发】仅在用户明确要求评审时使用，如"review 一下"、"帮我评审/审一下这些改动"、"codex review"、"入库前检查一下"、"跑一轮 review"、"按评审流程走一遍"、"提交前帮我审一审"。用户没提到评审时绝对不要主动触发本 skill；日常开发和 commit 前默认不跑评审。
---

# Codex Review（显式触发，不默认执行）

## 触发原则

本 skill 只在**用户明确要求评审**时执行。开发完成、commit 之前都**不要**自动套用本流程——用户没提 review/评审就直接正常交付。

触发后按下面的流程跑，目标是保证进入仓库的是健壮版本，而不是「能跑」的版本。

## 快速流程（本地直跑）

```bash
cd <仓库根目录>
codex exec review --uncommitted        # 评审 staged+unstaged+untracked 改动
```

- **`--uncommitted` 与自定义 PROMPT 互斥**：想加自定义评审重点就不能传
  `--uncommitted`；评审未提交改动就用裸 `--uncommitted`。
- 其他形态：`--base <branch>`（对分支评审）、`codex exec review -`（stdin 读指令）。
- 本机 codex CLI：`/opt/homebrew/bin/codex`（已登录，无需额外配置）。

## 迭代纪律

1. **每条发现都要修复或显式驳回**（驳回要在 commit message / 文档里留理由）。
2. **每个修复配回归测试**——先复现（红），修复后转绿。
3. **修完一轮立刻再跑一轮 review**：评审发现是逐轮深入的（第一轮通常抓并发/正确性，
   后面抓配置耐久性、UX 一致性、缓存陈旧等边缘问题）；连续一轮无发现才视为收敛。
4. 全量回归（不只跑新测试），再 commit & push。
5. 评审反馈里涉及**通用模式**的经验，回填到
   [references/codex-review-workflow.md](references/codex-review-workflow.md) 的
   「常见缺陷模式」一节。

## 用 Orca 编排跑独立窗口 codex 评审

需要 codex 在独立窗口审、本侧等结果再修复时，走 Orca supervised orchestration
（run-create → task-create → `worker-start --task <id> --worktree current --agent codex`
→ `check --wait` → 修复 → `worker-release`）。**关键**：

- P4 pending 改动评审必须 `--worktree current`（新 worktree 看不到未提交 CL）。
- worker 假死识别（codex 自更新退出/手动 kill 后 dispatch 仍显示 dispatched）：
  先 `dispatch-show` / `worker-read` 确认，再 `worker-abandon` + `--retry-of` 重启。
- `check --wait` 输出是 NDJSON 心跳 + 尾部 pretty JSON，别按行 parse。
- Codex worker 收到带 task/dispatch/capability 的 live preamble 后，生命周期回报只能走
  preamble 给出的 `orca orchestration` 命令；不要用 Codex 内建 sub-agent/提问通道代替。
- Windows PowerShell 不能直接复制 preamble 里的 bash `\` 续行；改成单行，长
  `worker_done --body` 用 PowerShell literal here-string，避免引号和换行损坏 payload。
- worker 主动工作时每 5 分钟 heartbeat；`worker_done` 必须恰好一次，成功后立即停手。
  只读长评审若要求逐条发现，dispatch 时应显式允许写独立 report artifact，否则
  「body 仅 3 句」会迫使 worker 把完整报告塞进一条超长句子。

命令以 `orca skills get orchestration` 的版本匹配指南为准；完整踩坑清单见仓库根目录
`references/orca-orchestration.md`。

## 深入参考

- [references/codex-review-workflow.md](references/codex-review-workflow.md) ——
  常见缺陷模式（在途竞态 / 阈值当状态 / 假成功 / 聚合残留 / SQLite 加列）、
  确定性复现竞态的测试技巧。评审中遇到具体问题时读。
