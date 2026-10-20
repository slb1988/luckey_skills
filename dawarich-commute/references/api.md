# Dawarich API 契约（本实例实测）

实例：`http://10.77.77.6:3000`（QNAP NAS Docker，WireGuard 网段 10.77.77.0/24，客户端必须绕过系统代理直连）。

## 权威 spec

- **`http://10.77.77.6:3000/api-docs/v1/swagger.yaml`**（注意带 `/v1/`）——完整 OpenAPI 3.0 spec，约 200KB
- 官网文档站 `dawarich.app/docs/api/...` 是 Docusaurus 客户端渲染，静态抓取拿不到参数细节，别抓

## 认证

两种方式同时带即可（不同端点文档声明不一致，places/visits 声明 Bearer header，points/stats 声明 query param）：

- Query param：`?api_key=<KEY>`
- Header：`Authorization: Bearer <KEY>`

Key 在 web 端 Settings → API key 生成。无 key 时 `/api/v1/stats` 返回 401，根路径 200（可用来区分「服务活着但 key 错」与「服务挂了」）。

## 端点

### `GET /api/v1/points` — 轨迹点（通勤计算的数据源）

参数：`start_at` / `end_at`（ISO 8601，`2024-02-03` 或 `2024-02-03T13:00:03Z`）、`page`、`per_page`、`order=asc|desc`。

- 分页总量在响应头 **`X-Total-Pages`**（不在 body），`per_page=1000` 实测可用
- 点的关键字段：`timestamp`（unix 秒）、`latitude`、`longitude`、`accuracy`（米，可能为 null）、`velocity`、`city`、`tracker_id`、`import_id`

### `GET /api/v1/places` — web 端手动建的地点（锚点来源）

返回数组：`id`、`name`、`latitude`、`longitude`、`source`（manual=web 手动建）、`tags`。
通勤脚本按名称匹配锚点：`home`/`家` → 家，`公司`/`work` → 公司。

### `GET /api/v1/stats` — 总量自检

`totalDistanceKm`、`totalPointsTracked`、`totalCountriesVisited`、`totalCitiesVisited`、`yearlyStats[]`。`--selfcheck` 用它验证 key。

### 其他（暂未用于通勤，留备扩展）

- `GET /api/v1/timeline?start_at&end_at` — 逐日 visits+tracks+photos（范围 ≤31 天）；实例上 visits 检测未积累前返回空 days
- `GET /api/v1/visits?start_at&end_at` — 访问段（place、started_at/ended_at、duration、status）
- `GET /api/v1/points/tracked_months` — 有数据的月份
- `POST /api/v1/areas`、`GET /api/v1/areas` — 地理围栏区域

## iOS 上报数据特征（实测）

- iOS Dawarich app 走显著变化定位：**室内/静止不产生轨迹点**——工作日白天在公司可能数小时无点，夜间在家也只有零星点
- 稀疏日 12–14 点/天，密集日 250–400 点/天（app 是否在前台/追踪模式差异）
- 每天**最后一个轨迹点几乎总是在家**（最可靠的家的证据）；每天**第一个点通常已离家 ~500m+**（iOS 要移动一段才唤醒上报）
- app 不自动续传时数据会断档；手动补传后历史点带原始时间戳入库（`import_id` 为空，tracker_id 是设备 UUID）
