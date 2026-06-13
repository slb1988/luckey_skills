# frp 内网穿透搭建记录

> 搭建日期：2026-06-13
> VPS 公网 IP：81.68.211.31
> frp 版本：v0.69.1
> 凭据策略：本文件可提交，真实 token 不写入此文件；本机私有 token 放在 `frp-secrets.local.md`。

## 一、当前状态

| 项目 | 值 |
|---|---|
| 公网 IP | **81.68.211.31** |
| frps 版本 | v0.69.1 |
| 控制端口 | 7000/tcp |
| 业务端口 | 18080-18082/tcp（等 frpc 接入），18083-18089 预留 |
| 防火墙 | ufw 已启用，开放 22/7000/18080-18082 |
| systemd | frps.service active (running) |

## 二、VPS 端配置

### `/etc/frp/frps.toml`

```toml
bindPort = 7000

auth.method = "token"
auth.token = "REPLACE_WITH_FRP_TOKEN"

transport.tls.force = true

allowPorts = [
  { start = 18080, end = 18089 }
]

log.to = "/var/log/frp/frps.log"
log.level = "info"
log.maxDays = 7
```

### 文件清单

| 路径 | 用途 |
|---|---|
| `/opt/frp/frps` | frps 二进制（v0.69.1） |
| `/etc/frp/frps.toml` | frps 配置 |
| `/etc/systemd/system/frps.service` | systemd 服务 |
| `/var/log/frp/frps.log` | 日志 |

## 三、常用命令

```bash
sudo systemctl status frps          # 查看状态
sudo systemctl restart frps         # 重启
sudo systemctl stop frps            # 停止（紧急关闭）
sudo journalctl -u frps -f          # 实时日志
sudo ss -lntp | grep frps           # 监听端口
```

## 四、端口映射总览

| 公网地址 | 映射服务 | frpc 本机端口 |
|---|---|---|
| `81.68.211.31:18080` | agent/harness | 3000 |
| `81.68.211.31:18081` | Jira | Jira 实际端口，默认 8080 |
| `81.68.211.31:18082` | TeamCity | TeamCity 实际端口，默认 8111 |
| `81.68.211.31:18083-18089` | 预留 | - |

## 五、frpc 配置模板

创建 `/etc/frp/frpc.toml`：

```toml
serverAddr = "81.68.211.31"
serverPort = 7000

auth.method = "token"
auth.token = "REPLACE_WITH_FRP_TOKEN"

transport.tls.enable = true

[[proxies]]
name = "agent"
type = "tcp"
localIP = "127.0.0.1"
localPort = 3000
remotePort = 18080

[[proxies]]
name = "jira"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8080
remotePort = 18081

[[proxies]]
name = "teamcity"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8111
remotePort = 18082
```

`localPort` 改为实际监听端口。Jira 默认 8080，TeamCity 默认 8111。

## 六、添加更多端口映射

在 `frpc.toml` 的 `[[proxies]]` 列表末尾追加，`remotePort` 须在 18080-18089 范围内：

```toml
[[proxies]]
name = "new-service"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9000
remotePort = 18083
```

## 七、访问验证

```bash
# 等 frpc 接入后：
curl -i http://81.68.211.31:18080/health

# 没有 /health 时使用根路径：
curl -i http://81.68.211.31:18080/
```

## 八、回滚

```bash
# 停止服务
sudo systemctl stop frps

# 关闭端口
sudo ufw delete allow 18080/tcp

# 完全卸载
sudo systemctl disable --now frps
sudo rm -f /etc/systemd/system/frps.service
sudo systemctl daemon-reload
sudo rm -rf /opt/frp /etc/frp /var/log/frp
sudo userdel frp || true
```

## 九、注意事项

- VPS 是腾讯云 CVM，还需在腾讯云安全组控制台放行 `7000/tcp` 和 `18080-18082/tcp`，否则外网不通。
- 获取 VPS 公网 IP 时避免走代理：`curl --noproxy '*' ifconfig.me`。
- 真实 token 不应写入可提交 reference；如 token 泄露，应在 VPS `/etc/frp/frps.toml` 和所有 client `frpc.toml` 中同步轮换。
