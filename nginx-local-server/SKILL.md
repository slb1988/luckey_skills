---
name: nginx-local-server
description: Reference for local nginx server (192.168.2.13) serving py_automation frontend. Documents nginx config, SPA routing, static file tricks, and jump.html redirect helper. Use when troubleshooting or modifying nginx behavior on this machine.
---

# Nginx Local Server

## 概述

本机 `192.168.2.13` 上运行宿主 nginx（port 80），为 py_automation 前端提供静态文件服务。另有一个 Docker nginx 容器运行在 port 81（Dify 项目）。

## 快速信息

| 项目 | 值 |
|------|-----|
| 服务器 IP | `192.168.2.13` |
| 前端根目录 | `/data/py_automation/frontend/dist` |
| nginx 配置文件 | `/etc/nginx/sites-enabled/py_automation.conf` |
| 实际文件 | `/etc/nginx/sites-available/py_automation.conf`（软链接） |

## 两个 Nginx 实例

| 实例 | 端口 | 用途 |
|------|------|------|
| 宿主 nginx（systemd） | 80 | py_automation 前端 + 静态资源 |
| Docker nginx 容器 `docker-nginx-1` | 81、444 | Dify 项目反向代理 |

```bash
# 宿主 nginx
ps aux | grep "/usr/sbin/nginx.*daemon on"
# root  2438  nginx: master process /usr/sbin/nginx -g daemon on;

# Docker nginx
docker ps --format '{{.Names}} {{.Ports}}' | grep nginx
# docker-nginx-1 ... 0.0.0.0:81->81/tcp ...
```

## Nginx 配置 (`py_automation.conf`)

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    root /data/py_automation/frontend/dist;
    index index.html index.htm;

    # index.html — never cache（确保部署后浏览器立即拿到新版）
    location / {
        etag off;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        try_files $uri $uri/ /index.html;
    }

    # Hashed assets（/assets/ 下）— 永久缓存（immutable）
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }

    server_tokens off;
}
```

> **备份文件**：`/etc/nginx/sites-available/py_automation.conf.bak`（修改前自动备份）

## 关键问题：SPA 路由拦截静态页面

### 问题

由于 `location /` 中 `try_files $uri $uri/ /index.html`，所有不匹配文件/目录的请求都会 fallback 到 `/index.html`（SPA 入口）。SPA 加载后，Vue/React Router 会接管 URL，导致访问静态 `.html` 页面时被重定向到 SPA 路由（如 `/dashboard/branch-status`）。

### 典型场景

访问 `/jump.html/?url=...` 时：
- `$uri` = `/jump.html/` → nginx 视为目录 → `try_files` 找不到 → fallback 到 `/index.html`
- SPA 加载 → Router 解析 URL → 跳转到 `/dashboard/branch-status?url=...`

### 解决方案：文件改为目录

将独立的 `.html` 文件改为**同名目录 + index.html**，利用 nginx 的目录索引机制：

```bash
# 1. 删除文件
rm /data/py_automation/frontend/dist/jump.html

# 2. 创建同名目录并放置 index.html
mkdir -p /data/py_automation/frontend/dist/jump.html

# 3. 写入内容
cat > /data/py_automation/frontend/dist/jump.html/index.html << 'HTML'
<!DOCTYPE html>
<html>
<head><script>/* ... */</script></head>
<body></body>
</html>
HTML
```

### 工作原理

| URL | nginx 行为 |
|-----|-----------|
| `/jump.html/?url=...` | `$uri` = `/jump.html/` → 命中目录 → 服务 `index.html` ✅ |
| `/jump.html?url=...` | `$uri` = `/jump.html` → 文件不存在（是目录）→ 301 重定向到 `/jump.html/` ✅ |

两种形式都能正确服务，不会 fallback 到 SPA。

### 替代方案（需要 sudo）

如果能修改 nginx 配置，更优雅的方案是添加精确匹配：

```nginx
location = /jump.html {
    try_files /jump.html =404;
}
```

## jump.html 跳转页

当前位于 `/data/py_automation/frontend/dist/jump.html/index.html`。

功能：读取 URL query param `url`，执行 `location.href` 跳转。用于将 HTTP 链接重定向到自定义协议（如 `pltool://`）。

### 示例

```
http://192.168.2.13/jump.html/?url=pltool%3A%2F%2Fsync%3Fstream%3DRel-0.2%26cl%3D95958%26build_config%3DDevelopment
```

参数 `url`（URL 编码后）会被 `URLSearchParams.get('url')` 解析，然后 `location.href` 跳转。

## 调试命令

```bash
# 检查 nginx 是否返回正确内容
curl -s "http://localhost/jump.html/?url=https://example.com"

# 检查 HTTP 状态码
curl -s -o /dev/null -w "%{http_code}" "http://192.168.2.13/jump.html/"

# 查看目录结构
ls -la /data/py_automation/frontend/dist/

# 测试 nginx 配置语法（需要 sudo）
sudo nginx -t

# 重载 nginx（需要 sudo）
sudo nginx -s reload
```

## 注意事项

- **可 sudo**：拥有 sudo 权限，可以直接修改配置并 reload nginx。
- **浏览器缓存**：修改文件后，浏览器可能缓存旧响应。测试时使用无痕模式或硬刷新（Ctrl+Shift+R）。
- **Docker nginx**：修改 Dify 的 nginx 配置需操作 `/mnt/disk2/dify/docker/nginx/conf.d/` 下的文件并重启容器。
- SPA 的 `index.html` 和 assets 由前端构建生成，修改前确认。
