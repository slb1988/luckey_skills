---
name: lldap-setup
description: 使用 Docker 部署 LLDAP（轻量级 LDAP 认证服务）。当用户提到安装 lldap、搭建 LDAP 服务器、Docker LDAP、统一认证、LDAP 认证、lldap 部署、配置 LDAP 服务时触发。即使用户只说"需要搭个 LDAP"或"有没有轻量的认证服务"，也应该考虑使用此 Skill。
---

# LLDAP Docker 部署

使用 Docker Compose 一键部署 LLDAP（Lightweight LDAP）认证服务，数据持久化到 `/data/lldap`。

## 什么是 LLDAP

LLDAP 是一个轻量级的 LDAP 实现，提供 Web 管理界面，适合家庭实验室、小型团队统一认证。支持与 Authelia、Nextcloud、Gitea、Jellyfin 等数十种服务集成。

- 镜像: `lldap/lldap:stable`
- GitHub: https://github.com/lldap/lldap

---

## 部署步骤

### 1. 创建数据目录

```bash
mkdir -p /data/lldap
```

### 2. 生成随机密钥

```bash
# JWT Secret（32字符）
JWT_SECRET=$(tr -dc 'A-Za-z0-9!#%&()*+,-./:;<=>?@[\]^_{|}~' </dev/urandom | head -c 32)
echo "JWT: $JWT_SECRET"

# 管理员密码（12字符）
ADMIN_PASS=$(tr -dc 'A-Za-z0-9!#%&()*+,-./:;<=>?@' </dev/urandom | head -c 12)
echo "Admin: $ADMIN_PASS"
```

### 3. 创建配置文件

写入 `/data/lldap/lldap_config.toml`，参考 `references/lldap_config.toml`。

关键字段：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `ldap_host` | `"0.0.0.0"` | LDAP 监听地址 |
| `ldap_port` | `3890` | LDAP 端口 |
| `http_host` | `"0.0.0.0"` | Web UI 监听地址 |
| `http_port` | `17170` | Web UI 端口 |
| `jwt_secret` | 随机生成 | JWT 签名密钥，生产环境必须替换 |
| `ldap_base_dn` | `"dc=example,dc=com"` | LDAP Base DN |
| `ldap_user_dn` | `"admin"` | 管理员用户名 |
| `ldap_user_pass` | 随机生成 | 管理员初始密码（首次登录后修改） |
| `database_url` | `"sqlite:///data/users.db?mode=rwc"` | 数据库连接 |
| `key_seed` | 随机字符串 | 密码加密种子 |

> ⚠️ **安全提醒**：生产环境必须修改 `ldap_base_dn`、`ldap_user_pass`、`jwt_secret` 和 `key_seed`。

### 4. 创建 docker-compose.yml

写入 `/data/lldap/docker-compose.yml`，参考 `references/docker-compose.yml`。

```yaml
services:
  lldap:
    image: lldap/lldap:stable
    container_name: lldap
    restart: unless-stopped
    ports:
      - "3890:3890"   # LDAP
      - "17170:17170" # Web UI
    volumes:
      - /data/lldap:/data
    environment:
      - UID=1000
      - GID=1000
      - TZ=Asia/Shanghai
```

> **注意**：如果 `/data/lldap` 下已有 `lldap_config.toml`，容器会自动使用它，不需要额外的环境变量。

### 5. 启动服务

```bash
cd /data/lldap
docker compose pull
docker compose up -d
```

### 6. 验证部署

```bash
# 查看容器状态
docker ps --filter name=lldap

# 查看启动日志
docker logs lldap

# 验证 Web UI 可访问
curl -s -o /dev/null -w "%{http_code}" http://localhost:17170
# 应返回 200
```

---

## 默认端口与服务

| 服务 | 端口 | 协议 | 说明 |
|------|------|------|------|
| LDAP | `3890` | TCP | 标准的 LDAP 查询与绑定 |
| Web UI | `17170` | HTTP | 管理界面，用户登录、管理 |

### LDAP 连接信息

```
Host: <服务器IP>
Port: 3890
Base DN: dc=example,dc=com
Bind DN: cn=admin,ou=people,dc=example,dc=com
```

集成其他服务时，按各自文档填写上述 LDAP 参数即可。具体集成模板见 lldap 仓库的 `example_configs/` 目录。

<memory category="common-patterns">
Windows 盘 FTP 想统一用 LLDAP 账号：微软 IIS FTP 只认 Windows 本地账户或 AD 域，不支持通用 LDAP Bind，接不进 LLDAP；pGina 也无效（IIS FTP 走 LogonUser 网络登录，不经过交互式登录）；LLDAP 只存密码哈希不可导出，"同步成 Windows 本地账户"路线不通。已确认可行路径：用 SFTPGo（Windows 原生服务，FTP/FTPS/SFTP/WebDAV 一体）替代 IIS FTP，其内置 LDAP 用 `bind_as_user: true`，用户 DN 模式 `uid=%username%,ou=people,<base dn>`，首次登录自动建档；盘符权限用 SFTPGo 的 per-user/per-group virtual folder 映射（如 D:\、E:\ 分用户设只读/读写）。
</memory>

---

## 默认管理员账号

| 字段 | 值 | 来源 |
|------|-----|------|
| 用户名 | `admin` | `ldap_user_dn` |
| 密码 | 配置中 `ldap_user_pass` 的值 | 启动时创建 |
| Web UI | `http://<IP>:17170` | 浏览器访问 |

> ⚠️ **首次登录后立即修改密码**。如果忘记密码，可在 `lldap_config.toml` 中设置 `force_ldap_user_pass_reset = true` 并重启容器。

---

## 数据持久化

所有数据存储在宿主机 `/data/lldap/` 下：

| 文件 | 说明 |
|------|------|
| `users.db` | SQLite 数据库（自动创建） |
| `lldap_config.toml` | 主配置文件 |
| `docker-compose.yml` | Docker Compose 编排文件 |
| `private_key` | 密码加密私钥（自动生成，如果配置了 `key_file`） |

---

## 日常管理

```bash
# 停止
docker compose -f /data/lldap/docker-compose.yml down

# 重启
docker compose -f /data/lldap/docker-compose.yml restart

# 查看实时日志
docker logs -f lldap

# 更新镜像
docker compose -f /data/lldap/docker-compose.yml pull
docker compose -f /data/lldap/docker-compose.yml up -d

# 进入容器
docker exec -it lldap /bin/bash
```

---

## 健康检查

容器内置健康检查命令：

```bash
# 手动执行（在容器内）
docker exec lldap /app/lldap healthcheck --config-file /data/lldap_config.toml
```

---

## 故障排查

| 症状 | 排查方式 |
|------|----------|
| 容器起不来 | `docker logs lldap` 查看最后 50 行日志 |
| `/data` 无法写入 | 容器内的 `/data` 是挂载的宿主机目录，确认权限 |
| 端口冲突 | 宿主机 3890 或 17170 已被占用，修改 compose 端口映射 |
| 密码登录失败 | 在 config 中设置 `force_ldap_user_pass_reset = true` 重启 |
| 数据库损坏 | 停止容器 → 备份 → 删除 `users.db` → 重启（注意：用户数据会丢失） |
| 忘记管理员密码 | 编辑 `lldap_config.toml`，修改 `ldap_user_pass`，设置 `force_ldap_user_pass_reset = true`，重启 |

---

## 集成 LDAPS（可选）

如需启用 LDAPS（加密 LDAP），在 `lldap_config.toml` 中添加：

```toml
[ldaps_options]
enabled = true
port = 6360
cert_file = "/data/cert.pem"
key_file = "/data/key.pem"
```

并在 `docker-compose.yml` 中暴露 6360 端口，将证书文件放入 `/data/lldap/` 目录。

---

## 集成 SMTP（可选）

如需密码重置邮件功能，在 `lldap_config.toml` 中配置：

```toml
[smtp_options]
enable_password_reset = true
server = "smtp.gmail.com"
port = 587
smtp_encryption = "TLS"
user = "sender@gmail.com"
password = "your-app-password"
from = "LLDAP Admin <sender@gmail.com>"
reply_to = "Do not reply <noreply@localhost>"
```

> 各服务商具体配置及故障排查见：[references/smtp-config.md](references/smtp-config.md)

---

## 参考文件

- `references/lldap_config.toml` — 完整配置文件模板
- `references/docker-compose.yml` — 完整 Docker Compose 模板
- `references/smtp-config.md` — SMTP 密码重置配置详解（多服务商对照）
