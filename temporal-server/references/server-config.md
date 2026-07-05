# Temporal Server 配置记录

## 当前服务器（2025-07-05 部署）

| 项目 | 值 |
|------|-----|
| **主机** | `81.68.211.31`（腾讯云） |
| **内网 IP** | `10.0.0.3` |
| **Temporal CLI** | `v1.7.2`（Server `1.31.1`，UI `2.49.1`） |
| **gRPC 端口** | `7233`（0.0.0.0） |
| **Web UI 端口** | `8233`（0.0.0.0） |
| **启动方式** | 后台 `nohup`，日志 `/tmp/temporal-dev.log` |
| **持久化** | 无（内存模式，重启丢数据） |

## 启动命令

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
nohup temporal server start-dev --ip 0.0.0.0 --ui-port 8233 > /tmp/temporal-dev.log 2>&1 &
```

⚠️ **必须先 `unset` 代理环境变量**，否则启动会报 `context deadline exceeded`。

## 防火墙

ufw 已放行两个端口：

```
7233/tcp  ALLOW  Anywhere
8233/tcp  ALLOW  Anywhere
```

## 访问地址

- Web UI: `http://81.68.211.31:8233`
- gRPC: `81.68.211.31:7233`

---

## 修改记录

| 日期 | 变更 |
|------|------|
| 2025-07-05 | 初始部署，绑定 0.0.0.0:7233 + 0.0.0.0:8233 |
| 2025-07-05 | 添加 ufw 规则放行 7233/tcp 和 8233/tcp |
| 2025-07-05 | 修复代理干扰问题（unset http_proxy 后重启） |
