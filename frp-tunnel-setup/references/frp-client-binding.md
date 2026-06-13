# frpc Client 快速绑定流程

用于把一台本地机器上的服务绑定到既有 VPS frps。默认 VPS：

```text
serverAddr = 81.68.211.31
serverPort = 7000
allowed remotePort = 18080-18089
```

真实 token 如需在本机复用，读取 `frp-secrets.local.md`；输出给用户或写入可提交文件时使用 `REPLACE_WITH_FRP_TOKEN`。

## 1. 确认本地服务

先确认服务在本机可访问：

```bash
curl -i http://127.0.0.1:LOCAL_PORT/
```

如果服务有健康检查：

```bash
curl -i http://127.0.0.1:LOCAL_PORT/health
```

## 2. 确认系统架构

```bash
uname -s
uname -m
```

常见下载包：

| 系统 | 架构 | frp 包 |
|---|---|---|
| macOS | arm64 | `darwin_arm64` |
| macOS | x86_64 | `darwin_amd64` |
| Linux | x86_64 | `linux_amd64` |
| Linux | aarch64 | `linux_arm64` |

## 3. 下载 frpc

以 `v0.69.1` macOS Apple Silicon 为例：

```bash
FRP_VERSION="v0.69.1"
mkdir -p ~/frp-client
cd ~/frp-client
curl -LO "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION#v}_darwin_arm64.tar.gz"
tar -xzf "frp_${FRP_VERSION#v}_darwin_arm64.tar.gz"
./frp_${FRP_VERSION#v}_darwin_arm64/frpc --version
```

Linux amd64 示例：

```bash
FRP_VERSION="v0.69.1"
mkdir -p ~/frp-client
cd ~/frp-client
wget "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION#v}_linux_amd64.tar.gz"
tar -xzf "frp_${FRP_VERSION#v}_linux_amd64.tar.gz"
./frp_${FRP_VERSION#v}_linux_amd64/frpc --version
```

## 4. 写入 `frpc.toml`

单服务 agent/harness 示例：

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
```

## 5. 前台启动验证

macOS Apple Silicon 示例：

```bash
~/frp-client/frp_0.69.1_darwin_arm64/frpc -c ~/frp-client/frpc.toml
```

Linux amd64 示例：

```bash
~/frp-client/frp_0.69.1_linux_amd64/frpc -c ~/frp-client/frpc.toml
```

成功日志应包含：

```text
login to server success
proxy added: [agent]
[agent] start proxy success
```

## 6. 公网访问验证

```bash
curl -i http://81.68.211.31:18080/
curl -i http://81.68.211.31:18080/health
```

没有 `/health` 时，用服务真实路径替代。

## 7. Linux systemd 常驻

```bash
sudo mkdir -p /opt/frp /etc/frp /var/log/frp
sudo cp ~/frp-client/frp_0.69.1_linux_amd64/frpc /opt/frp/frpc
sudo cp ~/frp-client/frpc.toml /etc/frp/frpc.toml
sudo chmod +x /opt/frp/frpc
```

创建 `/etc/systemd/system/frpc.service`：

```ini
[Unit]
Description=frp client
Documentation=https://github.com/fatedier/frp
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/frp/frpc -c /etc/frp/frpc.toml
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now frpc
sudo systemctl status frpc --no-pager
```

## 8. macOS launchd 常驻

```bash
sudo mkdir -p /opt/frp /etc/frp /usr/local/var/log/frp
sudo cp ~/frp-client/frp_0.69.1_darwin_arm64/frpc /opt/frp/frpc
sudo cp ~/frp-client/frpc.toml /etc/frp/frpc.toml
sudo chmod +x /opt/frp/frpc
```

创建 `/Library/LaunchDaemons/io.frp.frpc.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>io.frp.frpc</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/frp/frpc</string>
    <string>-c</string>
    <string>/etc/frp/frpc.toml</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/usr/local/var/log/frp/frpc.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/usr/local/var/log/frp/frpc.stderr.log</string>
</dict>
</plist>
```

加载：

```bash
sudo chown root:wheel /Library/LaunchDaemons/io.frp.frpc.plist
sudo chmod 644 /Library/LaunchDaemons/io.frp.frpc.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/io.frp.frpc.plist
sudo launchctl enable system/io.frp.frpc
sudo launchctl kickstart -k system/io.frp.frpc
sudo launchctl print system/io.frp.frpc
```

## 9. 新增一个本地服务

1. 选择未占用的 `remotePort`，范围 `18080-18089`。
2. 确认本地服务：`curl -i http://127.0.0.1:LOCAL_PORT/`。
3. 在 `frpc.toml` 末尾追加：

```toml
[[proxies]]
name = "SERVICE_NAME"
type = "tcp"
localIP = "127.0.0.1"
localPort = LOCAL_PORT
remotePort = REMOTE_PORT
```

4. 重启 frpc。
5. 验证：`curl -i http://81.68.211.31:REMOTE_PORT/`。

## 10. 常见排障

- `login to server failed`：检查 VPS `7000/tcp`、token、TLS 配置。
- `start proxy error`：检查 `remotePort` 是否已占用、是否在 `allowPorts` 范围内。
- 公网端口连不上：检查云安全组、VPS ufw、frpc 是否运行。
- 连接成功但服务无响应：检查本地服务是否监听 `127.0.0.1:LOCAL_PORT`。
- agent/harness 场景：确认应用自身有认证，不要只依赖 frp token。
