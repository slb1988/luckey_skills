---
name: hearthstone-pack-analyzer
description: 炉石传说卡包价值分析工具。用于分析新卡包中哪些卡牌我已拥有、哪些缺失、缺失卡的天梯使用率、多余卡能分解多少尘，并给出购买建议。用户提供卡包卡牌列表时触发，或说"分析卡包"、"这个卡包值得买吗"、"查一下这些卡我有没有"时使用。账号信息和所有 HSReplay API 细节见 references/hsreplay-api.md。
---

# 炉石传说卡包分析

**API 文档、账号参数、尘价表**: 见 `references/hsreplay-api.md`

## 分析流程

### 第一步：确认 HSReplay 登录状态

用 Playwright 打开 `https://hsreplay.net/collection/mine/`：
- 已登录（页面标题含"我的收藏"）→ 进入第二步
- 跳转登录页 → 提示用户手动完成 Google 登录，登录后将 cookies 保存至 `.claude/hsreplay_session.json`

登录后用 `browser_network_requests(filter='collection')` 从网络请求中确认 `account_lo`：
```
URL 格式: /api/v1/collection/?region=5&account_lo=37007265&type=CONSTRUCTED
```

### 第二步：并行获取数据（page.evaluate 内执行）

```js
// A. 我的收藏（需登录 cookie）
fetch('/api/v1/collection/?region=5&account_lo=37007265&type=CONSTRUCTED', { credentials: 'include' })

// B. 全量卡牌数据库（公开，用于名称→dbfId 映射）
fetch('https://api.hearthstonejson.com/v1/latest/zhCN/cards.collectible.json')
```

### 第三步：匹配拥有情况

```js
const owned = collection[String(card.dbfId)] || [0,0,0,0,0,0,0,0];
const maxNormal = card.rarity === 'LEGENDARY' ? 1 : 2;
const missing  = Math.max(0, maxNormal - owned[0]);  // owned[0]=普通数, owned[1]=金卡数
const extra    = Math.max(0, owned[0] - maxNormal);
```

### 第四步：查缺失卡使用率（批量，每张间隔 80ms）

```js
// BRONZE_THROUGH_GOLD 免费可用；DIAMOND_THROUGH_LEGEND 需要 Premium
fetch(`/analytics/query/single_card_stats_over_time_v2/?GameType=RANKED_STANDARD&card_id=${dbfId}&LeagueRankRange=BRONZE_THROUGH_GOLD`, { credentials: 'include' })
// 取 data.series[0].data 最后3条均值作为近期流行度（%）
```

### 第五步：输出报告

按以下四块结构输出：

1. **缺失卡汇总**（传说 / 史诗 / 稀有各一表）
   - 列：卡名 | 职业 | 费用 | 拥有 | 缺失 | 3日均流行度 | 评级

2. **多余卡 & 可分解尘**
   - 列出多余普通版和金卡，按尘价表计算总分解价值

3. **使用率评级说明**（参见 references/hsreplay-api.md 评级表）

4. **购买建议**
   - 缺失卡合成总尘 vs 购买金币价值对比
   - 点名高使用率（>3%）缺失核心牌
   - 明确结论：强烈建议买 / 可以买 / 不急 / 不值得
