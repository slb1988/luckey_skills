# jump.html — SPA 路由绕过

## 问题

由于 `location /` 中 `try_files $uri $uri/ /index.html`，所有不匹配文件/目录的请求都会 fallback 到 `/index.html`（SPA 入口）。SPA 加载后，Vue/React Router 会接管 URL，导致访问静态 `.html` 页面时被重定向到 SPA 路由（如 `/dashboard/branch-status`）。

### 典型场景

访问 `/jump.html/?url=...` 时：
- `$uri` = `/jump.html/` → nginx 视为目录 → `try_files` 找不到 → fallback 到 `/index.html`
- SPA 加载 → Router 解析 URL → 跳转到 `/dashboard/branch-status?url=...`

## 解决方案：文件改为目录

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

### 调试命令

```bash
# 检查是否返回正确内容
curl -s "http://localhost/jump.html/?url=https://example.com"

# 检查 HTTP 状态码
curl -s -o /dev/null -w "%{http_code}" "http://192.168.2.13/jump.html/"
```
