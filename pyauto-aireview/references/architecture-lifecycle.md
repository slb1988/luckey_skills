# AI Review 架构、对象身份与生命周期

## 1. 参与者与责任边界

| 组件 | 主要责任 | 业务真相 |
|---|---|---|
| P4V `RequestReview.py` | 刷新 shelf、交接作者 workspace、打开申请页、后台收口本地 workspace | 作者本机状态与原 shelved CL |
| Web 前端 | 申请、详情、diff、AI 报告、评论、决策和提交进度展示 | 只展示 API 投影，不是状态权威 |
| pyAutomation backend | Review 状态机、AI/compile/submit job、回调、决策、通知、P4 对账 | Review、活动流和任务行 |
| TeamCity | 同机执行 Sync、Unshelve/merge、Build/AS/报告、Pi 评审 | 具体 build、step 与 artifact |
| MainDev `Tools/AiReview` | 校验合并证据、组装上下文、启动 Pi、校验并发布结果 | 本轮评审输入、session、manifest、result |
| build-api-proxy / 模型上游 | Pi 与 backend fallback 的 LLM 调用 | 请求时延、错误和 token |
| submit worker / P4 | 串行代提交、自动合并、未知结果对账、作者署名恢复 | P4 是否真实提交及最终 CL |
| 飞书 | 评审、风险、失败、评论和提交通知 | 辅助通知；失败不改变业务状态 |

前端页面由 Web 服务提供，Flask API 当前挂载在 `/ai_review/...`。不要把旧文档中的 `/api/ai_review/...` 当作现行路由；执行前仍以目标服务的 Swagger 为准。

## 2. 稳定身份与易错身份

### 2.1 Review ID

`AIReview.id` 是业务记录的稳定身份。reopen/refresh 复用同一 Review；它应是跨轮次、未来会话绑定和活动审计的主锚点。

### 2.2 CL

- 创建时 `review.cl` 指向 shelved CL。
- `p4 submit -e` 可能把 CL rename 成新号；成功后 `review.cl` 更新为实际 submitted CL。
- 因此原 CL、当前 CL、提交后 CL 必须分栏记录，不能用 CL 号替代 Review ID。
- `ai_reviews.cl` 有唯一约束，同一 CL 全库只对应一条 Review；rejected/archived 走 reopen，不新建重复行。

### 2.3 TeamCity build

一次 Flow 会创建多个 build：

```text
Flow composite
  └─ TaskAiReview
      └─ TaskBuildUEWindows
          └─ TaskUnshelve
              └─ TaskSyncCyanCookDepot
```

依赖声明方向与执行方向相反。用户给出的 Flow build URL、Task build URL和 Review URL不能直接互推；必须从 snapshot dependencies 和 Task build 的 callback 参数建立映射。

### 2.4 callback 代际

`env.AI_REVIEW_CALLBACK_URL` 带 `review_id` 和一轮 callback nonce。后端只接受当前代际；refresh、reopen、chain retry 会轮换或废弃旧 nonce。报告时只展示 `review_id`，token/nonce 必须隐藏。

### 2.5 Agent 与 workspace

整条链通过 `runOnSameAgent=true` 落在同一 WinBuilder；P4 client/workspace 通常由 `<agent>_<stream>` 派生。不同机器可并行，同一机器的 Flow/Task 仍是多个独立 TeamCity build。

## 3. 端到端主流程

### 阶段 A：作者发起

1. P4V 调用 `RequestReview.py`。
2. 强制刷新 shelf，使 server 上 shelf 与本地预期内容一致。
3. 记录文件与校验信息；释放需要交接的 opened 状态和 `+l` 锁。
4. 打开 `/dashboard/ai-review/request?cl=<CL>`。
5. 本地 watcher 后台观察 Review 终态，用于提交成功后的 sync/resolve 或 rejected 后的恢复。

Shelve 是业务边界：服务端无法凭空取得作者 client 中尚未上传的内容。任何 destructive revert 都必须发生在 shelf 成功并可复核之后。

### 阶段 B：预检与创建

`GET /ai_review/request/preflight?cl=` 返回 CL 元数据、现有 Review、branch 默认 reviewer、提交规则预检、strict/jury、force_ai、是否含可编译代码及 branch review 开关。

`POST /ai_review/request`：

- 要求 shelf 存在；
- 强制执行 submit validation；
- 创建/重开 Review；
- 同步拉首屏文件清单和 diff；
- 写参与者和活动；
- 创建 `AIReviewJob` 并用 one-shot kick 尽快推进；
- 发相应通知。

已有 rejected/archived 记录时走 reopen；进行中重复请求被拒绝。

### 阶段 C：AI/TeamCity 流水线

AI job 的持久 stage：

```text
load_diff → trigger_compile → tc_inflight → await_compile → analyze
```

- `load_diff`：构建文本 diff/文件元数据。
- `trigger_compile`：除纯二进制跳链和 submitted 历史单外，触发 `PLN_FlowAiReview`；`need_compile` 只控制 BuildUE 是否实际执行。
- `tc_inflight`：触发后、关联 build ID 前的防重复 fence。
- `await_compile`：轮询或等待 callback；归因 Sync/Unshelve/Build/AiReview 根失败步骤，并处理 merge gate、瞬时 chain retry。
- `analyze`：没有可信定案 callback 时，使用 backend LLM 静态分析兜底。

当前设计不再用后端 branch busy 门串行 TC 投递；并行度交给 WinBuilder 池和 TeamCity 队列。不要根据旧 `blocked_by` 文档恢复已退役门逻辑。

### 阶段 D：构建机 Pi 评审

1. Sync 到固定基线。
2. Unshelve 后再同步/merge，并产出可审计 `merge_result.json`。
3. 按需 BuildUE、AngelScript 检查和 warning/error 报告。
4. Collect 校验合并证据后生成评审输入。
5. Runner 启动受限 Pi，生成 session、stdout/stderr 和 manifest。
6. Publish 解析 JSON、覆盖不可信元数据、原子写 `result.json` 并回调。
7. Cleanup 始终 revert 该链 workspace。

Pi 进程异常、timeout 或坏 JSON 不应伪造成 approve。Publish 合成 `verdict=error`，构建仍可能绿色收口。

### 阶段 E：callback 与 fallback 合并

定案 verdict：`approve | reject | needs_discussion`。

- 清理本轮旧 AI 产物；
- 写 findings 与 AI task comments；
- 写 summary/risk/source/verdict；
- 更新 `__ai__` participant；
- 记活动和通知；
- callback 优先于 backend LLM；并发写前再次检查当前代际。

非定案 verdict：`error | skipped`。

- 只记留痕，不把 Review 当成功；
- job 继续走 backend LLM fallback；
- 如果 fallback 也失败，按 AI job 重试预算和失败通知处理。

callback 可提前收敛编译成功侧；失败侧仍由 worker 根据完整 chain 归因，避免把 AiReview 尾部失败误标成编译失败。

### 阶段 F：人工/系统决策

- 指定 reviewer 时，普通决策只允许指定人；open flow 可在首次决策时登记 reviewer。
- 任一有效 reject 使 Review rejected；任一有效 approve 使 Review approved，不做多数票计数。
- approve 受编译、AI、strict jury、自批风险等门限制；reject 不受完成门限制。
- AI participant 仅记录模型结论，不等同于人工票。
- 低风险、无指定 reviewer、非 strict 等条件满足时，系统可自动 approve。
- branch review 关闭且非 strict 时，可走受控 direct pass；提交规则预检仍保留。

完整规则见 [decision-submit-notification](decision-submit-notification.md)。

### 阶段 G：代提交与收口

`approved + shelved` 只负责入 `AIReviewSubmitJob`，HTTP 决策线程不直接执行 P4：

1. submit worker 按 workspace/domain 串行 claim；不同 domain 可并行。
2. 首选 `p4 submit -e`；out-of-date/open-files 可转受控 auto-merge。
3. 结果明确成功：先把 DB 收敛为 submitted，再软性恢复作者署名和通知。
4. 确定性冲突可 rejected；结果未知进入 manual_required，禁止猜 CL。
5. 进程中断由 stale recovery 和只读 sweep 对账；一旦已有失败记录，不自动无限重试。
6. RequestReview watcher 根据 submitted/rejected 关闭作者本地工作流。

P4 与 DB 不在一个事务里，所以“P4 已提交、DB 还没记”是必须设计对账的合法中间态；不能看到旧 CL missing 就直接判断失败。

## 4. 状态机摘要

### Review

```text
pending/reviewing → approved → submitted
pending/reviewing/approved → rejected
rejected/archived → reopen → pending/reviewing
submitted/rejected/archived = frozen（approved 仍允许 reject-only 收敛）
```

### AI status

```text
pending → running → done
                  ↘ failed
```

`done` 表示当前业务轮拿到合法 AI 结果，不由 TC SUCCESS、risk=0 或 pi exit=0 单独证明。

### Compile status

编译是否“必需”由 shelved 状态和 request option共同决定。`need_compile=0` 可使 BuildUE skipped，但 Sync/Unshelve/Pi 仍可能运行；chain 前置失败与“没有要求编译”必须分开表达。

### Submit job

```text
queued → running → done
                ↘ failed
                ↘ manual
stale running → 对账 → done / queued / manual
```

普通提交失败后 Review通常保持 approved，等待人工 retry/reject；不要套用 AI job 的五次重试语义。

## 5. Source of truth

处理任何“现在是否已上线/当前默认是什么”问题时按以下顺序确认：

1. 生产 API/DB/activity、TeamCity build/startProperties、构建机 artifact/log；
2. 生产部署 revision 和 P4 have/head；
3. 当前源码、`backend/server/applications/ai_review/SKILL.md` 及其 references；
4. 本 skill 的稳定机制摘要；
5. plans、个人记忆、带日期事故文档只能用于提出假设。

发现文档与源码冲突时，报告冲突并以源码+运行时为准，不在排障过程中顺手“修文档即修系统”。
