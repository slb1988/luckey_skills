---
name: hearthstone-deck-advisor
description: 炉石传说卡组推荐器。把 HSReplay 的卡组胜率、出场率、对阵矩阵下载到本地，结合我的收藏和粉尘，推荐"现在就能组/粉尘够合成"的最强卡组，并按当前天梯环境加权。用户说"推荐卡组"、"我现在能组什么"、"这些尘该合什么"、"现在天梯打什么好"、"更新炉石数据"、"炉石环境怎么样"时触发。分析单个卡包值不值得买用 hearthstone-pack-analyzer。
---

# 炉石卡组推荐

脚本在 `scripts/`，数据在 `~/.hs-advisor/`（Chrome profile、登录会话、每日快照，都不进仓库）。

## 流程

```bash
cd .claude/skills/hearthstone-deck-advisor/scripts
python hs_fetch.py login       # 仅首次或会话过期时：弹出 Chrome，用户手动登录，脚本等待
python hs_fetch.py fetch       # 下载卡牌库 + 环境数据 + 我的收藏 -> data/snapshots/<日期>/ 和 data/latest/
python hs_advisor.py recommend # 推荐报告（默认标准模式）
python hs_advisor.py meta      # 环境概览：出场率、胜率、最好打/最难打
python hs_advisor.py show <deck_id>   # 完整卡表，标出已有/缺失
```

`fetch` 输出里 `logged_in: False` 或没有 `collection__*` 行时，先跑 `login`。登录必须由用户在窗口里完成，
**启动 `login` 前先告诉用户，并给足等待时间**（默认 600 秒，后台运行）。

常用参数：`--format wild`、`--class MAGE`、`--dust 3200`（覆盖收藏里的粉尘数，比如游戏内一键分解之后的总数）、
`--field my_field.json`（自定义对手分布）、`--all-variants`、`--json`。

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

默认环境是 HSReplay 该分段近 7 天的整体出场率。用户说"我最近老遇到 X"时，写一个对手分布文件再跑：

```json
{"Cannon Warrior": 30, "Holy Paladin": 20, "Azalina Priest": 15}
```

```bash
python hs_advisor.py recommend --field my_field.json
python hs_advisor.py meta --field my_field.json
```

键是 `meta` 输出里的卡组类型英文名或 archetype id，值是相对权重。

## 数据范围与限制

- 直连 HSReplay 会被 Cloudflare 拦（403），所以抓取走真实 Chrome + 页面内 fetch；窗口会短暂弹出。
- 免费账号只有 **青铜–黄金段**、全服区数据；钻石–传说段和国服单独数据需要 Premium（`fetch` 会自动探测，有权限就一并下载，
  `recommend` 默认优先用高分段）。
- 狂野模式没有出场率和对阵数据，综合分只反映列表自身胜率。
- 收藏来自 HDT 上传到 HSReplay 的数据，游戏里开包/合成后要等 HDT 同步再 `fetch`。
- 抓取频率保持每天至多一两次，仅个人使用。

接口细节与账号参数见 `../hearthstone-pack-analyzer/references/hsreplay-api.md`。
