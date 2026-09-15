# GitHub → VPS 静态发布

## 发布边界

- 源码：<https://github.com/slb1988/save_one_stroke.git>。
- 目标站点：<https://game.luckeyhome.site/>，独立 game 子域与 TLS。
- 发布由 `@vps-agent` 直接从 GitHub 拉取指定版本并在 VPS 执行；不经 NAS 中转、反代或文件同步。
- 只操作该游戏站点。VPS 认证、Nginx/TLS 运维和具体命令由 VPS agent 自己的技能与业务上下文负责，不在本 skill 复制运维流程或保存凭据。

## 稳定部署约定

VPS 检出目录为 `/home/ubuntu/games/save_one_stroke`，静态发布采用 `/var/www/game/releases/<commit>` 与 `/var/www/game/current` 软链，站点配置位于 `/etc/nginx/sites-available/game`。这些是目标站点的定位约定，执行前由 VPS agent 核对；有漂移先回报，不顺带迁移基础设施。

直接由 Nginx 提供游戏的 HTML/CSS/JS、本地物理库、关卡 JSON/清单及需要公开的规则文档，无生产 Node 进程需求。发布内容使用明确的静态文件范围，不把 `.git`、凭据或开发私有文件暴露为静态资源。

## 最小交接

1. 确认发布获授权，游戏改动已提交并推送，记录远端可取的 commit/tag；若用户要求某分支最新，先解析成具体 commit 后交接。不要让服务器拉取未验证的本机工作区。
2. 给 VPS agent 仓库、版本、目标域名、仅此站点的范围，以及本地实际完成的关键验证。缺版本或目标有歧义时先补齐，不默认发布。
3. 让 VPS agent 按已有 release/current 约定发布、保留可回滚版本，并回报部署版本与关键验收证据；失败先回报，不授权扩大修改其他服务。
4. 验收使用严格 TLS 校验，不能用 `curl -k` 或关闭证书验证。至少检查公网首页、入口 JS、本地 Matter.js、关卡清单与一份实际关卡 JSON、`docs/LEVEL_FORMAT.md`；要求成功状态且内容/类型正确，防止 HTML fallback 伪装资源成功。
5. 区分静态资源验证与浏览器可玩性验证。只在收到实际结果后报告发布成功；未进行交互试玩明确注明。回滚同样指定已知版本并验证此站点。

交接示例（替换占位符后发送，而非创建 skill 时执行）：

> 请从 https://github.com/slb1988/save_one_stroke.git 拉取已推送版本 `<commit-or-tag>`，发布到 https://game.luckeyhome.site/。只处理此静态游戏站点，沿用 release/current 约定，不经过 NAS，不新增生产 Node 服务、不调整其他服务。请用严格 TLS 验证首页及入口 JS、Matter.js、关卡清单/实际关卡 JSON 和规则文档的状态、类型与内容，回报实际部署 commit、关键验证与回滚版本；遇到阻塞先回报。本地验证：`<实际命令与结果>`。
