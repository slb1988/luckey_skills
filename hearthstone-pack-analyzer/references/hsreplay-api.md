# HSReplay.net API 参考

## 账号信息

- 战网 ID: Luckey#5237（国服）
- region: `5`（国服）
- account_lo: `37007265`
- Session 文件: `.claude/hsreplay_session.json`（存有 csrftoken 和 cookies，可能过期需重新登录）

## 登录流程

1. 用 Playwright 打开 `https://hsreplay.net/`，自动跳转到 Google OAuth 登录
2. 用户手动完成 Google 登录
3. 登录成功后保存 cookies 到 `.claude/hsreplay_session.json`

登录后从网络请求中捕获 `account_lo`（方法：监听 `/api/v1/collection/` 请求的 URL 参数）：

```js
// 在 hsreplay.net/collection/mine/ 页面执行
const requests = await page.network_requests(filter='collection');
// URL 格式: /api/v1/collection/?region=5&account_lo=37007265&type=CONSTRUCTED
```

## 核心 API

### 1. 获取我的收藏

```
GET /api/v1/collection/?region=5&account_lo=37007265&type=CONSTRUCTED
```

**需要登录 cookie**，无需 Premium。

返回格式：
```json
{
  "collection": {
    "<dbfId>": [normal_count, golden_count, 0, 0, 0, 0, 0, 0],
    "123493": [1, 0, 0, 0, 0, 0, 0, 0]
  }
}
```

- `[0]` = 普通版拥有数量
- `[1]` = 金卡版拥有数量
- 传说最多 1 张，其他最多 2 张

### 2. 卡牌流行度数据

```
GET /analytics/query/single_card_stats_over_time_v2/?GameType=RANKED_STANDARD&card_id=<dbfId>&LeagueRankRange=BRONZE_THROUGH_GOLD
```

- **无需 Premium**（BRONZE_THROUGH_GOLD 段位免费）
- **需要 Premium**：DIAMOND_THROUGH_LEGEND 及以上段位
- 返回每日流行度时间序列（`popularity_over_time`），单位为 % （含该卡的套牌占所有对局的比例）

返回格式：
```json
{
  "series": [
    {
      "card_id": 123493,
      "name": "popularity_over_time",
      "data": [
        {"x": "2026-05-28", "y": 10.2},
        ...
      ]
    }
  ]
}
```

### 3. 卡牌数据库（中文）

```
GET https://api.hearthstonejson.com/v1/latest/zhCN/cards.collectible.json
```

公开 API，无需登录。返回所有可收集卡牌的完整信息，用于名称→dbfId 映射。

关键字段：
```json
{
  "dbfId": 123493,
  "name": "巴珊娜·符文图腾",
  "rarity": "LEGENDARY",  // COMMON / RARE / EPIC / LEGENDARY
  "cardClass": "DRUID",
  "cost": 7,
  "set": "CATACLYSM"
}
```

## 流行度评级参考

| 流行度 | 评级 | 含义 |
|--------|------|------|
| >8% | 🔥🔥🔥 | 顶级核心，强势套牌必备 |
| 3~8% | 🔥🔥 | 主流用牌 |
| 1~3% | 🔥 | 有人使用 |
| 0.2~1% | 低 | 小众/情况用牌 |
| <0.2% | 极低 | 几乎不用 |

## 合成/分解尘价参考

| 稀有度 | 合成价 | 分解价 | 金卡合成 | 金卡分解 |
|--------|--------|--------|----------|----------|
| 普通   | 40     | 5      | 400      | 50       |
| 稀有   | 100    | 20     | 800      | 100      |
| 史诗   | 400    | 100    | 1600     | 400      |
| 传说   | 1600   | 400    | 3200     | 1600     |
