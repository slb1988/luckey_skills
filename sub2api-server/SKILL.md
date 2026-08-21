---
name: sub2api-server
description: 本机（VM-0-3-ubuntu / 81.68.211.31）Sub2API（LuckeyAPI）部署与运维参考。文档覆盖 Docker Compose 栈、端口映射、命名卷、配置位置，以及前置 nginx 反向代理（luckeyhome.site）。当用户提到启动/停止/重启 sub2api、luckeyhome.site 打不开、改本机 nginx 反代、查看 sub2api 容器时触发。
---

# Sub2API Server (LuckeyAPI)

本机 `VM-0-3-ubuntu`（公网 `81.68.211.31`）运行 Sub2API——AI API 网关，前端品牌 "LuckeyAPI"。
公网经 nginx 反代到 `luckeyhome.site`。

## 架构

```
公网用户
   │  HTTPS https://luckeyhome.site:443
   ▼
nginx (systemd, 监听 0.0.0.0:80/443)
   │  80 → 301 跳转 HTTPS;  443 → proxy_pass http://127.0.0.1:8700
   ▼
sub2api 容器  (宿主机 8700 → 容器内 8080)
   ├── sub2api-postgres  (postgres:18-alpine, 5432, 仅内网)
   └── sub2api-redis     (redis:8-alpine,    6379, 仅内网)
```

## 快速信息

| 项目 | 值 |
|------|-----|
| 主机 | `VM-0-3-ubuntu` / 公网 `81.68.211.31` |
| 部署目录 | `/home/ubuntu/sub2api-build/deploy` |
| Compose 文件 | `docker-compose.yml`（命名卷版本） |
| Compose 项目名 | `deploy`（= 目录名；卷名前缀 `deploy_`） |
| 应用镜像 | `weishaw/sub2api:latest`（本地 tag `sub2api:latest` 同一 ID） |
| 端口 | 宿主机 `8700` → 容器 `8080` |
| 域名 | `luckeyhome.site` / `www.luckeyhome.site` |
| 环境变量 | `/home/ubuntu/sub2api-build/deploy/.env` |
| 数据卷 | `deploy_sub2api_data`、`deploy_postgres_data`、`deploy_redis_data` |
| 网络 | `deploy_sub2api-network`（bridge） |

## 启停命令

```bash
cd /home/ubuntu/sub2api-build/deploy
docker compose up -d                 # 启动整栈（postgres、redis、sub2api）
docker compose ps                    # 状态（应全部 Up (healthy)）
docker compose logs -f sub2api       # 应用日志
docker compose restart sub2api       # 仅重启应用
docker compose down                  # 停止整栈
```

nginx 是 systemd 服务（已 enable，随开机自启）：

```bash
systemctl status nginx
sudo systemctl reload nginx          # 改配置后平滑重载
```

## nginx 反向代理要点

`/etc/nginx/sites-available/default`：

- **80** → `return 301 https://$host$request_uri`（HTTP 强制跳 HTTPS）
- **443** ssl：letsencrypt 证书 `/etc/letsencrypt/live/luckeyhome.site/`
- `proxy_pass http://127.0.0.1:8700`（指向 sub2api 宿主机映射端口）
- 反代带 WebSocket 升级头（`Upgrade` / `Connection: upgrade`），`proxy_buffering off`（适合流式/SSE）
- ACME 校验放行 `/.well-known/acme-challenge/`

## .env 关键项

| 变量 | 本机值 / 说明 |
|------|--------------|
| `BIND_HOST` | `0.0.0.0` |
| `SERVER_PORT` | `8700`（宿主机对外端口） |
| `POSTGRES_PASSWORD` | `sub2api_pg_2024_secure` |
| `ADMIN_EMAIL` | `admin@sub2api.local`（首次启动自动建的管理员） |
| `JWT_SECRET` / `TOTP_ENCRYPTION_KEY` / `ADMIN_PASSWORD` | 留空 → 每次启动自动生成（生产建议固定，否则重启后会话/2FA 可能失效） |

> 详细部署方法（Docker / 二进制 / macOS）见仓库 `deploy/README.md`；管理员后台 API 用法见 `sub2api-admin` skill。

## 诊断提示

- 本机 shell 全局设置了 `http_proxy`/`https_proxy` → mihomo `127.0.0.1:7892`。本地验证服务时务必加 `--noproxy '*'`，否则 localhost 请求被代理拦截。
  ```bash
  curl -s --noproxy '*' -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8700/health   # 期望 200
  curl -sk --noproxy '*' -o /dev/null -w "%{http_code}\n" https://127.0.0.1/ -H "Host: luckeyhome.site"   # 期望 200
  ```
- 容器健康检查路径是容器内 `http://localhost:8080/health`（`docker compose ps` 显示 healthy 即应用正常）。
