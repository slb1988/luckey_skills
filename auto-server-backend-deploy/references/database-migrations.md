# 数据库迁移与后端发布

<memory category="troubleshooting">
- **CL 1530 确认根因**：新版代码依赖 `ai_review_jobs.requeue_requested`，而当时 `/data/py_automation/backend/deploy.sh` 未执行数据库迁移，形成代码/schema 不一致；详情 500 并非 review 数据损坏。
- 该缺列查询在 `pending` 路径触发，`done/running/failed` 跳过，因此部分详情正常不能证明迁移已完成；同一缺列也影响 AI 队列轮询和部分构建回调。
</memory>

<memory category="core-rules">
- **发布约束（排查时尚未实现保护）**：涉及 schema 的新版后端，必须在启动前完成数据库迁移，迁移失败须中止发布；代码同步、进程启动成功不能代替 schema 验证。
- **迁移链前置条件**：迁移执行依赖完整的历史 revision 链。CL 1530 排查时，迁移链引用了未入库的 `7a0c333004f0`；该缺口未解决前，仅追加 `db upgrade` 不足以形成可用的发布保护。
</memory>
