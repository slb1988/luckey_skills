---
name: hearthstone-deck-advisor
description: 炉石传说卡组推荐器。把 HSReplay 的卡组胜率、出场率、对阵矩阵下载到本地，结合我的收藏和粉尘，推荐"现在就能组/粉尘够合成"的最强卡组，并按当前天梯环境加权。用户贴任务截图求配卡，或说"快速做任务"、"刷活动进度"、"推荐卡组"、"我现在能组什么"、"这些尘该合什么"、"现在天梯打什么好"、"更新炉石数据"、"炉石环境怎么样"时触发。分析单个卡包值不值得买用 hearthstone-pack-analyzer。
---

# 炉石卡组推荐

脚本在 `scripts/`，数据在 `~/.hs-advisor/`（Chrome profile、登录会话、每日快照，都不进仓库）。

## 快速做任务

用户想刷活动或周常进度时，按**单位时间能触发多少次有效计数**选卡，不直接用 `recommend` 的胜率榜。

1. **读任务原文。** 从截图或文字确认还差多少、什么动作计数、哪些模式有效、加成给哪张牌或哪个动作。例如「抽到指定系列的牌」看的是被抽到的牌，不是过牌法术属于哪个系列；写「获取」的效果不要当成「抽牌」。仅在关键条件看不清时追问。
2. **用现有数据配一套。** 先查 `~/.hs-advisor/data/latest/`：用 `cards_zhCN.json` 看牌文，用 `cards_enUS.json` 核对 `set`、`rarity`，再按 `dbfId` 用 `Collection.count` 核对收藏张数。优先用已有卡，把低费、可重复的触发手段与能吃加成的牌搭起来。快照够用就不刷新环境、不登录；收藏未核实时不报「0 尘」。
3. **给能直接开打的结果。** 先核对模式、职业、套牌张数和同名上限，再用 `hs_common.encode_deckstring` 生成导入码，用 `decode_deckstring` 回读核对卡表。默认只给一套：说明排哪个模式、是否缺卡，附可复制的代码、起手留牌和最赚进度的一两个动作。不把估算说成实测场数。

## 天梯推荐流程

```bash
cd .claude/skills/hearthstone-deck-advisor/scripts
python hs_fetch.py login       # 仅首次或会话过期时：弹出 Chrome，用户手动登录，脚本等待
python hs_fetch.py fetch       # 下载卡牌库 + 两个数据源的环境数据 + 我的收藏 -> data/snapshots/<日期>/ 和 data/latest/
python hs_fetch.py fetch --source firestone   # 只刷新 Firestone 环境数据：纯 HTTP，不弹浏览器，不需要登录
python hs_advisor.py recommend # 推荐报告（默认标准模式、Firestone 钻石–传说段）
python hs_advisor.py meta      # 环境概览：出场率、胜率、最好打/最难打
python hs_advisor.py show <deck_id>   # 完整卡表，标出已有/缺失
```

`fetch` 输出里 `logged_in: False` 或没有 `collection__*` 行时，先跑 `login`。登录必须由用户在窗口里完成，
**启动 `login` 前先告诉用户，并给足等待时间**（默认 600 秒，后台运行）。

常用参数：`--format wild`、`--class MAGE`、`--dust 3200`（覆盖收藏里的粉尘数，比如游戏内一键分解之后的总数）、
`--field my_field.json`（自定义对手分布）、`--all-variants`、`--json`。

## 两个数据源

| | Firestone（默认） | HSReplay |
|---|---|---|
| 分段 | 全部免费：`legend-diamond`（默认）、`legend`、`top-2000-legend`、`diamond`、`platinum`、`bronze-gold`、`all` | 免费只有 `BRONZE_THROUGH_GOLD`；钻石以上要 Premium |
| 对阵数据 | 卡组类型 **对各职业** 的胜率 | 卡组类型 **对各卡组类型** 的胜率（更细） |
| 狂野模式 | 有出场率和对阵 | 只有卡组胜率 |
| 样本来源 | Firestone 用户，海外玩家为主，不分服区 | HDT 用户，全服区合并；国服单独数据要 Premium |
| 抓取方式 | 公开静态文件，直接 HTTP | 真实 Chrome + 页面内 fetch（Cloudflare） |
| 我的收藏 | 无 | 有（需登录） |

- 选数据源：`--source firestone|hsreplay`，默认 `auto`（有 Firestone 数据就用它）。`--rank` 传 HSReplay 的大写分段名时自动切到 HSReplay。
- 要更多 Firestone 分段：`python hs_fetch.py fetch --source firestone --fs-ranks legend-diamond,legend`，
  再用 `--rank legend` 查看。每个分段要下载约 30 个卡组类型的对阵文件（各约 1 MB）。
- 用户在钻石以上：用默认的 Firestone。用户在黄金以下，或想看卡组类型间的克制关系：加 `--source hsreplay`。
- 两个源的卡组类型命名不同（如 `yogg-warrior` 对 `Cannon Warrior`），`--field` 文件里的名字要用当前数据源 `meta` 输出的名字。

## 报告怎么读

- **综合分** = 卡组类型对当前环境的期望胜率 + 该具体列表相对同类型平均的优势。
  - 期望胜率 = Σ 对手出场率 × 对阵胜率（对阵格少于 30 场的忽略，覆盖不足一半时退回类型总胜率）。
  - 列表优势按样本量向类型均值收缩（先验 600 场），避免几百场的高胜率列表霸榜。
- 分三档：**现在就能组**（0 尘）、**粉尘够合成**、**超出预算**；默认每个卡组类型只留最好的一个列表。
  更贵的一档只在比便宜档同类型高出 0.5 分以上时才列出。
- 报告里的“多余副本可分解”只是估算：数据分不清哪些副本不可分解（例如赠送卡），以游戏内一键分解数值为准。
- **合成优先级**：综合分前 60 的列表里最常缺的卡，用来判断哪张卡合了最通用。

给用户结论时，在脚本结果之上再做判断：样本量小的列表要提醒；合成建议优先选"多个强卡组共用"的卡；
传说卡轮换在即（看卡牌 `set`）时提醒保值问题。

## 按我自己的天梯加权

默认环境是所选数据源该分段的整体出场率。用户说"我最近老遇到 X"时，写一个对手分布文件再跑
（示例见 `~/.hs-advisor/fields/example_rogue_heavy.json`）：

```json
{"ayaya-rogue": 50, "void-cthun-dh": 30, "harold-blood-dk": 20}
```

```bash
python hs_advisor.py recommend --field my_field.json
python hs_advisor.py meta --field my_field.json
```

键是 `meta` 输出里的卡组类型英文名或 archetype id，值是相对权重。

## 数据范围与限制

- 直连 HSReplay 会被 Cloudflare 拦（403），所以它的抓取走真实 Chrome + 页面内 fetch；窗口会短暂弹出。
- **没有免费的国服单独环境数据**：国服钻石以上只有 HSReplay Premium（服区筛选）能看；两个免费源都以海外玩家为主，
  国服环境通常相近但不完全一致，用户反馈差异大时用 `--field` 按实际遇到的对手修正。
- HSReplay Premium 开通后 `fetch` 会自动探测并下载 `DIAMOND_THROUGH_LEGEND`、`LEGEND` 分段。
- 已查过但没接入的来源（2026-11）：HSGuru 有钻石–传说筛选，但 Cloudflare 交互验证连真实 Chrome 也过不去；
  Vicious Syndicate 周报按分段分析，但只有文章和图表，没有可下载的数据。
- 收藏来自 HDT 上传到 HSReplay 的数据，游戏里开包/合成后要等 HDT 同步再 `fetch`。
- 抓取频率保持每天至多一两次，仅个人使用。Firestone 数据文件地址取自其开源客户端
  （`Zero-to-Heroes/firestone` 的 `constructed-meta-decks-state-builder.service.ts`），失效时去那里核对。

接口细节与账号参数见 `../hearthstone-pack-analyzer/references/hsreplay-api.md`。
