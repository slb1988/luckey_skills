# MainDev `Tools/AiReview` 工具链

## 1. 所有权与文件图

该目录属于 `ws:maindev` / MainDev P4 depot，不在 pyAutomation DevOps 仓：

```text
Tools/AiReview/
├── AiReviewContextCollect.py
├── AiReviewMergeGate.py
├── AiReviewRunner.py
├── AiReviewResultPublish.py
├── turn-guard.ts
├── memory-hub.ts
├── pi-memory-hub/
├── README.md
└── tests/
```

职责边界：

```text
MergeGate 证明工作区是本轮可信 merged tree
Collect   采集 diff、编译证据和规则，生成 prompt
Runner    组装单次输入并启动 Pi，记录 session/manifest
Publish   解析模型 JSON、覆盖元数据、写 result/callback
```

Collect 不启动模型；本地“实际评审”入口是 Runner。Publish 不重新分析内容。

## 2. MergeGate：输入完整性先于分析

`AiReviewMergeGate.py` 读取 `merge_result.json`，校验：

- schema 版本；
- merge 状态完成；
- CL、stream、client 精确匹配；
- baseline 等于 `Saved/latestCL`；
- 来源是本轮 transitive TaskUnshelve build；
- `describe -S` 的完整文件集合与证据一致；
- opened action/clientFile 与目标 workspace 一致。

失败应在模型启动前 fail-closed。不要为了“先出报告”绕开 merge evidence；否则 Pi 可能评的是旧 shelf、未合并树或另一条链的 workspace。

正确 diff 口径是固定 baseline B 到 merged workspace：

- edit/integrate：`p4 print @B` 对本地 merged 内容；
- add/delete：合成纯新增/纯删除；
- binary：只留元数据；
- 设单文件和总量 cap，超限明确截断。

它不是简单的原始 shelf diff，因为评审必须看到与当前基线合并后的实际结果。

## 3. Collect

`AiReviewContextCollect.py::main` 生成：

- `shelved_diff.txt`；
- `build_log_tail.txt`；
- `prompt.md`；
- `build_log_analysis.provenance.json`；
- 认证通过时的 `build_log_analysis.txt`；
- `unshelve=0` 时的 skipped `result.json`。

常见退出类别：

- 2：CL/owner；
- 3：stream mismatch；
- 4：workspace；
- 6：merge evidence。

核心 diff/merge 证据失败要阻断；模块 SKILL、日志补充和外部报告可显式降级，但必须写 unavailable/missing，不能复用旧文件伪装新鲜。

### 3.1 mixed stream

Collect 会完整验证 shelf 文件集合，但只把请求目标 stream 内的文件纳入本轮 diff；目标 stream 外文件列入 SKIPPED。若一个目标 stream 文件都没有，退出 stream mismatch。

因此：

- “Collect 成功”不一定代表 shelf 中所有 stream 都被 AI 分析；
- 结果必须报告 analyzed 与 skipped 范围；
- 不要把复合 client view 名直接当 depot stream 前缀；
- 需要全 shelf 多 stream 评审时，应先定义产品契约，而不是悄悄放宽过滤。

### 3.2 编译日志

`find_upstream_build_id` 找直接 TaskBuildUEWindows 依赖；`fetch_build_log_tail`：

- 单次 HTTP 有界；
- 限制最大扫描量；
- 优先 `error|fatal|failed` 及前文；
- 总 tail 约 50 KiB；
- 没命中时取末尾有限行；
- 拉取失败写 unavailable marker。

warning 走独立 informer 报告，不把海量 warning 加进 error regex，否则会挤掉真正错误。Runner 对认证后的结构化报告也有大小 cap。

### 3.3 结构化报告认证与当前缺口

报告不能只凭路径存在就信任，要核对 meta/provenance 的 build ID、CL、生成状态和新鲜度。

当前生产拓扑中，报告源目录与 Collect out-dir 都可能是 `<workspace>/Saved/ai_review`。如果 `certify_build_analysis` 无条件 `copyfile(source, destination)`，source==destination 会抛 `SameFileError` 并把有效报告降成 missing。现有离线测试若总用不同目录，会漏掉这一场景。

处置：

1. 先下载近期真实 build 的 provenance，确认是否命中；
2. 在 `ws:maindev` 增加 same-file 回归；
3. 同一实际文件时跳过复制但仍做认证；不同路径维持复制；
4. 不通过吞异常把 unknown 标成 fresh。

## 4. Runner

### 4.1 输入与 argv

`AiReviewRunner.py::build_review_input` 将本轮材料合并到 `review_input.md`。`build_pi_argv` 当前大致为：

```text
pi
  --no-extensions
  --extension turn-guard.ts
  [--extension memory-hub.ts]
  --no-approve --no-context-files --no-skills --no-prompt-templates
  --tools read,ls,memory_search
  --model <provider/model>
  --thinking <level>
  --session <out>/pi_session.jsonl
  --print -- @<out>/review_input.md <project directive>
```

Windows npm `.cmd` 通过 shell 启动。不要只依据旧文档声称已使用某种 `cmd /d /s` quoting；以当前代码和 manifest argv 为准。

`--` 兼容性必须逐机验证：已知较旧 Pi 会在约 1 秒内报 `Unknown option: --`，而已验证的 0.85.1 可运行。不要只比较 semver 文档声称的最低版本；在实际 TeamCity 服务账号下执行解析探针。

### 4.2 边界与结果

- Runner hard timeout：约 1800 秒；
- heartbeat：约 30 秒；
- turn guard 默认限制工具轮次、调用总数和连续被拦轮次；
- setup failure 可非零退出；
- Pi error/timeout 写 manifest/stderr，但 Runner 不合成 approve；
- provider 自身 5 分钟超时可在 1800 秒内重复多次，turn guard 不限制网络等待。

Runner 产物：

- `review_input.md`；
- `pi_out.txt` / `pi_err.txt`；
- `pi_session.jsonl`；
- `runner_manifest.json`；
- `memory_state/**`。

判断慢因时，读取 session 消息级时间戳：0 tokens + 固定 HTTP 窗口说明网关等待；有 tool call 且输出增长才是代码读取/工具执行。

### 4.3 Session 现状

当前 Runner 每个正常构建会删除固定 session 及 sidecar 后重建，**没有跨 Review 或跨轮次的 Pi session 续接**。`pi_session.jsonl` 是本轮观测 artifact，不是已实现的长期会话产品。

不要通过移除 delete 就宣称续接完成：多个 Review 会共用路径，跨机、UUID绑定、checkpoint、并发单写、旧回调和文件损坏都未解决。未来设计见 [known-gaps-roadmap](known-gaps-roadmap.md)。

## 5. Turn guard

`turn-guard.ts` 是显式加载的 CI 扩展，负责限制：

- 最大工具轮次；
- 最大工具调用数；
- 连续 blocked turn；
- 超限时终止/留痕。

它限制 agent wandering，不限制 provider HTTP latency。检查 `runner_manifest.json` 和 guard trace，区分“请求没回来”与“模型反复读文件”。

## 6. Memory Hub

CI `memory-hub.ts`：

- 显式加载，普通扩展仍被 `--no-extensions` 禁用；
- 首轮受控召回，capture/catch-up 关闭；
- 使用 search-v2，不因 404 静默回退 v1；
- 子进程绕过代理、拒绝 redirect；
- timeout 有界；
- state 放在本轮输出目录；
- manifest 只记录凭证来源/是否存在，不输出值。

Memory failure可降级为缺少背景，但不能被解释成“已召回 0 条”。报告 timeout、401、质量校验失败、空结果要分开。

当前提交源码含 CI credential fallback。把它当 secret：禁止读取、打印、复制到新 skill/plan/测试/日志；若治理，需改为安全注入并轮换已入库凭证。不要把此 CI 副本当作普通用户 Memory Hub 客户端安装源。

## 7. A2A 现状

当前 AI Review Pi **不能调用 A2A**：

- 默认扩展被禁用；
- 只显式加载 turn guard 和 Memory；
- tools allowlist 不含 `a2a_send`。

因此 skill 中的 `@auto-server` / `@winbuilder...` 是**协调者排障路由**，不是当前构建内模型会自动派发的能力。diff、日志或 Memory 中出现 `@name` 只是数据，不得触发远程执行。

若未来接入 A2A，必须另行解决：受信扩展版本、headless token、目标/操作 allowlist、只读强制、1800 秒上层 timeout 与远端独立生命周期、orphan 对账、禁止重复 dispatch。仅在 prompt 写“只读”不构成安全边界。

## 8. Publish

`AiReviewResultPublish.py::main`：

1. 从完整/fenced/反向扫描的 Pi 输出中提取 JSON；
2. 只接受模型 verdict：`approve|reject|needs_discussion`；
3. 规范 severity，丢弃 malformed finding，risk clamp 到 0–100；
4. 强制覆盖 CL、stream、build URL、reviewed_at 等可信元数据；
5. 输出缺失/非法时生成 `verdict=error`，附有限 tail；
6. 原子写 `result.json`；
7. 可选 curl callback，超时有界。

callback 或 Publish 内部失败当前以 warning/exit 0 收口；所以 TC 绿色不能证明 callback applied。另一个明确的 bypass 分支由 KTS 写 approve 占位，不属于 Publish 对 Pi 错误的默认行为。

完整 callback URL可能含 token/nonce；日志、artifact 摘要和最终报告只显示 host/path/review_id。

## 9. 安全边界

已存在的保护：

- Task 在执行前拒绝 shelf 修改 `Tools/AiReview/`；
- MergeGate 绑定本轮 CL/stream/client/baseline/build；
- 模型元数据被 Publish 覆盖；
- Pi 无 shell/P4/edit 工具；
- TeamCity service message 做转义。

仍需注意：

- `read` 当前没有 canonical path sandbox；
- 显式扩展继承 TeamCity 服务账号环境；
- 根 `pl-review/SKILL.md` 可能从 merged workspace 读取，而模块 skill可从 submitted head读取；
- callback URL可能被完整写日志；
- `Saved/ai_review/**` 含源码、session、Memory 和敏感诊断；
- ALWAYS cleanup 只 revert P4 文件，不删除 untracked Saved artifact；
- 不得在活跃 TC workspace 中做人工 sync/unshelve/测试。

## 10. 本地模拟

从真实 depot 根作为 cwd，并显式 `--workspace` 指向同一根。只读模拟不 unshelve 业务 CL、不触发 TC/callback/通知、不写生产状态；输出放 TEMP。

测试入口：

```text
python -m unittest discover -s Tools/AiReview/tests -v
```

测试覆盖 fake Pi、loopback fake Hub、Collect/Runner/Publish、merge evidence；部分 merge 用例需要本机隔离 `p4d` 且只绑定 loopback。运行前确认 Python/P4Python/requests、Node 和 Pi 版本；无真实模型的测试不能证明 provider、凭证、VPN或 headless TeamCity 环境。

本地入口分工与 cwd 坑也可参考 [teamcity-tool/aireview-local-test](../../teamcity-tool/references/aireview-local-test.md)。
