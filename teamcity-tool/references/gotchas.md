# TeamCity 非 obvious 行为与配置陷阱

本文件记录 TeamCity 在 REST API、参数传递、Perforce VCS root、checkout 模式、Kotlin DSL 等方面的非显而易见的行为。读到这些条目时应该主动在相关配置中检查。

## Chain 参数、解析上下文与快照

权威参考：[build-chain-parameters.md](build-chain-parameters.md)。相关机制集中维护于该文，避免这里复制出第二套规则：

- `override.dep` 在声明它的配置中尝试解析，仅覆盖接收方已有键；`reverse.dep` 保留表达式且可以创建接收方参数。
- Composite 没有自己的 Agent。Agent 名称策略用字面正则；目标 Agent 路径公式可以用定向 reverse.dep 延迟解析，两者不能混为一谈。
- 项目/模板中的空 env 参数会遮蔽 Agent 值；已入队快照、新配置和实际启动值是三个不同检查对象。
- 重排需保留业务平台的 build ID 关联并重新检查请求状态，不无条件取消旧链或复活终态请求。

## Perforce VCS root：`client-mapping` 覆盖 stream view

在 `use-client: stream` 模式下，TeamCity 默认让 Perforce 服务器根据 stream 定义生成 workspace view。如果 VCS root 上存在 `client-mapping` 属性（即使是空字符串），它会**替换** stream 自动生成的 view，导致 sync 映射错误路径、checkout 目录为空。

**检查命令：** REST API GET `/app/rest/vcs-roots/id:<ID>?fields=properties(property)`，确认没有 `client-mapping`。

## Perforce workspace option：`rmdir` 会删除 checkout 目录

`workspace-options` 里如果包含 `rmdir`，Perforce 会在 sync 后删除空目录。在 TeamCity 的 agent checkout 流程中，这通常表现为：**build 执行期间文件存在，build 结束后整个 checkout 目录被清空**。

应使用 `normdir`（Perforce 默认行为，不删除目录）。

## 同机状态与 checkout 目录

同机 snapshot 边保证 Agent 一致，但还需保证消费者使用同一个真实 engine Root 和分支。
脚本式 Sync 的 DevOps checkout 可以与 engine Root 不同；后续 MANUAL Build/Review 核验的是
engine Root、P4 client spec 与预期路径一致，不是让所有 checkoutDirectory 字符串机械相等。
自动 checkout/目录清理不应覆盖这份共享 UE 状态；详细契约见主参考的“工作区公式”。

## `vcsroot.<ID>.p4client` 参数名与 VCS root ID 强绑定

该参数名中的 `<ID>` 必须是 VCS root 的**实际 ID**。重命名或复制 VCS root（得到新 ID）后，必须同步修改这个参数名。TeamCity 不会自动更新。

## REST API 复制 vs 移动 build config

`POST /app/rest/projects/id:<TARGET>/buildTypes` 配合 `sourceBuildType` 和 `move=true` 实际执行的是**复制**，不是移动。复制后必须手动：
1. 删除源 build config
2. 重新接线 snapshot dependencies 到新 ID
3. 修正 `vcsroot.<ID>.p4client` 等绑定旧 ID 的参数名

## Project ID 前缀约束

启用 Kotlin versioned settings 时，TeamCity 要求所有子 build config ID 和 VCS root ID 的前缀与父 project ID 一致。重命名 project ID 后必须批量重命名子 ID，否则 DSL 加载报错。

## Kotlin DSL patches 模式：UI 与 VCS  coexist

为了避免 UI 改动和 VCS 改动互相覆盖，可以把 buildType 放到 `patches/buildTypes/*.kts`，VCS root 留在 `settings.kts`。TeamCity UI 改动会生成/更新 patch 文件并写回 VCS，不会覆盖 `settings.kts`；VCS 开发者直接编辑 patch 文件即可。

注意：`changeVcsRoot` patch 要求对应的 VCS root 已在 `settings.kts` 中注册，否则 `mvn teamcity-configs:generate` 会报 `Expected VCS root ... not found`。

## TeamCity 状态同步延迟

REST/UI 保存、写回 VCS、服务器应用、某次构建选定 revision 分属不同阶段。
先看项目 `versionedSettings/status` 与实际 build 的 `versionedSettingsRevision`，再决定是否需要加载已确认的 VCS 版本。
`not read only` 或 `generated settings from cache` 仅是设置选择信息，不足以单独证明缓存错误，不能据此清缓存/重启服务器。

## Checkout directory 过期自动清理会整树删除目录（默认 192h）

任何曾被 buildType 登记为 custom checkout directory 的目录都会进入 agent 的 directory map。当属主配置**移除 checkoutDir / 被删除 / 停止在该 agent 运行**后，条目成孤儿；距最后使用超过 `teamcity.agent.checkoutDir.expireHours`（默认 192h）即被 `DirectoryMapDirectoriesCleanerImpl` 整树 `rd /s /q`——agent 日志 "Build directory has expired, unused or free disk space is needed"，**与磁盘余量无关**。

要点：
- 删除发生在 P4 之外 → have-table 完好 → 裸 `p4 sync` 不会自愈，必须 `p4 -c <client> clean <root>\...`
- 删除被进程占用会留 `<dir>\.teamcity.clean.checkout.required` 标记 → 下次强制重清，需手工删标记 + map 陈旧条目
- 防御：`buildAgent.properties` 设 `teamcity.agent.checkoutDir.expireHours=never` 并重启 agent；用 checkoutDir 的配置必须 `requirements` 钉死 agent；游戏工作区路径永不登记为 checkout dir
- agent 自升级会重写 directory map 时间戳 → 升级后一周是高危窗口

2026-08-19 实战事故（E:\WinBuilder3_MainDev 被删、PL_BuildUgsBinaries 三连红、真凶 PLN Task_Sync_CyanCookDepot）完整报告见 [checkout-dir-auto-clean.md](checkout-dir-auto-clean.md)。

## 升级陷阱（2026-08-11 实测 2025.11 → 2026.1.3）

### Java 17 → 21 是硬性要求
新版本要求 Java 21，但启动脚本从 PATH/JAVA_HOME 解析 java，旧环境可能仍是 17。启动/升级后**必须验证实际 JVM**：
```bash
ss -tlnp | grep 8111                    # 拿 java PID
sudo readlink /proc/<PID>/exe           # 必须是 java-21
```
⚠️ `ps aux | grep Bootstrap` 会同时匹配到本机的 **Jira** JVM（Java 17，atlassian-jira，端口 8083），别认错。

### 数据格式升级页不是报错
升级后首次启动会显示 "data directory and database need to be upgraded"，数据格式 1032 → 1039，**不可降级**。这不是故障，但必须先备份再确认（UI 上点确认即可，会自动重启）。

### 升级前的备份是硬性要求
- Web UI 内置备份到 `.BuildServer/backup/TeamCity_Before_Upgrade_*.zip`
- 或 mysqldump（数据库在 docker 容器 `mysql`，13306 → 3306，root 密码在容器环境变量）
- 数据目录 40GB，物理拷贝耗时较长，内置 zip + SQL dump 组合够用

### 升级后 agent 要求
Agent 必须用 Java 21，老 Java 的 agent 能连上但**无法跑新构建**。Windows agent 需单独升级其 JVM。
