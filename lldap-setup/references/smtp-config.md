# LLDAP SMTP 密码重置配置

## 工作原理

```
用户点击「忘记密码」→ LLDAP 查用户邮箱 → 通过 SMTP 发重置链接 → 用户收邮件重置
```

- LLDAP 本身不存储重置令牌；重置链接是 JWT 签名的一次性 URL，无需数据库
- `enable_password_reset = true` 后，Web UI 登录页自动出现「Forgot password?」入口
- 仅当用户记录中 `email` 字段非空时才能收到邮件

## 配置段

在 `lldap_config.toml` 中添加：

```toml
[smtp_options]
enable_password_reset = true
server = "<SMTP服务器地址>"
port = <端口>
smtp_encryption = "<NONE|TLS|SSL|STARTTLS>"
user = "<邮箱账号>"
password = "<邮箱密码或授权码>"
from = "LLDAP Admin <邮箱账号>"
reply_to = "Do not reply <邮箱账号>"
```

## 常见 SMTP 服务商配置

| 服务商 | server | port | smtp_encryption | 密码类型 |
|--------|--------|------|-----------------|----------|
| 飞书企业邮箱 | `smtp.feishu.cn` | 25 | `NONE` | 邮箱密码 |
| 腾讯企业邮箱 | `smtp.exmail.qq.com` | 465 | `SSL` | 客户端专用密码 |
| 163 邮箱 | `smtp.163.com` | 465 | `SSL` | 客户端授权码 |
| QQ 邮箱 | `smtp.qq.com` | 465 | `SSL` | 授权码 |
| Gmail | `smtp.gmail.com` | 587 | `TLS` | App Password |
| Outlook | `smtp-mail.outlook.com` | 587 | `STARTTLS` | 邮箱密码 |
| 阿里企业邮箱 | `smtp.qiye.aliyun.com` | 465 | `SSL` | 邮箱密码 |
| 自定义 (25 端口) | 按服务商 | 25 | `NONE` 或 `STARTTLS` | — |

> **端口与加密对应**：25 → `NONE`/`STARTTLS`，465 → `SSL`，587 → `TLS`/`STARTTLS`。`STARTTLS` 是从明文升级到加密，`SSL`/`TLS` 是全程加密。

## 生效方式

修改 `lldap_config.toml` 后重启容器：

```bash
docker restart lldap
```

无需重建镜像或重新 `docker compose up`。

## 验证

**方式一**：检查容器能否连通 SMTP 服务器

```bash
docker exec lldap sh -c 'echo "QUIT" | nc <server> <port>'
```

正常响应：
```
220 <hostname> ESMTP ready
221 2.0.0 Bye
```

**方式二**：浏览器访问 `http://<IP>:17170`，确认登录页出现「Forgot password?」链接，点击后输入已填写邮箱的用户名，应收到重置邮件。

## 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 登录页无「忘记密码」入口 | `enable_password_reset` 未设为 `true` | 检查配置并重启 |
| 点发送后无反应 / 超时 | 容器无法连通 SMTP 端口 | `nc` 测试连通性，检查防火墙 |
| 提示用户未填写邮箱 | 该用户在 LLDAP 中 `email` 为空 | 管理员登录 Web UI 补填 |
| 邮件进入垃圾箱 | 发件域名未配置 SPF/DKIM | 在 DNS 添加 SPF 记录 |
| `STARTTLS` 握手失败 | 服务商不支持升级加密 | 改用 `SSL`(465) 或 `NONE`(25) |
