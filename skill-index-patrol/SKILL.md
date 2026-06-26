---
name: skill-index-patrol
title: SKILL.index.json 巡检
description: 监控 P4 各分支 SKILL.index.json 的 totalFiles 数量，发现减少时通知飞书群并 DM 真正的责任人。当用户提到"SKILL 数量减少"、"巡检漏报"、"谁删了 SKILL"、"patrol 脚本"时触发。
tags: [P4, Feishu, Patrol, SKILL, CI]
---

# SKILL.index.json 巡检

## 脚本位置

```
C:\Users\admin\.violoop\workspace\skill_index_patrol.py
C:\Users\admin\.violoop\workspace\skill_index_patrol_state.json  ← 状态文件
```

Agenda 任务 ID：`agenda_1782391486987_0769ir3ao`（每 5 分钟）

---

## 监控逻辑

1. 读 state 文件中每个分支的 `last_cl` + `last_count`
2. `p4 changes {depot_path}@{last_cl+1},#head` 拿增量 CL 列表
3. 对每个 CL：`p4 print -q {depot_path}@{cl}` 读 JSON，取 `stats.totalFiles`
4. `delta < 0` → 触发告警（群消息 + DM 责任人）
5. 更新 state 文件

**只监控 `stats.totalFiles`**，其他字段（totalSections / totalTags）不报警。

---

## 已知问题 & 修复

### 问题 1：漏检历史 CL（最重要）

**根因**：脚本只扫 `last_cl` 之后的变更。如果问题 CL 发生在基线建立之前，永远不会被检测到。

**复现场景**：
- 巡检任务首次运行时建立 baseline（如 last_cl=108441）
- 问题 CL 108380 发生在 108441 之前 → 永远漏掉

**修复**：`--since-cl` 参数回扫：
```powershell
cd C:\Users\admin\.violoop\workspace
$env:FEISHU_APP_SECRET='...'; $env:P4_SUNLAIBING_PASSWD='...'
python skill_index_patrol.py --since-cl <问题CL号>
```
注意：`--since-cl` 会覆盖所有分支的 last_cl，用完后 state 会更新到最新，不影响后续正常巡检。

---

### 问题 2：告警发给 CI bot 而非真人

**根因**：`CyanCookCI` 是 auto-merge 机器人，它提交的 CL description 里才有真正的责任人。

**auto-merge description 格式**：
```
#auto-merge:manual Rel-0.2->MainDev CL:108372 by LinGuanyu[Audio] ...
#auto-merge: Rel-0.2->MainDev CL:103984 by CyanCookCI ...
```

**BOT_USERS 黑名单**（定义在脚本里）：
```python
BOT_USERS = {'cyancookci', 'administrator', 'cyancookban'}
```

**处理流程**：
```
提交人 CyanCookCI → is_bot() = True
  → extract_real_author(user, desc, cl=CL号) 用正则 CL:(\d+)\s+by\s+([A-Za-z0-9_]+) 提取
  → 短描述匹配失败（p4 changes 截断）→ 自动 p4 describe -s {cl} 拉完整描述重试
  → 得到真人 JiangJiacheng + 原始CL 109169
  → lookup_user_id('JiangJiacheng') 查飞书 open_id
  → DM 发给当事人，说明 "你的 CL 109169 经 auto-merge (CL 109326) 合入后导致数量减少"
```

**⚠️ 关键坑：`p4 changes` 描述截断（已修复）**

`p4 changes` 返回的描述字段默认只保留 ~31 个字符：
```
#auto-merge:manual Rel-0.2->M    ← 截断在这里
```
完整描述实际是：
```
#auto-merge:manual Rel-0.2->MainDev CL:109169 by JiangJiacheng entry-design skill update
```

**修复**：`extract_real_author` 在短描述正则匹配失败时，自动调用 `get_full_desc(cl)`（`p4 describe -s {cl}`）获取完整描述再重试。调用方**必须传 `cl=` 参数**，否则回退无法触发：
```python
real_user, orig_cl = extract_real_author(a['user'], a['desc'], cl=a['cl'])
```

如果 bot 套 bot（CyanCookCI 的 CL by CyanCookCI），`real_user` 仍为 bot → fallback 群里提醒。

---

## 用户信息查询

**不用 p4 email，直接查内部 API**：
```
GET http://192.168.2.13:5000/user/get_userinfo_by_p4id/{p4_userid}
```

返回：
```json
{
  "result": {
    "userid": "ou_a8df36499532f60666df651259582a8e",  ← 飞书 open_id
    "full_name": "林冠宇",
    "p4_userid": "linguanyu",
    "is_resigned": false
  },
  "status": { "code": 0 }
}
```

**注意大小写**：API 不区分大小写（LinGuanyu / linguanyu 都能查到），但 p4 用户名区分，建议直接把原始 p4 用户名传给 API。

---

## 诊断 checklist

| 现象 | 排查步骤 |
|------|----------|
| 某个 CL 导致数量减少但没有告警 | 检查 state 里 `last_cl` 是否晚于问题 CL；用 `--since-cl` 回扫 |
| DM 发给了 CyanCookCI/Administrator | 检查 `BOT_USERS` 是否包含该账号；检查 description 格式是否被正则覆盖 |
| `Could not find Feishu user` | `Invoke-RestMethod http://192.168.2.13:5000/user/get_userinfo_by_p4id/XXX` 手动验证；注意 p4 用户名大小写 |
| 脚本 exit code 1 极短退出 | agenda taskType 是否 `generative`（不能是 `command`，Windows 下会找 /bin/bash） |
| 想查某 CL 在该文件的 totalFiles | `p4 -p 192.168.2.236:1666 -u sunlaibing print -q //CyanCookOfficialDepot/MainDev/SKILL.index.json@<CL>` 后解析 JSON |

---

## 分支配置

```python
BRANCHES = {
    'MainDev': '//CyanCookOfficialDepot/MainDev/SKILL.index.json',
    'Rel-0.2': '//CyanCookOfficialDepot/Rel-0.2/SKILL.index.json',
}
```

新增分支直接在脚本 `BRANCHES` 字典里加一行。
