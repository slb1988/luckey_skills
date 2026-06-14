# frpc 开机自启 — macOS (launchd)

适用：macOS，Apple Silicon 或 Intel。Linux 见 [frpc-persistence-linux.md](frpc-persistence-linux.md)，Windows 见 [frpc-persistence-windows.md](frpc-persistence-windows.md)。

## 前提

- `/opt/frp/frpc` 已安装（`/opt/frp/frpc --version` 可执行）
- `/etc/frp/frpc.toml` 已写入正确配置
- `/usr/local/var/log/frp/` 目录存在

```bash
sudo mkdir -p /opt/frp /etc/frp /usr/local/var/log/frp
sudo cp ~/frp-client/frp_0.69.1_darwin_arm64/frpc /opt/frp/frpc
sudo chmod +x /opt/frp/frpc
sudo cp ~/frp-client/frpc.toml /etc/frp/frpc.toml
```

## 安装 launchd 服务

```bash
sudo tee /Library/LaunchDaemons/io.frp.frpc.plist > /dev/null << 'EOF'
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
EOF

sudo chown root:wheel /Library/LaunchDaemons/io.frp.frpc.plist
sudo chmod 644 /Library/LaunchDaemons/io.frp.frpc.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/io.frp.frpc.plist
sudo launchctl enable system/io.frp.frpc
```

如果之前有手动在后台启动的 frpc，先停掉避免重复：

```bash
pkill -f frpc || true
```

## 验证

```bash
sudo launchctl print system/io.frp.frpc   # 应显示 state = running
curl -i http://81.68.211.31:18080/        # 公网验证
```

## 常用管理命令

```bash
# 查看状态
sudo launchctl print system/io.frp.frpc

# 重启（改完 frpc.toml 后执行）
sudo launchctl kickstart -k system/io.frp.frpc

# 停止（不卸载，下次开机仍会启动）
sudo launchctl kill SIGTERM system/io.frp.frpc

# 卸载（彻底移除自启）
sudo launchctl bootout system /Library/LaunchDaemons/io.frp.frpc.plist
sudo rm /Library/LaunchDaemons/io.frp.frpc.plist
```

## 查看日志

```bash
tail -f /usr/local/var/log/frp/frpc.stdout.log
tail -f /usr/local/var/log/frp/frpc.stderr.log
```

## 排障

| 现象 | 原因 | 解决 |
|---|---|---|
| `state = waiting` 反复重启 | frpc 启动失败（token/配置错误） | 看 stderr 日志定位原因 |
| `Bootstrap failed: 125` | plist 已加载，重复 bootstrap | 先 bootout 再 bootstrap |
| 公网不通但 launchd running | 检查本地服务是否监听 | `curl http://127.0.0.1:LOCAL_PORT/` |
| 重启后隧道断开 | 网络起来慢于 frpc 启动 | `KeepAlive=true` 会自动重连，无需处理 |
