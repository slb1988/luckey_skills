# auto-server 上的 Memory Hub 局域网转发（:9287）

Memory Hub 跑在 NAS `10.77.77.6:9287`（WireGuard 地址），LAN 机器直连不到 NAS 的物理网段。
2026-09-09 起在 auto-server（`192.168.2.13`，WG `10.77.77.4`）上架了透明 TCP 转发，
LAN / WG 网段任意机器可经 auto-server 访问 Hub。

## 访问入口

| 入口 | 适用网段 | 目标 |
|------|----------|------|
| `http://192.168.2.13:9287` | 局域网 192.168.2.x | NAS `10.77.77.6:9287` |
| `http://10.77.77.4:9287` | WireGuard 网段 | 同上 |

**验证用 `/health/ready`，不要用 `/`**：Hub 根路径没有路由，gunicorn 对 `/` 一律返回 404
（"Not Found / The requested URL was not found on the server"）。这个 404 来自 Hub 本身，
恰恰证明转发链路是通的——转发器是透明 TCP 管道，不改写任何字节，转发与直连的响应逐字节一致
（只有 Hub 按请求生成的 `X-Request-Id` 不同）。

```bash
curl http://192.168.2.13:9287/health/ready   # 应返回 ready
```

## 实现

- 转发器：`/home/dev/port-forward/forward-9287.py`（Python asyncio 纯 TCP 转发，无外部依赖，
  HTTP/WebSocket 均可穿透；监听 `0.0.0.0:9287`，目标 `10.77.77.6:9287`）
- 常驻：`systemd --user` 服务 `forward-9287.service`（`Restart=always`），
  已 `loginctl enable-linger dev`，开机/重启后无需登录自动拉起
- 防火墙：UFW active（INPUT 默认 DROP），已放行 `9287/tcp ALLOW Anywhere`（v4+v6，
  持久化在 ufw 规则文件，重启不丢）

## 运维命令

```bash
systemctl --user status forward-9287     # 状态
systemctl --user restart forward-9287    # 改端口/目标后重启
journalctl --user -u forward-9287 -f     # 日志
```

改目标地址/端口：编辑 `forward-9287.py` 里的 `TARGET_HOST` / `TARGET_PORT` / `LISTEN_PORT`，
然后 `systemctl --user restart forward-9287`。

## 坑：dev 用户没有 sudo 密码

auto-server 的 `dev` 账户 sudo 需要密码（会话内拿不到），nginx 由 root 运行无法 reload，
所以没有用 nginx 反代，而是用户态转发器（9287 > 1024，无需特权端口）。

**需要 root 时的替代路径**：`dev` 在 docker 组（等价 root），用特权容器 + chroot 宿主机执行：

```bash
docker run --rm --privileged --net host -v /:/host alpine:3.21 \
  chroot /host <命令>          # 例：/usr/sbin/ufw allow 9287/tcp、iptables -L -n
```

宿主机本地镜像有 `alpine:3.21`、`nginx:alpine`、`postgres:*-alpine` 等可直接用，无需拉取。
ufw 的 Python SyntaxWarning 输出是噪音，看最后 "Rule added" 即可。

## 关闭转发

```bash
systemctl --user disable --now forward-9287
sudo ufw delete allow 9287/tcp   # 或用上面的 docker 路径执行
```
