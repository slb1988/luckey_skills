# Windows：给指定应用开直连白名单

**适用模式：Rule（规则）。** `PROCESS-NAME,<文件名>,DIRECT` 让 mihomo 直接连目标，不经过代理节点；连接仍可能显示从 TUN 或系统代理进入，这是正常的。Global 模式不执行这条规则。

## 1. 找到真正建立连接的 `.exe`

在 Verge「连接」里找到目标请求，看进程名或进程路径的最后一段；也可以在任务管理器「详细信息 → 名称」核对。要查正在运行的程序，可在 PowerShell 执行：

```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE '%hearthstone%'" | Select-Object Name, ExecutablePath -Unique
```

**填文件名，不填软件显示名。** 保留 `.exe`、点号和连字符：`Hearthstone` 不是 `Hearthstone.exe`，`battlenet.exe` 也不是 `Battle.net.exe`。以下是已核对的 Windows 主程序名；其他版本以实际连接为准。

| 应用 | `PROCESS-NAME` 填什么 |
|---|---|
| 飞书 | `Feishu.exe` |
| Perforce P4V | `p4v.exe` |
| UE Launcher | `ue-launcher.exe` |
| Visual Studio | `devenv.exe` |
| JetBrains Rider | `rider64.exe` |
| JetBrains PyCharm | `pycharm64.exe` |
| Visual Studio Code | `Code.exe` |
| 炉石传说 | `Hearthstone.exe` |
| 暴雪战网 | `Battle.net.exe` |

规则跟着**发起连接的进程**，不按父子关系继承。比如 UE Launcher 的 `msedgewebview2.exe`、VS Code 启动的 `codex.exe`、飞书的 `ttdaemon.exe` 或会议进程 `video_conference_sdk.exe`，都不是主进程。不要为了单个应用把共享的 WebView2、Node、Java 等运行时全局直连。

## 2. 在两处各加一条，保留原有列表

用 `Win+R` 打开 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\profiles`，或在 Verge 的订阅页编辑**全局** Merge 和 Script。先备份要改的文件。以 VS Code 为例，已有的条目不用重复加：

| 文件 | 编辑位置 | 只追加这一项 |
|---|---|---|
| `Merge.yaml` | 现有 `prepend-rules:` 列表，和其他 `-` 对齐 | `- PROCESS-NAME,Code.exe,DIRECT` |
| `Script.js` | `main()` 内的 `directProcesses` 数组 | `"Code.exe",` |

`directProcesses` 是这份脚本的数组，不是 mihomo 配置字段。脚本会把数组项转为 `PROCESS-NAME` 规则，放在 `MATCH,PROXY` 之前。如果是没有该数组的自定义脚本，可以在 `return config` 前写 `config.rules = ["PROCESS-NAME,Code.exe,DIRECT", ...(config.rules || [])];`，不要再加一遍数组项。

**为什么要写两处？** 在这里使用的 Local 单节点配置里，Merge 的 `prepend-rules` 会出现在生成文件的顶层，却不等于进入了核心的 `rules` 表；全局 Script 才把条目插入实际列表。也不要只改订阅 YAML，刷新会覆盖。

如果要放行的是**某个服务而非整个进程**，例如只让多个客户端访问战网国服时直连，可将 `DOMAIN-SUFFIX,battlenet.com.cn,DIRECT` 加到 Merge 的 `prepend-rules` 和 Script 的 `config.rules` 前段，**不要**放进 `directProcesses`。这样不必全局放行通用名称 `Agent.exe`。

## 3. 应用当前配置并验证

保存后，在 Verge 重新应用**当前**配置，让它重新生成并加载规则，不必切换订阅或重启电脑。验证分两层：

| 要确认什么 | 判据 |
|---|---|
| 核心加载了规则 | `GET /configs` 的 `mode` 是 `rule`；`GET /rules` 中对应 `ProcessName` 的 `payload` 是完整文件名，`proxy` 是 `DIRECT`，排在兜底 `Match` 之前。 |
| 应用这次真的直连 | 让应用发起一次新请求，在 Verge「连接」中查看，或查 `GET /connections`：按 `metadata.process` / `metadata.processPath` 核对应用，`start` 晚于重载，`rule=ProcessName`、`rulePayload=Code.exe`（换成目标程序）、`chains=["DIRECT"]`。有双向收发可进一步确认连通。 |

旧连接不会重新匹配，等自然重连即可，不必强断对局或工作会话。没看到新连接，只能确认规则已加载；如果新连接因 `IP-CIDR` 或 `DomainSuffix` 走了 `DIRECT`，它确实直连了，但不能据此说是进程规则命中。

**手工改磁盘时：** 若核心规则表仍是旧的，核对生成的 `clash-verge.yaml` 的 `prepend-rules:` 和实际 `rules:` 两处。Windows 服务模式还要用管理员权限备份当前 `C:\ProgramData\clash-verge-service\users\<当前实例>\runtime\config.yaml`，只同步这次的规则项，保留服务自己的管道和认证设置。然后调 `PUT /configs?force=true`，body 为 `{"path":""}`；它重读运行时文件，不会代替 Verge 执行全局脚本。纯规则改动不需要 `POST /restart`。管道连接方法见 [Windows 参考](windows.md)。

**撤销：** 从两份源文件移除对应项，用同样方法重新应用，核对核心规则表即可。
