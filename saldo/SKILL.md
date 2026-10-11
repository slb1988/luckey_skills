---
name: saldo
description: Saldo（复刻 Percento 的 Flutter 资产快照记账 App）开发与迭代导航。当用户提到 saldo、Percento 复刻/对标、记账 App、资产快照、entry CSV 导入导出、净资产趋势、收支统计、复式转账、Flutter drift 记账项目时触发。即使用户只说「继续搞 saldo」「复刻下一屏」「看看记账 app」也应触发。仓库在 Mac ~/Documents/Src/saldo。
---

# Saldo

复刻 `/Applications/Percento.app`（macOS Catalyst）的自有实现：Flutter 3.41.9 + drift ^2.30（解析 2.34.4）+ Riverpod + Decimal。本 skill 只做路由——读最少的文件拿上下文，细节一律以仓库内文档为准。

## 入场顺序

1. `~/Documents/Src/saldo/AGENTS.md` — 硬规则（金额禁 float / as-of 重建 / tombstone / 每批必 commit + CHANGELOG）
2. `docs/architecture.md` — 分层、四表模型、复式转账、汇率、里程碑
3. 对应模块 `lib/**/SKILL.md` — 模块级坑与约定
4. 本尊行为/文案疑问 → `docs/hopper/`（61 模块逆向 md + `strings/Localizable.zh-Hans.txt` 术语表 + guide/）；i18n 术语必须对齐该表
5. 产品蓝图与本尊 8 实体 REA 结论 → vault `.claude/plans/类Percento记账App克隆蓝图.md`、`percento-rea-findings.md`

## 模块地图（lib/）

| 模块 | 一句话 |
|---|---|
| `data/` | drift 四表（accounts/entries/settings/fx_rates）+ fx_service + event_log（JSONL 事件日志） |
| `features/home/` | macOS 三栏 shell：侧栏（wordmark/四导航/收藏/齿轮）+ 分类手风琴 |
| `features/accounts/` | 类型选择页（分类横幅默认收起点击展开）→表单、详情页（增减金额\|修改余额分段动作）、排序中点；分组概念已移除勿再引入 |
| `features/entries/` | 记账；快照制核心——Entry.balance = 变动后余额 |
| `features/transfer/` | 复式转账：单事务两条互链 Entry，四象限差额规则 |
| `features/charts/` | 趋势图 as-of 逐日重建；TrendPoint 按分类合计（byCategory） |
| `features/stats/` | 收支统计分桶；同类内部互转经 transferEntryUuid 配账后双腿不计收支 |
| `features/history/` | 全账户流水，行首分类色竖条 |
| `features/import_export/` | Percento CSV 契约（9 列 zh-Hans/min2max5/按年拆/无 BOM）；导入幂等+转账互链 |
| `features/notices/` | 顶部提示条系统 |
| `features/settings/` | 设置页全量（主货币/主题色/示例/指南/回收站/备份/应用锁/自动刷新）+ 诊断；settings 键枚举在 providers.dart |

## 工作流速查

- **UI 对标本尊**：`open -a` 启动两个 app；截图用 `screencapture -x -l <kCGWindowNumber>`（**不是** kCGWindowID，Swift 侧读不出；窗口列表脚本 `/tmp/windump.swift`）；Percento 无窗时 `pkill -x Percento && sleep 2 && open -a Percento`。
- **无头 UI 验证（saldo 自身 build）**：`pkill -x saldo && open build/macos/Build/Products/Debug/saldo.app`。Flutter macOS 的语义控件暴露进 System Events AX 树，可按标签点：`osascript -e 'tell application "System Events" to tell process "saldo" to click (button "退出示例" of … of window 1)'`（`entire contents of window 1` 列全部）。`click at {x,y}` 用屏幕逻辑坐标（CGWindow bounds 就是逻辑点），命中该点**最前台**的窗口——点击前先确认目标 app 窗口在最前，否则点到别的 app。AX 树只剩窗口标题时先解锁语义：`set value of attribute "AXEnhancedUserInterface" of process "saldo" to true`。
- **i18n**：`lib/l10n/app_en.arb`（模板）+ `app_zh.arb`，改后 `flutter gen-l10n`；UI 禁硬编码文案。
- **改 drift schema** 后 `dart run build_runner build -d`。
- **golden 视觉验证**：测试里先加载 Arial Unicode 等字体否则中文变豆腐块；测试字体不含 Material Icons 字形，golden 里图标呈方块属预期（真机正常）。
- **每批收尾**：`flutter analyze` 零问题 + `flutter test` 全绿 → 更新 CHANGELOG.md + 相关 SKILL.md → git commit（英文信息，不留脏工作区）。
- 当前进度与版本：看 `CHANGELOG.md` 顶部 Unreleased + 最新 tag。

<memory category="code-locations">
Percento 本尊（/Applications/Percento.app, Catalyst）bundleId = `com.jakehao.mocha-dark`——
用 Orca computer use / computer-use 工具做对标探索时按此 bundleId 启动与定位目标 app（`open -a` 按名字即可，但 computer-use 的 app 列表/状态接口用 bundleId）。
注意截图可能滞后于 accessibility 树：树已渲染新页面但截图还停在旧页时，重新抓一次截图即可，不要误判为点击未生效。
</memory>

<memory category="code-locations">
Percento 活体数据库（REA/数据实证入口）：`~/Library/Containers/<UUID>/Data/Library/Application Support/Percento/Model.sqlite`——Catalyst 应用的 UUID 容器（本机 3BEC34F8-3C1E-45B6-9E29-CD69276D9453），**不在** app group `group.app.percento`。WAL 模式，分析前先 cp 快照副本再查，勿碰活库。
运行时根因：`decimalMigrated=1` 后旧 Double 金额列冻结写 0、`Account.lastEntryBalance` 缓存失效，余额权威来源 = 最新 Entry 的 `decimalBalance`；Decimal 列在 sqlite 按 REAL 存储。
完整实证见 `.claude/plans/percento-rea-findings.md`「运行时数据库实证」一节。
</memory>
