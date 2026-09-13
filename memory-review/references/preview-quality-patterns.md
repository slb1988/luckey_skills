# 常见预览质量模式

| 模式 | 处置 |
|------|------|
| 自环边（`user -HAS_PREFERENCE-> user`、`x.vue -FIXES-> x.vue`） | remove 该边后 approve |
| Orca 派发模板污染：`orca(Project)` 被当作评审对象项目的属主 | remove 实体（级联清边） |
| 预览 1 实体 0 边、正文有实质内容 | approve `original` |
| novelty=evolution（演进链 SUPERSEDES/REFINES 旧记忆） | 正常 approve，链路本身即价值 |
| 个人偏好类记忆（硬件选型、购物兴趣） | 可批；这类画像是设计内的记忆类型 |
| `DECIDED` 边错挂 Person（`项目 -DECIDED-> 女儿/家长`，target 应是决策实体而非人） | 按三元组 remove（一个三元组可覆盖多条同三元组重复边），保留其余预览 approve curated |
| 整个预览只有 Orca 派发模板实体（`orca` + 派发约定），正文实际内容零抽取 | curated/original 都会灌噪音（original 正文大半是模板原文，Graphiti 重抽同样撞上）；建议 reject 或升级人工 |
| `orca` 实体不一定是污染：正文真实主题就是 orca 本身（如 Orca Arguments 配置机制）时合法 | 看正文主题而非实体名，勿误删 |
| 同一编码规则在多个 Linear 工单上被重复验证（换工单重述同一事实）、或正文只含单张工单的完成状态 | novelty 不保证覆盖同队列条目，须跨条目横向比对：通用规则只留最佳一份主记录，其余 reject；单工单完成状态按短期状态 reject |
| 正文/预览含事实性错误（校验条件写反、结论已被线上最终版本证伪或取代） | reject；需要留存时以修正版重投，勿批带病版本——错误事实入图谱比丢记忆危害大 |
| project/user 归属错误（worker 误标对话主体、记忆落错 project） | 不能原地带病批准：先向目标**物理 group** 重投干净摘要并验证 memory/episode 的 `group_id`；原条仍待审则 reject，已 indexed 则走 admin invalidate |
| 演进链兄弟条目对同一对象的归属事实矛盾（同批 c85 记备份任务建在 HBS 3，c94 实体写成 AList 托管且 `alist -RUNS-> 任务`） | novelty 演进分析（SUPERSEDES/REFINES）不标矛盾，须横向核对链条内事实一致性；删带病条目的错误归属实体（级联清边）后 approve，保留该条核心增量事实——两条都带病批会同时制造矛盾事实 + 同对象双节点 |
| preview 从正文提及的前身/参考链接脑补派生关系（正文是“替换/不更新了”，却抽成 `songloft -BASED_ON-> xiaomusic`） | 删幻觉源实体级联清边（或按三元组 remove）；顺带避免与同批同名异型实体（如 xiaomusic Project vs Service）被合并 |
| 同一对象的实体名变体横跨同批多条目（`project-lungfish`/`projectlungfish`/`ProjectLungfish`），且变体是预览的主实体 | 不要用 removals 删主实体（会掏空预览）；正常 approve。待 memory `indexed` 后重查目标物理 group，只有实际仍存在的独立节点才列为 `/graph/edits` merge 候选；preview 名称可能在批准重验或 Graphiti 写入时归入 canonical，不能凭审核包假定图上已生成同名节点 |
| 非 canonical 实体写法成对出现（`Memory Hub`/`memory-hub`、`xiaoyingtao`/`小樱桃`、`Chat Hub`） | 机制已接管大部分：preview 落库前机械规范化（NFKC+空白折叠+重名合并），casefold/normalized 唯一候选自动进别名管理页待审（approved 后批准重验自动改写）；漏网的仍按外科清理统一改到图谱 canonical 写法后再 approve |
