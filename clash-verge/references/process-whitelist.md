# 进程白名单：PROCESS-NAME → DIRECT 标准流程

给某个进程的所有流量开直连（绕过代理）的完整落地流程。域名级直连同理（DOMAIN-SUFFIX），只改第 2 步的规则形态。

## 生效层级（先建立认知）

- **两个源文件保持同步**：全局 `profiles/Merge.yaml`（`prepend-rules`）+ 全局 `profiles/Script.js`（`main()` 里向 `config.rules` 前置注入）。只改一边会在 profile 切换后出现行为不一致。
- **活动 profile 是 local 单节点配置（`MATCH,PROXY` 兜底）时，`prepend-rules` 在运行时配置里是惰性顶层 key，不进核心规则表——Script.js 是唯一实际注入层**。订阅 profile 下两者都被处理。
- service 模式下核心实际加载 ProgramData 的 `runtime\config.yaml`，不是 `%APPDATA%` 那份——详见 [windows.md](windows.md)「Service 模式」节。

## 步骤

1. **拿真实进程名**（含准确大小写，进程名未必是小写）：
   ```bash
   powershell -Command "Get-Process | Where-Object { \$_.ProcessName -match '<关键词>' } | Select-Object -Unique ProcessName, Path"
   ```
   安装目录下的兄弟进程（守护/更新/会议 SDK 等独立 exe）是各自的 PROCESS-NAME，需要就分别加，一条规则盖不住。

2. **改源文件**（改前先备份 `.bak-<用途>-<时间戳>`）：
   - `Merge.yaml` 的 `prepend-rules` 加 `- PROCESS-NAME,<Name>.exe,DIRECT`，放进现有 PROCESS-NAME 组里
   - `Script.js` 的 `directProcesses` 数组加 `"<Name>.exe"`

3. **同步进运行时配置** `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\clash-verge.yaml`，注意有**两处**：顶层 `prepend-rules` 副本（惰性，为一致性同步）+ 实际 `rules:` 列表（前置到规则最前）。

4. **service 模式提权覆盖**：用 `Start-Process powershell -Verb RunAs`（弹一次 UAC）把改好的运行时配置拷贝覆盖到 `C:\ProgramData\clash-verge-service\users\<哈希>\runtime\config.yaml`（原文件留 `.bak`）。非 service 模式跳过此步。

5. **热重载**：`PUT /configs?force=true`，body `{"path":""}`。纯规则改动**不需要** `POST /restart`（restart 只在 TUN 路由变更后必须）。

## 验证（不看配置文件，看核心状态）

1. `GET /rules` — 新规则应出现在规则表最前段（prepend 位置），确认 `proxy` 是 `DIRECT`。
2. `GET /connections` 按 `metadata.processPath` 过滤目标进程——**只有变更后新建的连接才会命中新规则**；规则匹配发生在连接建立时，老长连接带着旧匹配结果存活。
3. 老连接不必强求立刻杀死：部分 TUN 长连接 `DELETE /connections/{id}` 返回 400 关不掉，等自然断开即可，不影响「规则已生效」的判定。
