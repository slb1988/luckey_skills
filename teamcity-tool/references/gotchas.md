# TeamCity 非 obvious 行为与配置陷阱

本文件记录 TeamCity 在 REST API、参数传递、Perforce VCS root、checkout 模式、Kotlin DSL 等方面的非显而易见的行为。读到这些条目时应该主动在相关配置中检查。

## 参数解析：排队时解析 vs 运行时解析

| 参数 | 解析时机 | 在 pipeline 上是否可用 |
|---|---|---|
| `%teamcity.agent.name%` | build 实际分配到 agent 后 | **不可用**。pipeline 在排队时还没有 agent，会解析为空字符串 |
| `%PARAM%`（自定义参数） | 排队时 | 只有当该参数在当前 build 配置自身、父项目或上游 `reverse.dep.*` 注入后可用 |

**结论：** `reverse.dep.*.PARAM` 永远不要用 `%teamcity.agent.name%`；用它传递字面量或已解析的自定义参数。

## `reverse.dep.*` 参数的作用域

`reverse.dep.*.PARAM_NAME` 在 parent/pipeline 上定义，会把 `PARAM_NAME` 的值注入到所有下游 build。但它不会把参数名本身“定义”到下游——如果下游本来没有这个参数，`%PARAM_NAME%` 引用会保持为字面字符串。

正确模式：
```
Pipeline 参数：
  DefaultAgent = DefaultAgent
  reverse.dep.*.DefaultAgent = DefaultAgent   ← 字面量

Downstream 参数：
  DefaultAgent = DefaultAgent   ← 自己也要定义，供 agent requirement 使用

Agent requirement：
  teamcity.agent.name == %DefaultAgent%
```

## 入队后的 build 携带参数快照

build 入队时会快照当前参数值。之后修改 build config 的参数不会影响已经排队的 build。修复参数后必须取消并重新触发 chain。

## Perforce VCS root：`client-mapping` 覆盖 stream view

在 `use-client: stream` 模式下，TeamCity 默认让 Perforce 服务器根据 stream 定义生成 workspace view。如果 VCS root 上存在 `client-mapping` 属性（即使是空字符串），它会**替换** stream 自动生成的 view，导致 sync 映射错误路径、checkout 目录为空。

**检查命令：** REST API GET `/app/rest/vcs-roots/id:<ID>?fields=properties(property)`，确认没有 `client-mapping`。

## Perforce workspace option：`rmdir` 会删除 checkout 目录

`workspace-options` 里如果包含 `rmdir`，Perforce 会在 sync 后删除空目录。在 TeamCity 的 agent checkout 流程中，这通常表现为：**build 执行期间文件存在，build 结束后整个 checkout 目录被清空**。

应使用 `normdir`（Perforce 默认行为，不删除目录）。

## 共享 checkout 目录的三个必要条件

当 chain 中一个 build sync 代码、下游 build 读取代码时：

1. **相同的 `checkoutDirectory`**（例如 `/mnt/disk2/TeamCity/buildAgent/work/%teamcity.agent.name%_%P4Stream%`）
2. **snapshot dependency 设置 `run-build-on-the-same-agent = true`**
3. **下游 build 移除自己的 VCS root，并把 `checkoutMode` 设为 `MANUAL`**

如果下游仍保留 `ON_AGENT` 且没有 VCS root，TeamCity 仍会在 build 开始时清理 checkout 目录，导致上游 sync 的内容丢失。

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

通过 REST API 修改配置后，如果 versioned settings 已启用，TeamCity 可能不会立即重新加载 VCS 中的最新 DSL。必要时需在 UI 手动点击 **"Load project settings from VCS"** 强制刷新。

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
