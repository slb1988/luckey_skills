# AiReview 工具链本地模拟测试（Collect / Runner / Publish）

## 工具链分工与真正入口

- `Tools/AiReview/AiReviewContextCollect.py`（MainDev depot）只**备料**：采集 diff、`build_log_tail.txt`、`build_log_analysis.txt` 等到 out_dir，不启动 AI。
- `Tools/AiReview/AiReviewRunner.py` 才是**实际启动 Pi 分析的入口**——本地模拟评审跑的是它，不是 Collector。
- `Tools/AiReview/AiReviewResultPublish.py` 只解析 `pi_out.txt` 发布 verdict（Publish 契约见 SKILL.md 对应 memory）。

## 本地测试硬性前置

- 进程 cwd 与 `--workspace` 必须**都**指向 depot 根 `D:\MainDev`；脚本内相对路径推导以此为锚。
- Runner 等新文件可能只在 shelf 里而未提交（2026-09 实测：`Tools/AiReview/` 7 个文件含 Runner 存于 shelf，工作区没有，`p4 opened` 为空）——启动报「文件不存在」时先 `p4 describe` 核 shelf，别误判为被删，恢复前先确认无并行任务占用。
- 只读验证纪律：不 unshelve 业务 CL、不提交、不触发 TC / 业务回调，采集与输出一律落临时目录。

## 已确认根因：copyfile SameFileError 误标 missing（2026-09 本地测 CL 130205 发现）

新版采集把 informer 报告复制进 out_dir 时用 `copyfile`，而真实 TC 布局里**报告源目录与 collect 输出目录是同一目录**（同机同 workspace 的 `Saved/ai_review/`，布局见 [task-aireview-notification.md](task-aireview-notification.md)）→ src==dst 抛 SameFileError → 有效编译报告被标成 `missing`。注意 depot 现版 `AiReviewContextCollect.py` 尚无此 copy 逻辑，该 bug 在待提交的 shelf 版里——shelf 落地前必须修（src==dst 时跳过 copy 直接视为 present），否则线上链路每单丢报告。

## stream 过滤行为实测

CL 130205（shelf 含 MainDev `1.txt` + Wwise `a.cpp`）以目标 stream `MainDev` 采集：只 `1.txt` 进 diff，`a.cpp` 进 SKIPPED 节，不硬失败——印证 SKILL.md 中 STREAM_MISMATCH 的现行语义。
