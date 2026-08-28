# Windows 细节

## 应用数据目录

`%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\`（即 `C:\Users\<用户名>\AppData\Roaming\...`）

| 文件/目录 | 作用 |
|---|---|
| `profiles\<id>.yaml` | 订阅 profile。**订阅更新会覆盖**，临时改动先备份 `.bak`，长期方案用 Merge |
| `profiles.yaml` | profile 列表 + 各分组选择缓存（UI 上选的节点持久化在这里） |
| `verge.yaml` | Verge 设置：端口覆盖、TUN（`enable_tun_mode`）、系统代理开关。端口以这里为准 |
| `clash-verge.yaml` | **合并后的运行时配置，核心实际加载它**，排查看这份 |
| `logs\` | 核心日志 |

## 端口

- mixed 默认 **7897**（profile yaml 里写的 7890/7893 会被 Verge 覆盖，属正常）
- 查监听与进程：

```bash
netstat -ano | findstr LISTENING | findstr ":7897"
powershell -Command "Get-Process -Id <PID> | Select-Object Id,ProcessName"   # 核心进程名 verge-mihomo
```

## 控制 API：命名管道

Windows 下 Verge 通常关闭 TCP external-controller（运行时配置里 `external-controller: ''`），走命名管道 **`\\.\pipe\verge-mihomo`**。以 `clash-verge.yaml` 里的 `external-controller*` / `secret` 字段为准。

curl 连不上这个管道（会报 Connection refused），用 PowerShell 的 `NamedPipeClientStream`。**直接用封装好的脚本 [../scripts/mihomo-pipe-api.ps1](../scripts/mihomo-pipe-api.ps1)**：

**Git Bash 调用时的坑**：MSYS 会把 `/xxx` 形式的参数转换成一个不存在的盘符路径（如 `/version` → `C:/Program Files/Git/version`），导致 API 返回 400。两种解法任选：

```powershell
# 方法1：路径用双斜杠
powershell -ExecutionPolicy Bypass -File scripts/mihomo-pipe-api.ps1 -ApiPath "//version"
powershell -ExecutionPolicy Bypass -File scripts/mihomo-pipe-api.ps1 -ApiPath "//proxies/OpenAI"
powershell -ExecutionPolicy Bypass -File scripts/mihomo-pipe-api.ps1 -ApiPath "//proxies/OpenAI" -Method PUT -Body '{"name":"<节点名>"}'

# 方法2：禁用参数路径转换
MSYS2_ARG_CONV_EXCL='*' powershell -ExecutionPolicy Bypass -File scripts/mihomo-pipe-api.ps1 -ApiPath "/version"
```

在 PowerShell/CMD 里直接调用则无此问题，用单斜杠即可。

脚本要点（改写时注意）：
- 管道响应是 chunked 编码，JSON 前要剥掉尺寸行（脚本已处理）
- **不要设置 ReadTimeout**——该流不支持，会抛异常（不影响读数据但刷错误信息）
- 中文分组/节点名要 URL 编码，如 `代理` → `%E4%BB%A3%E7%90%86`

## 排查命令速查

```bash
# 通过代理测试（对照组思路：目标域名 vs google/baidu）
curl -x http://127.0.0.1:7897 -s -o NUL -w "%{http_code} %{time_total}s" --connect-timeout 12 https://<目标域名>

# 看出口 IP 与 ASN（判断是否数据中心 IP）
curl -x http://127.0.0.1:7897 -s http://ipinfo.io/json

# 详细握手过程（区分 CONNECT 失败 vs TLS 挂起）
curl -x http://127.0.0.1:7897 -v -o NUL --connect-timeout 12 https://<目标域名>

# 内网网段是否被 TUN 劫持（TUN 路由 metric 0 会赢过物理路由）
route print -4 | findstr "<网段前緺>"

# 本机有哪些网卡/地址（确认内网段是不是本机直连）
powershell -Command "Get-NetIPAddress -AddressFamily IPv4 | Format-Table IPAddress, InterfaceAlias"
```

## 配置持久化：全局 Merge.yaml

应用数据目录下 `profiles\Merge.yaml` 是「全局扩展配置」，对所有 profile 生效、订阅更新不丢。加任意顶层字段（如 `tun:`）会合入最终配置。改完后：

1. 同步改一份到运行时 `clash-verge.yaml`（保证立即生效）
2. 调管道 API `POST /restart` 重启核心（TUN 改动热重载不重建路由表）

实测过的全局 TUN 排除内网段配置（写在 Merge.yaml）：

```yaml
tun:
  enable: true
  stack: gvisor
  auto-route: true
  strict-route: false
  auto-detect-interface: true
  route-exclude-address:
    - <内网段/24>
  dns-hijack:
    - any:53
```
