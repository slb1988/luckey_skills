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

    # ===== 静态资源压缩 =====
    # 优先发送构建产物预生成的 .gz（零 CPU，压缩率最高）
    gzip_static on;
    # 运行时 gzip 兜底：覆盖无 .gz 伴生文件的响应
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_vary on;
    gzip_proxied any;
    gzip_types text/css text/plain application/javascript application/json image/svg+xml;

    # index.html — never cache（确保部署后浏览器立即拿到新版）
    location / {
        etag off;
        if_modified_since off;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "Thu, 01 Jan 1970 00:00:01 GMT";
        try_files $uri $uri/ /index.html;
    }

    # Hashed assets under /assets/ — cache forever (immutable)
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
        # 404 on a hashed asset = stale SPA in browser memory → force reload
        error_page 404 = @missing_asset;
    }

    location @missing_asset {
        add_header Content-Type "application/javascript; charset=utf-8";
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        return 200 "window.location.reload(true);";
    }

    server_tokens off;
}
```

> **备份文件**：`/etc/nginx/sites-available/py_automation.conf.bak`（修改前自动备份）

## 静态资源压缩

### 三层防缓存策略

| 层级 | 机制 | 说明 |
|------|------|------|
| 1. HTTP 头 | `no-store` + `if_modified_since off` + `etag off` + past `Expires` | 浏览器永不缓存 `index.html` |
| 2. HTML `<meta>` | `http-equiv="Cache-Control/Pragma/Expires"` | 兜底，防止浏览器忽略 HTTP 头 |
| 3. `@missing_asset` | 资产 404 → `window.location.reload(true)` | 旧 SPA 在浏览器内存中时，新部署后自动刷新 |

### 策略：gzip_static 优先 + 运行时 gzip 兜底

| 层级 | 指令 | 触发条件 | CPU 开销 | 压缩率 |
|------|------|---------|---------|--------|
| 1 | `gzip_static on` | 同目录存在 `.gz` 伴生文件 | 零 | 最高（离线压缩） |
| 2 | `gzip on` | 无 `.gz` 伴生文件 / 小文件 | 低 | 中等（level 5） |

### 前提前端构建

前端 `vite-plugin-compression`（build 时对 >10KB 的文件生成同名 `.gz`）：
```bash
# build 后在 dist/assets/ 中应出现成对文件
ls /data/py_automation/frontend/dist/assets/index-*.js*
# index-XTP6Nire.js      ← 原始 1.7MB
# index-XTP6Nire.js.gz   ← gzip 压缩 ~550KB
```

如 `.gz` 文件缺失，`gzip_static` 静默跳过，运行时 gzip 会兜底压缩（有效但略耗 CPU）。

### 关键系统属性

- Ubuntu 官方 nginx 包**默认编译进 `http_gzip_static_module`**，无需额外安装
- `gzip_static` 不比对文件 mtime，`.gz` 比原文件旧不影响行为
- 不对图片（png/jpg/webp）开 gzip — 已是压缩格式，徒耗 CPU
- `text/html` 默认被 gzip 覆盖，无需列入 `gzip_types`

### 效果

首屏 JS（1.73MB）+ CSS（357KB）≈ 2.1MB → gzip 后约 550KB，传输体积减少 ~74%。

## SPA 路由拦截 & jump.html

> 详细参考：[jump.html](references/jump-html.md) — SPA fallback 导致静态 HTML 被路由劫持的问题、解决方案（目录化）和跳转页用法。

## 调试命令

```bash
# 查看目录结构
ls -la /data/py_automation/frontend/dist/

# 测试 nginx 配置语法
sudo nginx -t

# 重载 nginx（平滑，不断连接）
sudo systemctl reload nginx

# 验证 gzip 生效（应出现 Content-Encoding: gzip）
JS_FILE=$(curl -s http://192.168.2.13/ | grep -o 'assets/index-[^"]*\.js')
curl -sI -H 'Accept-Encoding: gzip' "http://192.168.2.13/$JS_FILE" | grep -i 'content-encoding\|content-length'
```

## 注意事项

- **可 sudo**：拥有 sudo 权限，可以直接修改配置并 reload nginx。
- **浏览器缓存**：修改文件后，浏览器可能缓存旧响应。测试时使用无痕模式或硬刷新（Ctrl+Shift+R）。
- **Docker nginx**：修改 Dify 的 nginx 配置需操作 `/mnt/disk2/dify/docker/nginx/conf.d/` 下的文件并重启容器。
- SPA 的 `index.html` 和 assets 由前端构建生成，修改前确认。
