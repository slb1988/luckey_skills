# Vue SPA 子路径反代（luckeyhome.site nginx / /memory-hub/）

在 luckeyhome.site 的 nginx（VM-0-3-ubuntu / 81.68.211.31）上，把内网 WireGuard 机器上的
Vue 3 前端仪表盘挂到子路径 `/memory-hub/` 的完整配方与系统原理。
当前实例：`https://luckeyhome.site/memory-hub/` → `http://10.77.77.6:9288/`（memory-hub 观测面板）。

## 组网拓扑（为什么能直连内网）

```text
公网用户 → https://luckeyhome.site (81.68.211.31) → nginx:443
   ├─ /            → 127.0.0.1:8700 (sub2api 主站)
   └─ /memory-hub/ → http://10.77.77.6:9288/   ← 经 wg0 WireGuard 隧道
```

- VPS 有 `wg0`（10.77.77.1/24），NAS 在 10.77.77.6，同网段直连（实测 200 / 17ms），**无需 frp**。
- `10.77.77.6` 是 WG 私有地址，公网用户浏览器不可达 → 必须 nginx **反代**而非 302 跳转。
  302 到内网 IP 只在客户端自身也连 WG 时有效。

## 子路径挂载的 nginx 配方（生产已验证）

```nginx
location = /memory-hub {
    return 302 /memory-hub/;          # 补尾斜杠，让前缀 location 命中
}

location /memory-hub/ {
    proxy_pass http://10.77.77.6:9288/;   # 尾斜杠 = 剥离 /memory-hub 前缀转发

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;

    proxy_set_header Accept-Encoding "";   # 必须：关上游压缩，sub_filter 才能改写响应体

    sub_filter_types text/javascript application/javascript;  # text/html 默认已含，重复声明会告警
    sub_filter '/assets/' '/memory-hub/assets/';
    sub_filter '/api/v1' '/memory-hub/api/v1';
    sub_filter 'I0=function(e){return"/"+e}' 'I0=function(e){return"/memory-hub/"+e}';
    sub_filter_once off;
}
```

⚠️ 不要照抄主站 location 的 `proxy_buffering off`：sub_filter 依赖默认开启的响应缓冲。

## Vite(base:"/") 产物在子路径下的三个路径来源（系统属性）

| 来源 | 形态 | 处理方式 |
|---|---|---|
| index.html 资源引用 | 字面量 `/assets/index-*.js\|css` | sub_filter 改写 `/assets/` |
| JS bundle 内 API 基址 | 字面量 `/api/v1`（Vite base 不碰运行时字符串） | sub_filter 改写 `/api/v1` |
| 运行时 modulepreload 链接 | helper `I0=function(e){return"/"+e}` 把相对依赖名拼成根绝对路径 | sub_filter 改写 helper |

核心系统属性（解释了为什么需要这三条改写）：

1. **动态 import 与 preload 链接的解析方式不同**：Vite 的动态 import 用相对 specifier
   （`import("./OutboxView-xxx.js")`），按 `import.meta.url` 解析 → 子路径下天然正确；
   但 modulepreload helper 把依赖名硬编码拼成 `"/" + 依赖名`（根绝对）→ 子路径下丢前缀，
   请求落到主站 location 返回 HTML → 浏览器报 "Failed to load module script ... MIME type text/html"。
2. **helper 只内联在入口 chunk 一份**：懒加载 chunk 是叶子模块（无嵌套动态 import、无自身 helper），
   因此单条 sub_filter 规则即可覆盖全部 chunk 的 preload。
3. **sub_filter 是响应体字面量替换**，前提：上游不压缩（`Accept-Encoding ""`）+ 缓冲开启。
4. `sub_filter_types` 默认只含 `text/html`；追加 JS 类型时**不要重复声明 text/html**
   （nginx -t 会报 duplicate MIME type 警告）。

## memory-hub 仪表盘特征（决定配方形状，重建后若变化需复测）

| 特征 | 影响 |
|---|---|
| Vue Router **hash 模式**（`/#/overview`） | 浏览器只请求 `/`，无需 SPA fallback；`/memory-hub/#/overview` 深链直接可用 |
| API 全部在 `/api/v1/*`（bundle 内硬编码） | 改写 `/api/v1` 即全覆盖 |
| uvicorn 直接托管 frontend/dist，无鉴权 | 无 cookie / 跨域问题 |
| 无 WebSocket / SSE | 无需长连接或流式特殊处理 |

## 验证命令（改完 nginx 必跑）

```bash
sudo nginx -t && sudo systemctl reload nginx
# 1. 302 补斜杠
curl -sk -o /dev/null -w "%{http_code} -> %{redirect_url}\n" https://luckeyhome.site/memory-hub
# 2. HTML 资源路径已改写
curl -sk https://luckeyhome.site/memory-hub/ | grep -oE '(src|href)="[^"]*"'
# 3. API 经改写路径可达
curl -sk https://luckeyhome.site/memory-hub/api/v1/health/live          # {"status":"healthy"}
# 4. bundle 内三处模式已改写（期望各 1，无残留旧串）
curl -sk https://luckeyhome.site/memory-hub/assets/index-*.js | grep -c 'I0=function(e){return"/memory-hub/"+e}'
# 5. 全量资源 200 + 正确 content-type
curl -sk https://luckeyhome.site/memory-hub/assets/index-*.js \
  | grep -oE 'assets/[A-Za-z0-9_.-]+\.(js|css)' | sort -u | while read -r f; do
      curl -sk -o /dev/null -w "%{http_code} %{content_type} ${f}\n" "https://luckeyhome.site/memory-hub/${f}"
    done
```

## 长期方案（源码级，可去掉全部 sub_filter hack）

前端 `frontend/`（NAS `/share/Container/memory-hub/frontend`）：
1. `vite.config.ts` 设 `base: './'`（相对路径，根路径与子路径双兼容）；
2. API 基址改相对（bundle 内 `/api/v1` 硬编码，改 `import.meta.env.BASE_URL + 'api/v1'`）；
3. NAS 上 `cd frontend && npm run build` 并重启 backend（:9287/:9288 短暂中断）。

需 NAS SSH 权限（VPS 免密未授权）。重建后 bundle 字符串模式可能变化，sub_filter 规则需复测。

## 维护提醒

- 所有 sub_filter 规则依赖 bundle 内字符串模式；前端重新 build 后必须跑上面验证命令。
- 配置备份：`/etc/nginx/sites-available/default.bak.<时间戳>`；回滚 = 拷回备份 + `nginx -t` + reload。
