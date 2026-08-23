# Vue SPA 子路径反代（luckeyhome.site nginx / /memory-hub/）

在 luckeyhome.site 的 nginx（VM-0-3-ubuntu / 81.68.211.31）上，把内网 WireGuard 机器上的
Vue 3 前端仪表盘挂到子路径 `/memory-hub/`。当前实例：`https://luckeyhome.site/memory-hub/`
→ `http://10.77.77.6:9288/`（memory-hub 观测面板）。

> **当前方案（2026-08-22 起）：前端已改为相对路径构建（`vite base: './'` + API 基址相对化），
> nginx 不再需要任何 sub_filter 改写**。下文「历史（已废弃）」记录旧 hack，回滚时参考。

## 组网拓扑（为什么能直连内网）

```text
公网用户 → https://luckeyhome.site (81.68.211.31) → nginx:443
   ├─ /            → 127.0.0.1:8700 (sub2api 主站)
   └─ /memory-hub/ → http://10.77.77.6:9288/   ← 经 wg0 WireGuard 隧道
```

- VPS 有 `wg0`（10.77.77.1/24），NAS 在 10.77.77.6，同网段直连（实测 200 / 17ms），**无需 frp**。
- `10.77.77.6` 是 WG 私有地址，公网用户浏览器不可达 → 必须 nginx **反代**而非 302 跳转。

## 现行 nginx 配方（无改写，生产已验证）

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
}
```

一个纯反代都够，原因：前端源码侧已保证子路径兼容（见下）。

## 前端为什么能零 hack（源码级方案，2026-08-22 落地）

前端 `frontend/`（NAS `/share/Container/memory-hub/frontend`）两处改动：

1. `vite.config.ts` 设 `base: './'` → 构建产物 index.html 的资源引用是**相对路径**
   `./assets/index-*.js`，在 `/memory-hub/` 页面按文档 URL 解析 → `/memory-hub/assets/...`，
   在根路径 `/` 直接访问时解析 → `/assets/...`，**双兼容**。
2. API 基址相对化：源码里所有硬编码 `/api/v1` 的 fetch（原形如 `` fetch(`/api/v1${e}`) ``）
   改为不带前导斜杠的 `api/v1`。页面始终以带尾斜杠 URL 打开（nginx 302 补斜杠保证），
   相对解析稳定 → `/memory-hub/api/v1`。

关键前提（保证相对路径不漂移）：
- Vue Router **hash 模式**（`/#/overview`）：浏览器始终只请求 `/memory-hub/`，相对基准恒定。
  深链 `/memory-hub/#/session/...` 直接可用，无需 SPA fallback。
- Vite 动态 import 用相对 specifier（`import("./SessionsView-xxx.js")`），按
  `import.meta.url`（= `/memory-hub/assets/index-*.js`）解析 → 子路径下天然正确。

**此方案彻底消除了 helper 标识符漂移问题**（见历史：旧 sub_filter 依赖的压缩变量名
`I0`/`E0` 每次 rebuild 都可能变，2026-08-21 曾因此线上挂掉）。前端以后随便 rebuild，
nginx 无需任何改动。

## memory-hub 仪表盘特征（重建后若变化需复测）

| 特征 | 影响 |
|---|---|
| Vue Router **hash 模式**（`/#/overview`） | 无需 SPA fallback；深链直接可用；相对解析基准恒定 |
| API 基址相对 `api/v1`（bundle 内） | 纯反代下自动落到 `/memory-hub/api/v1` |
| uvicorn 直接托管 frontend/dist | 无 cookie / 跨域问题 |
| 新版 dashboard 加了鉴权（LoginView/UsersView） | 未带 token 的 API 请求返回 401 **属预期**（≠ 路径错，路径错是 404） |
| 无 WebSocket / SSE | 无需长连接或流式特殊处理 |

## 验证命令（改完 nginx 或前端 rebuild 后必跑）

```bash
sudo nginx -t && sudo systemctl reload nginx
# 1. 302 补斜杠
curl -sk -o /dev/null -w "%{http_code} -> %{redirect_url}\n" https://luckeyhome.site/memory-hub
# 2. index.html 资源引用为相对路径（./assets/...，与 NAS 直连一致）
curl -sk https://luckeyhome.site/memory-hub/ | grep -oE '(src|href)="[^"]*"'
curl -sk http://10.77.77.6:9288/ | grep -oE '(src|href)="[^"]*"'   # NAS 直连对照，两者应一致
# 3. 公开 API 可达（无鉴权端点）
curl -sk https://luckeyhome.site/memory-hub/api/v1/health/live       # {"status":"healthy"}
# 4. 入口 chunk + 全部动态 import chunk 200 + 正确 MIME
INDEX=$(curl -sk https://luckeyhome.site/memory-hub/ | grep -oE 'src="\./assets/[^"]*\.js"' | head -1 | cut -d'"' -f2 | sed 's|^\./||')
curl -sk -o /dev/null -w "%{http_code} %{content_type} ${INDEX}\n" "https://luckeyhome.site/memory-hub/${INDEX}"
curl -sk "https://luckeyhome.site/memory-hub/${INDEX}" \
  | grep -oE 'import\("\./[A-Za-z0-9_.-]+\.(js|css)"\)' | sort -u \
  | sed 's/import(".\///;s/")//' | while read -r f; do
      curl -sk -o /dev/null -w "%{http_code} %{content_type} ${f}\n" "https://luckeyhome.site/memory-hub/assets/${f}"
    done | grep -v '^200'
# 5. bundle 内无根绝对 helper 残留（期望 0 输出）
curl -sk "https://luckeyhome.site/memory-hub/${INDEX}" | grep -cE '[A-Za-z0-9_$]{1,3}=function\(e\)\{return"/"\+e\}'
```

> 留意：grep 提取文件名会混入 `Node.js`/`this.css`/`e.js` 等字符串碎片导致假 404——只认
> `import("./xxx")` 这种真实动态 import 模式。401 是鉴权预期，不是路径问题。

## 历史（已废弃）：sub_filter hack 方案

2026-08-22 之前，前端用 `base: '/'` 构建，nginx 靠 3 条 sub_filter 把根绝对路径改写成
`/memory-hub/` 前缀。**已整体移除**，仅当回滚到旧前端时恢复。

```nginx
# 旧 hack（已禁用）——依赖三点：
proxy_set_header Accept-Encoding "";   # 关上游压缩（sub_filter 不能改写压缩体）
sub_filter_types text/javascript application/javascript;
sub_filter '/assets/' '/memory-hub/assets/';                    # index.html 资源引用
sub_filter '/api/v1' '/memory-hub/api/v1';                      # bundle 内 API 基址
sub_filter 'I0=function(e){return"/"+e}' 'I0=function(e){return"/memory-hub/"+e}';  # modulepreload helper
sub_filter_once off;
```

旧 hack 的机制与坑（理解报错模式有用）：
- Vite 的 modulepreload helper 把依赖名硬编码拼成 `"/" + 依赖名`（根绝对路径）→ 子路径下丢前缀，
  请求落到主站 location 返回 HTML → 浏览器报 "Failed to load module script ... MIME type
  text/html" 和 "Unable to preload CSS"。
- helper 只内联在入口 chunk 一份（懒加载 chunk 无嵌套动态 import、无自身 helper），单条规则即可
  覆盖全部 chunk。
- helper 的变量名（`I0`→`E0`）是 minifier 生成的，随 build 漂移，曾致 2026-08-21 线上故障；
  更换后需 `grep -oE '[A-Za-z0-9_$]{1,3}=function\(e\){return"/"\+e}' <bundle>` 找当前标识符。
- sub_filter 依赖响应缓冲，不能照抄主站 location 的 `proxy_buffering off`。
- 若把 base 改 `./` 后仍残留 `sub_filter '/assets/'`，会把 `./assets/` 误改为
  `./memory-hub/assets/` → 双重前缀 404。**换新前端必须同时删光 sub_filter**。

## 维护提醒

- 前端 rebuild 后跑上面验证命令（重点：NAS 直连与 nginx 代理的 index.html 应一致、无 helper 残留）。
- 配置备份：`/etc/nginx/sites-available/default.bak.<时间戳>`；回滚 = 拷回备份 + `nginx -t` + reload。
- 需 NAS SSH 权限改前端（VPS 免密未授权）；NAS 侧改完 build + 重启 :9288 后，VPS 侧只动 nginx。