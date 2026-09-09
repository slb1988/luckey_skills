# 关卡 2 自动决策开关（off|shadow|auto）与人工决策留样

权威文档：memory-hub 服务端 `docs/REVIEW_PIPELINE.md`（v20 节）。本文件只记审核操作所需的机制要点。

## 运行时三态开关（schema v20）

- `EXTRACTION_AUTO_REVIEW_MODES = ("off", "shadow", "auto")`（`service.py`），运行时模式存 `review_settings` 单行表；开关带短缓存、**跨进程生效**，dashboard 前端开关即切。
- **off（默认）**：不运行。首次启动与旧库迁移一律 off；不占 claim、不烧 attempts、**不产生影子 LLM 请求**（此前 token 消耗的来源）；预览 / novelty / intake / 人工 approve·reject / 决策留样全部不受影响。旧环境变量（含遗留 `DRY_RUN`）不再切换模式——升级到 v20 后已有部署默认即停耗。
- **shadow**：影子审计，只落审计轮次、**绝不处置**——shadow 恒为审计，「关掉影子」与「进入正式自动批准」是两个独立状态，不存在关影子反而自动放行。审计结果以可空 `auto_review_shadow` 字段（含 flags）出现在队列列表与详情，不伪装成人工/assistant 对话。
- **auto**：正式自动批准，只能由 admin 显式经 API 设置。

## 人工决策留样独立于影子（v20）

根因：旧「经验内化」只记录人工与影子的**分歧**，影子是学习样本的前提——一旦关掉影子（省 token），样本来源即断。v20 改为：

- `extraction_decision_samples` 表（schema v20）在每次**成功人工** approve/reject 的**同事务**写入；无影子、与影子一致、空理由都留样。
- **权威在 DB**；`data/review-feedback/extraction-decision-samples.jsonl`（`REVIEW_FEEDBACK_DIR` 配置）只是**镜像**——镜像失败绝不阻塞决策，只记 error 日志；可用 `python3 scripts/export_decision_samples.py` 从 DB 整体重建。
- 支持按项目 / 时间 / 记忆 ID 导出，供后续用大模型定位排查、优化上游抽取审核 prompt。

## 拒绝原因弹框

Dashboard 抽取审核的拒绝入口统一弹框填原因，textarea **可选**（空 / 纯空白允许，取消无动作，原话只做 trim）；经既有 rationale 链路落 `decision_rationale` 列并进入决策样本；详情抽屉对已决记录显示处置理由。

## 上游 prompt 草稿内化

可内化案例 = 有理由 / 有人工纠正的决策样本；据此生成上游抽取审核 prompt 的**待激活草稿**——不逐次调用模型、不自动激活、不自动改动正在生效的 prompt，人工确认后才生效。
