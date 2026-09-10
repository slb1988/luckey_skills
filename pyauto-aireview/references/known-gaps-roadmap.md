# 现行能力、已知缺口与路线边界

本文件防止把历史计划、当前源码和未来设计混为一谈。每次执行前仍需核 P4 head、部署 revision 和运行参数。

## 1. 当前已实现

- P4V Request Review 刷新 shelf、释放关键锁、打开申请页并后台收口本地 workspace。
- `/ai_review/request` 预检、创建/reopen、文件/diff首屏、参与者、评论、活动流。
- AI job持久 stage、秒级 kick + 60秒补偿 ticker、claim/fence/retry。
- Windows `PLN_FlowAiReview`：Sync → Unshelve/merge → BuildUEWindows/AS/report → TaskAiReview。
- Unshelve后固定baseline merge、`resolve -N`复查、版本化 `merge_result.json` 和 backend merge gate。
- MainDev Collect/Runner/Publish、turn guard、CI Memory search-v2、callback代际和metadata覆盖。
- callback定案优先；error/skipped时backend LLM fallback。
- 指定 reviewer、self、strict jury、自动批准、branch closed direct pass和approve gate。
- 独立 `ai_review_submit_jobs`，30秒submit worker、workspace/domain串行、跨域并行。
- submit unknown/manual、stale recovery、只读ghost/CL-missing对账和auto-merge。
- reviewer/AI/compile/comment/submit通知与前端submit progress。

## 2. 当前未实现或未完全实现

### 2.1 同一 Review 的 Pi 真续接

当前 Runner每轮删除固定 `pi_session.jsonl`并新建会话。尚无：

- Review.id ↔ Pi session UUID唯一绑定；
- 多轮 turn/report版本；
- 原生session目录长期保存；
- 服务端checkpoint与跨机恢复；
- 轻量 `TaskAiReply`；
- 追问/纠错UI；
- 人工裁定样本→规则候选→回放闭环。

因此“重新分析”是新一轮无状态执行，不是继续原 Pi上下文。不要把 session artifact存在误报成产品已支持续聊。

### 2.2 构建内 A2A

当前 Runner未加载 a2a-mentions且allowlist没有 `a2a_send`。协调者可以用 `@agent`排障，但构建里的Pi不会自动远程查机器。

未来若接入，需要服务端强制的目标/操作allowlist、headless凭证、只读能力、orphan对账与逐机验收；不能只把工具名加进argv。

### 2.3 路径沙盒与受信输入

Pi无shell/edit/P4工具，但 `read` 仍缺严格canonical root限制；显式扩展继承服务账号环境。根 `pl-review` 可能来自merged workspace，而模块规则/工具有submitted-source保护。需要统一受信bundle和路径sandbox，不能假设 `--tools read` 等于任意文件都安全。

### 2.4 Session/artifact敏感面

`Saved/ai_review/**` 可包含diff、prompt、session、Memory和callback诊断，当前清理主要处理P4 opened和部分Pi文件，不代表敏感untracked文件已清。artifact保留、访问、脱敏和过期策略仍需明确。

### 2.5 结构化 warning报告 same-file

当前Collect认证代码与TC布局可能形成 source==destination `copyfile`，导致有效报告被标missing。需要先用真实 provenance确认，再在 `ws:maindev`加同路径回归并最小修复。

### 2.6 构建机版本一致性

Runner使用 `--print -- @file`；较旧Pi可能不支持 `--`。当前没有证明所有WinBuilder都具备同一Pi/Node/Python/Memory环境的中央准入门。必须逐机测，不能用一台成功外推。

### 2.7 Secret治理

现有源码包含CI credential fallback和其他可能的hardcoded fallback。skill不保存值；治理需要迁移到安全注入、限制日志/URL、轮换已入库凭证并验证所有构建机。仅删除当前文件中的字符串不能使git/P4历史里的值失效。

### 2.8 callback可观测性

Publish/curl失败可warning-only并保持TC绿色；完整callback URL还可能进入日志。需要持续核后端activity并改进脱敏/投递确认，不能只看build status。

## 3. 已退役行为：不要复活

| 旧行为 | 现行替代 |
|---|---|
| Linux `TaskBuildUELinux` AI Review链 | Windows `TaskBuildUEWindows` + WinBuilder池 |
| 后端按branch busy门阻止TC投递 | TC立即投递；Agent/workspace与队列负责调度 |
| `ai_queue.blocked_by`业务排队UI | `ai_queue`兼容字段为空；看compile/build状态 |
| submit失败按固定次数自动重试并耗尽reject | 一次失败停，人工retry/reject；stale/ghost只读对账 |
| `AI_REVIEW_SUBMIT_RETRY_MAX`控制现行提交 | 兼容配置名可能保留，但现行worker不读取 |
| AI worker中的120秒submit sweep | 30秒独立submit worker/sweep |
| 根据作者+描述/最近CL猜rename结果 | 明确P4回执或cl_state；未知→manual |
| gate自动创建Review | `/ai_review/request`是创建/reopen入口 |
| 规则skip/exemption绕过门禁 | submit validation与review gate fail-closed |
| API `/api/ai_review/...` | 当前 Flask路由 `/ai_review/...` |
| TaskAiReview默认Linux工具/grep/find | 当前Windows Runner + read/ls/memory_search |
| timeout或基础设施错误合成approve | `verdict=error` + backend fallback/failed |

排查旧build时可按当时revision读旧语义，但修当前系统不能依据历史事故文档恢复这些路径。

## 4. 近期推荐优先级

### P0：安全与正确性

1. 迁移并轮换源码中的embedded/hardcoded credential；
2. 验证并修复结构化warning报告same-file；
3. 给所有候选WinBuilder建立Pi/Node/Python/Memory版本准入；
4. callback URL和artifact脱敏；
5. 对受信工具/rules/read路径做不可被shelf替换的隔离。

### P1：可观测性与时延

1. Dashboard直接显示 Review ↔ Flow ↔ Task ↔ Agent身份映射；
2. 记录Memory、每次provider attempt、backoff和fallback到结构化timeline；
3. model gateway健康熔断/总deadline，避免固定多次长timeout；
4. backend fallback若与Pi共享同一故障域，增加独立降级或明确fast-fail；
5. callback投递确认与后端activity缺失告警。

### P2：持续对话与经验闭环

推荐方案保持：

- 一个稳定 Review.id绑定一个Pi session UUID；
- 每轮短进程精确resume，不建普通LLM伪续接；
- session存在运行账号Pi原生目录，服务端保不可变checkpoint；
- 首评/代码refresh走完整Flow；纯追问走无Sync/Unshelve/Build的轻量Task；
- 报告版本不可变，reply/keep/revise分开；
- 每轮仍做Memory召回，但完整评审session不自动上传Hub；
- 用户纠错先保存为候选样本，人工确认和冻结回放通过后才更新 `pl-review`或prompt；
- 回复不改人工票、不提交P4、不自动改共享规则。

这是设计方向，不是现行API或数据库契约。实施前需用户确认产品取舍并重新核并行代码。

## 5. 文档漂移处理

已知旧资料容易出现：

- Linux/Windows节点名漂移；
- 作者按钮/决策规则与源码不一致；
- KTS描述文字说bypass default，但参数值实际是review；
- pending CL已提交、撤回或被后续CL覆盖；
- Memory endpoint/credential策略变化；
- A2A等待/取消语义变化。

采用以下规则：

1. runtime回答“线上现在”；
2. P4 head/source回答“代码现在”；
3. 模块SKILL用于索引稳定机制；
4. plans只回答“曾计划/待确认”；
5. 发现drift单独报告，不悄悄融合两个版本；
6. 文档更新使用时态中立描述，事故编号/日期放plan或个人memory。

## 6. 变更状态报告

任何涉及路线项的汇报都使用：

```text
Current source: 已实现/未实现，revision
Production: 已部署/未核实，effective config
Pending: 哪个workspace/CL，是否shelved
Validated: unit / isolated / builder / TC / production
Authorized: develop / submit / deploy / mutate production
```

不要使用“已完成”笼统覆盖五种状态。
