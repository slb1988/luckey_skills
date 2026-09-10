# AI Review 实施、测试与发布

## 1. 开工前冻结事实

任何改动先记录：

- 目标 Review/build/CL 和问题复现证据；
- 生产部署 revision、TeamCity versioned settings revision；
- 两个 P4 workspace 的 have/head/opened/pending shelves；
- 当前模块 SKILL与源码冲突；
- 哪些计划已实施、哪些只是 proposal；
- 哪些文件正被并行任务占用。

历史 plan、memory、事故 CL只能帮助定位，不是授权或部署状态。发现当前源码已经修复时，转为验证，不重复改一版。

若生成正式实施计划，保存到控制仓库 `.claude/plans/<功能描述>.md`，写清两个 depot、运行时和授权关卡。

## 2. 变更按所有权拆分

### `ws:autoserver-deveops`

- backend：model/api/service/ai_worker/submit_worker/P4 adapter/notification；
- frontend：AI Review页面与API client；
- TeamCity DSL：Flow/Sync/Unshelve/Build/Review；
- DevOps：RequestReview/P4 helpers/informer；
- migration与上述测试。

### `ws:maindev`

- `Tools/AiReview/**`；
- `pl-review`及模块规则；
- Memory CI bundle；
- MainDev工具测试。

### 运行时 machines

- `@auto-server`：部署、migration、服务重启、生产只读验证；
- `@winbuilder...`：逐机准入、实际 TC headless验证、机器配置变更。

跨仓协议变更要在同一计划中列清字段与版本，但两个 P4 depot各建专用 CL；不要把一个仓的 pending内容复制进另一个仓。

## 3. P4 纪律

### DevOps depot

- `192.168.2.13:1666` 是 Unicode；CLI使用 `p4 -C utf8`；
- 本次文件全部 `p4 reopen -c <专用CL>`；
- 描述遵循该 depot惯例，可中文；
- `p4 describe -s` 与 `p4 opened` 收尾核实；
- 不把无关 default/他人 CL文件卷入。

### MainDev depot

- `192.168.2.236:1666` 是非 Unicode；不要设置 utf8 charset；
- 描述使用英文；
- 修改后同样建独立 CL并核 opened/describe；
- 不用 git branch/worktree管理该目录。

用户可能在任务期间手工 submit pending CL。收尾前重新读 `p4 opened`；文件若已关闭而本地又有改动，要重新 `p4 edit`并建新 CL，不能声称旧 CL仍含最新内容。

未经用户明确“提交”授权只保留 pending，不 submit。部署、真实构建、生产DB修改和通知同样需要单独授权。

## 4. 代码设计边界

- 保持 Review/CL/build/callback代际可追踪；新增异步步骤要有持久状态和幂等键。
- 所有 check-then-act 都考虑 MySQL事务隔离和多 worker竞争，优先条件 UPDATE/CAS/row lock。
- P4与DB跨事务，结果未知必须进入可对账状态，不能猜成功或失败。
- 失败路径不能合成 approve/risk0；旧有效报告可显示，但本轮必须标失败。
- callback/body中的身份和模型元数据不可信，服务端/Runner强制覆盖并交叉校验。
- prompt“只读”不是权限边界；限制工具、canonical path、扩展、运行账号和目标 agent。
- 代码注释只保留非显而易见的外部约束/why；流程和排障写 reference，不在代码堆事故史。
- 新旧协议切换要能识别版本，旧 callback不能默认冒充新轮。

## 5. 测试分层

### 5.1 后端定向单测

根据改动选择：

| 改动 | 至少覆盖 |
|---|---|
| 创建/预检 | request API、submit validation、force/branch closed、重复/reopen |
| 状态机/决策 | approve gate、author、designated reviewer、jury、auto approve、terminal freeze |
| AI worker | kick、claim、stage、retry、tc_inflight、callback race、chain failure/skip |
| merge | merge gate、baseline、conflict、transient retry、实际失败节点 |
| submit | queue CAS、domain串行、跨域并行、fail closed、unknown、stale recovery、auto-merge |
| P4 | isolated p4d、shelved-only、base rev、CL rename、stream mapping |
| notification | 收件人、去重、失败log-only、真实error摘要 |
| API/UI投影 | ai_summary、submit_progress、activities、状态标签 |

从 `pyAutomation/backend` 的项目虚拟环境运行定向 pytest；确认测试配置指向隔离 DB/P4/HTTP。再按风险运行完整 `tests/unit/ai_review/` 与相关 trigger/client tests。

### 5.2 MainDev 工具测试

```text
cd <MainDev-root>
python -m unittest discover -s Tools/AiReview/tests -v
```

应覆盖：

- merged diff与evidence schema；
- mixed stream analyzed/skipped；
- Collect输出和exit；
- build-log tail与warning report provenance；
- report source==destination；
- fake Pi argv、Unicode路径、`.cmd`、timeout和process tree；
- turn guard；
- fake Memory成功/timeout/401/redirect/proxy；
- Publish JSON/metadata/error/callback；
- 无凭证泄漏。

fake Pi/Hub测试只证明本地逻辑，不证明真实模型、网络或构建机。

### 5.3 TeamCity DSL

验证：

- 结构/生成成功；
- 每条 snapshot边 same-agent；
- global buildType ID与依赖方向；
- Flow参数覆盖所有消费者；
- Windows Agent requirements；
- `AI_REVIEW_MODE`、Runner/Python UTF-8、artifactRules；
- Build失败仍运行Review；
- Cleanup ALWAYS；
- callback/log中敏感字段遮蔽。

如果本机缺匹配JDK/TeamCity版本，明确“静态检查通过、真实DSL生成未验证”，不要降低插件或改生产配置来迁就本机。

### 5.4 前端

至少验证：

- Review状态、compile/AI/submit progress投影；
- designated/jury/self/terminal按钮；
- Markdown与链接安全；
- activities分页；
- failed/manual_required文案不误称submitted；
- Review/Flow/Task链接不混淆。

### 5.5 隔离集成探针

优先使用 loopback fake服务、临时目录和隔离 p4d。探针保留真实参数解析、状态机或P4语义，只隔离业务副作用：

```text
基线复现 → 受控对比 → 最小修复 → 同探针回归 → 真实关键阶段验证
```

禁止探针：真实 Review callback、真实 submit、飞书群通知、在生产 TC workspace unshelve/revert、把用户 CL当测试夹具反复运行。

## 6. 构建机逐机准入

每台候选 WinBuilder都单独检查：

1. TC agent name、host、服务账号、agent home；
2. `NODE_WORKSPACE`、P4 client、Root/stream/owner；
3. Tools/AiReview have/head与trusted guard；
4. Python/P4/P4Python/requests/Node/Pi真实解析路径和版本；
5. Runner的 `--`、extensions、turn guard和process tree；
6. 模型 provider/model/base host与一次受控延迟，不输出key；
7. Memory no-proxy/no-redirect/search-v2/credential source；
8. effective `AI_REVIEW_MODE`、model、thinking、need_compile；
9. artifact provenance与TC日志；
10. A2A若启用，还要验证headless凭证、只读allowlist、远端生命周期。

一台通过不代表所有 WinBuilder可用。普通用户登录shell成功也不代表TC服务账号环境成功。

## 7. 真实链验收

得到明确授权后，按风险递进：

1. echo-only参数/Root探针；
2. 非默认stream + 测试CL的Sync/Unshelve；
3. merge_result和baseline；
4. `need_compile=0`链，确认仍有Pi；
5. 编译/AS/error/warning样本；
6. Pi真实模型、Memory、合法 result/callback；
7. backend callback/fallback竞争；
8. reviewer gate；
9. 沙盒submit queue与P4收口；
10. 生产小范围灰度。

每层报告实际 Agent、Root、CL、revision与artifact。匹配成功不等于Sync成功，TC SUCCESS不等于Review完成，approve不等于submitted。

## 8. 部署

### auto-server

- 后端/前端使用对应 deploy skill和目标仓库部署脚本；
- schema变更先读 migration reference，部署前跑migration并验证head；
- 不用过期 `start.sh` 或不可靠PID文件判断进程；
- 部署前核 submit queue/running job，避免在P4成功到DB收敛窗口强杀；
- 重启后验证 scheduler tasks、Swagger、health、DB schema、日志和一个只读详情。

### TeamCity

- versioned settings从P4进入；
- 记录配置revision与服务器应用状态；
- UI参数可用于紧急 mode切换，但要明确可能被VCS覆盖；
- 不取消/重建业务链而不更新Review关联。

### MainDev工具

工具随游戏stream sync到构建机。新stream首次运行前确认目标stream含工具revision；不要在builder上直接改生产文件。逐机只做环境和同步验证。

## 9. 回滚

每次改动提前定义：

- 源码 CL revert；
- DB migration是否可向后兼容/如何downgrade；
- TeamCity配置revision和mode；
- 在途callback/job/submit的代际处置；
- 已经P4提交的内容不能靠DB回滚撤销；
- embedded/泄露credential涉及轮换，不是删代码即可。

回滚也要保持fail-closed：不能为了快速恢复把 timeout/error映射成 approve。

## 10. 文档与交付

更新最窄权威文档：

- backend语义 → 模块 `SKILL.md` / references；
- TeamCity语义 → `Teamcity_PLN/SKILL.md` 或本 skill TeamCity reference；
- MainDev脚本 → `Tools/AiReview/README.md` / 本 skill toolchain reference；
- 跨系统稳定机制 → 本 `pyauto-aireview`；
- 一次性事故/个人环境 → 个人memory，不污染共享skill。

交付至少包含：文件、测试、两个workspace的pending CL、部署/未部署、真实验证/未验证、风险和回滚。用户没有明确要求review时不主动跑代码评审流程。
