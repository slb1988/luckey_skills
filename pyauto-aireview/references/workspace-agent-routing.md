# `ws:` 与 `@agent` 路由

## 1. 两种地址不是一回事

| 语法 | 表示 | 用途 |
|---|---|---|
| `ws:<name>` | 已注册项目 workspace，携带源码、VCS、skills和项目记忆 | 分析/修改/测试代码，创建 P4 CL |
| `@<agent-name>` | A2A 平台上的具体机器/运行时 agent | 读生产日志、DB、进程、机器配置、实际 artifact，或经授权执行机器动作 |

禁止把 `@agent` 当 workspace，也禁止把 `ws:` 当远程 agent。跨系统任务通常是：先由 owning workspace读源码确定要验证的变量，再让具体机器 agent补运行时证据。

## 2. AI Review 的 workspace

### `ws:autoserver-deveops`

注册工作区：`admin_sun_depot_7184`，本机路径通常为 `D:\work\admin_sun_depot_7184`。

负责：

- `pyAutomation/backend/server/applications/ai_review/`；
- pyAutomation AI Review 前端；
- `Teamcity_PLN/.teamcity/patches/buildTypes/`；
- `DevOps/RequestReview.py`、Setup/分发；
- `P4UnshelveStage.py`、Sync helper；
- `TeamCityLogParserInformer.py`；
- backend/frontend/DSL/RequestReview tests。

这是 `//depot/` 的 P4 workspace，目标服务器为 Unicode；命令行要按该项目规则使用 `p4 -C utf8`。修改后建立独立中文描述 pending CL，不把文件留在 default CL。

适用请求：

- API/DB模型/state machine；
- AI/submit worker；
- callback/fallback；
- TeamCity DSL/参数/通知；
- RequestReview 客户端；
- dashboard UI；
- migration、测试和服务部署代码。

### `ws:maindev`

注册工作区：`MainDev`，本机路径通常为 `D:\MainDev`。

负责：

- `Tools/AiReview/**`；
- `.claude/skills/pl-review/**` 与目录模块规则；
- MainDev 侧 Memory CI bundle和离线测试；
- `SetupP4.bat` / 引擎侧 P4VUtils 接线（若实际文件在该 depot）。

MainDev P4服务器为非 Unicode；不要加 `-C utf8`。修改后建立英文描述的专用 pending CL。不要用 git分支/worktree管理这个 P4 workspace。

适用请求：

- diff/merge evidence；
- Collect/Runner/Publish；
- Pi prompt、工具边界、session、Memory；
- warning/compile report接线；
- MainDev 本地模拟和单测。

### 旧 `ws:devops` / `ws:cyancook-devops`

它指向另一份旧 DevOps workspace，不等于 `ws:autoserver-deveops`。用户只说“DevOps”且改动目标不清楚时先确认；AI Review backend/当前 TeamCity DSL 默认按 `ws:autoserver-deveops` 路由。

## 3. AI Review 的 A2A agents

### `@auto-server`

生产服务器证据面，适合：

- Flask部署 revision、`app.log`；
- 生产 MySQL/Redis只读查询；
- APScheduler job/worker状态；
- TeamCity server REST/服务日志；
- build-api-proxy health、request history；
- nginx/frontend部署；
- 经明确授权的部署/重启/迁移验证。

源码修改不在这台机器现场直接改；回到 `ws:autoserver-deveops` 实施，再按 deploy skill发布。

### `@winbuilder4_maindev`

已知用于 WinBuilder4 现场。适合：

- 实际 TC agent用户与 agent home；
- `D:\WinBuilder4_MainDev` 等真实 workspace/client Root；
- Pi/Node/Python/P4/P4Python版本；
- `D:\Teamcity-BuildAgent\logs\...`；
- 本轮 `Saved/ai_review`、进程、网络和模型配置；
- 受控只读 smoke。

路径和账号仍要现场发现，不能把历史值当永久配置。

### 其他 WinBuilder agents

已出现的命名可能混用连字符/下划线，例如 `@winbuilder3-maindev` 与 `@winbuilder4_maindev`。`@winbuilder*_maindev` 只是文档模式，不是可派发的通配 agent；调用前从 A2A mention补全取得精确名字。

WinBuilder3 的 A2A workroot曾与 TeamCity engine root不同，说明“连上某机器”不等于“当前 cwd就是生产 TC workspace”。每次记录：agent name、host、服务账号、A2A workroot、TC root、P4 client、当前 build占用。

没有注册 WinBuilder1 agent时，不要杜撰 `@winbuilder1...`。可由 `@auto-server`/TeamCity artifact先完成诊断，或请用户选择可用机器入口。

## 4. 路由决策表

| 问题 | 首选 | 条件补证 |
|---|---|---|
| Review状态、worker为什么不动 | `ws:autoserver-deveops` 理解代码 | `@auto-server` 查DB/log/runtime |
| Dashboard/接口500 | `@auto-server` 取异常与migration状态 | `ws:autoserver-deveops` 修源码 |
| TeamCity build慢/错Agent | TeamCity REST + `teamcity-tool` | 实际 `@winbuilder...` 查本机环境 |
| Collect/Runner/Publish bug | `ws:maindev` | 对应 builder核真实artifact |
| warning缺失 | DevOps DSL/informer + MainDev Collect两端 | builder provenance与本地报告 |
| Pi版本/argv/provider问题 | 先看build artifact | `@winbuilder...` 在TC账号下核版本/config |
| callback/fallback慢 | `ws:autoserver-deveops` 梳调用链 | `@auto-server` 查proxy/backend history |
| submit卡住/CL missing | `@auto-server` 只读DB+P4事实 | `ws:autoserver-deveops` 修worker/P4 adapter |
| 需要改两仓协议 | 两个 workspace各一 worker/CL | 机器只做最终受控验收 |

## 5. 派发原则

### 5.1 给 workspace worker

发送：

- 目标、边界、已确认 Review/build/CL映射；
- 需要核对的源码/测试/部署状态；
- 明确 current vs pending vs historical；
- P4不提交/不部署边界；
- 验收和报告字段。

让目标 worker在项目根使用它自己的 skills和记忆，不要先把另一仓源码树加载到协调会话再复制给它。

### 5.2 给 A2A machine agent

发送：

- 精确时间窗、build/review/agent；
- 只读命令范围；
- 具体路径/进程/字段；
- 脱敏要求；
- 哪个结论需要它证实或排除；
- 不修改、不重启、不sync/unshelve/触发build，除非用户明确授权。

示例骨架：

```text
只读核实 build <id>。请报告 TC服务账号下 pi版本、agent日志时间窗、
本轮 runner_manifest/session错误摘要、目标服务连通与callback耗时。
不要输出token/key/完整URL，不要升级、重跑、sync或修改配置。
```

## 6. A2A 生命周期

- 派发成功后，远端任务独立于本地 Pi进程继续运行；本地等待中断不等于远端失败。
- 保存 dispatch/task ID，先查询原任务状态，绝不因“没收到结果”立即重复派发。
- 观察端等待长不应自动 cancel；平台硬 timeout可能杀远端进程树，长部署/测试要分阶段。
- 远端发现致命中断时应回报具体步骤、错误和建议，等待用户决定，不擅自扩大范围。
- 远端可能处于生产/TC workspace；任何 sync、revert、unshelve、build、config或service动作都要检查当前占用并取得授权。

## 7. Source 与 runtime 合并

跨系统结论要显式区分：

```text
源码：当前 head 的逻辑会怎样
部署：生产实际运行哪个 revision/config
现场：这一 build/Review 实际发生了什么
```

典型安全顺序：

1. API/REST/artifact先建立事实；
2. owning `ws:` worker解释代码路径；
3. 只在剩余归因需要时派精确 `@agent`；
4. 修改回 owning workspace；
5. 隔离测试；
6. 经授权部署；
7. 再由 runtime agent验证线上。

不要把远端 agent的业务skills、探索历史或整个文件内容搬回协调会话；收集结论与可复核证据摘要即可。

## 8. 凭证与敏感信息

所有路由共同遵守：

- 不回显 TeamCity bearer、callback token/nonce、P4 password、LLM key、Memory/A2A token；
- callback URL只报告 host/path/review_id；
- config只报告字段名、是否配置、来源和非敏感host/port；
- 不枚举整个 environment或home credential文件；
- artifact含diff/session/Memory时只取必要摘要，不通过公开链接分享；
- 发现源码硬编码 credential时报告位置与风险，不复制值；修复同时规划轮换。
