---
name: llm-distill
description: 从 build-api-proxy 网关的 history.db 请求留档中按天蒸馏团队经验（默认聚焦 Unreal/UE 项目），产出按日期归档的 Markdown 到 ~/llm-distill/。当用户提到"蒸馏 LLM 历史"、"分析网关留档"、"蒸馏 history.db"、"总结团队经验"、"llm-distill"、"继续蒸馏"、"蒸馏某一天/昨天的记录"时触发。即使用户只说"接着上次蒸馏"、"再蒸一天"、"把 LLM 对话里的经验捞出来"也应触发。依赖 build-api-proxy skill 的运维细节（容器名、docker exec、数据卷）。
---

# llm-distill：网关留档 → 按日经验蒸馏

## 是什么

build-api-proxy 把全团队所有经网关的 LLM 请求**完整留档**（含请求/响应原文）在 `history.db`。本 skill 把这些对话按天蒸馏成可复用的经验文档，产出到 **`~/llm-distill/<YYYY-MM-DD>.md`**，一天一个文件。

## ⚠️ 两条铁律

1. **30 天正文保留窗口**：`HISTORY_RETENTION_DAYS` 默认 30，超期记录**删正文留元数据**——更老的日期只剩 token 统计，无内容可蒸。蒸馏前先查正文完整率（见 references/extraction.md），空壳日期直接跳过并记录。**优先蒸最老的可用日期**（从旧往新），因为时间越久越接近被清。
2. **隐私敏感**：留档含全团队对话明文（代码、提问、可能粘贴过的密钥）。蒸馏产物是**经验条目**而非对话原文——不要把大段原文、密钥、个人隐私拷进产物 md。产物目录 ~/llm-distill/ 不要对外分享原始 transcript。

## 双产物结构

一天蒸馏产出**两层**：

```
~/llm-distill/
├── <YYYY-MM-DD>.md        # 层1：经验蒸馏汇总（全团队，条目制）
└── <YYYY-MM-DD>/          # 层2：每人当天工作详录
    ├── liyaohan.md        # 文件名 = key_name（归属人）
    ├── xuzhiyang.md
    └── ...
```

- **层1（经验条目）**：跨人汇总，只收可复用经验，标准见 references/analysis.md。
- **层2（每人详录）**：**事无巨细**记录这个人当天做了什么——目标、过程、关键转折、结论、遗留。它的使命是让读者能判断层1每条经验"是怎么被提取出来的、是通用规律还是特定 case"，所以层2 要保留完整过程链（包括走过的弯路），层1 条目用 `—— 来源成员` 回链到层2 对应文件。
- **思维链精选（跨两层）**：留档里约 3/4 的请求带 LLM thinking 块（distill_extract.py 以 `[thinking]` 前缀抽取，每块截 1500 字）。精读时若发现**解决问题的思路本身特别精彩**（漂亮的假设链、四两拨千斤的验证手段、从矛盾现象到根因的跳跃），单独标记收录——这是让团队学习"agent 怎么思考问题"的素材，与技术经验分开收录。标准与格式见 references/analysis.md「思维链精选」。

## 流程（一天）

### 1. 选日期并确认可蒸

```bash
docker exec -i build-api-proxy python3 << 'EOF'
import sqlite3
c = sqlite3.connect('/app/data/history.db')
r = c.execute("""SELECT COUNT(*), SUM(CASE WHEN LENGTH(COALESCE(request_body,''))>10 THEN 0 ELSE 1 END)
 FROM request_history WHERE ts LIKE '<DAY>%'""").fetchone()
print('<DAY>', 'total', r[0], 'purged_or_empty', r[1])
EOF
```

同时看 ~/llm-distill/ 里已有哪些日期文件，避免重复；选"最老的、正文完整率 >0、还没蒸过"的一天。完整率低（<40%）时在产物 md 头部注明覆盖偏差。

### 2. 提取会话 transcript

把 `scripts/distill_extract.py` 拷进容器执行（**默认全量提取不过滤**——蒸馏目标是每人全量工作记录，关键词过滤会漏非 UE 内容；两阶段：按 session 去重取最长快照 → 再按"首个用户提问 hash"二次去重合并同对话的反复快照）：

```bash
docker cp <skill_dir>/scripts/distill_extract.py build-api-proxy:/tmp/distill_extract.py
docker exec build-api-proxy rm -rf /tmp/distill
docker exec build-api-proxy python3 /tmp/distill_extract.py <DAY>           # 全量
docker exec build-api-proxy python3 /tmp/distill_extract.py <DAY> ue,uproject  # 可选：只在需要定向时用关键词
docker cp build-api-proxy:/tmp/distill /tmp/distill
```

产物：`/tmp/distill/*.txt`（每会话一个文件，`index.tsv` 含大小索引）。耗时几分钟（一天约 4-12GB 正文）。

### 3. 建话题索引，挑精读对象

```bash
python3 <skill_dir>/scripts/topic_index.py /tmp/distill > /tmp/topics.txt
```

按文件大小排序读索引：**>100K 的交互式长会话是经验富矿**；自动化机器人流量（skill 抽取 sub-agent、slug 生成、"reply with exactly: ok" 等）直接跳过。机器人流量的识别特征见 references/extraction.md。

### 4. 精读并蒸馏

用 `scripts/session_read.py` 按需抽取单个会话的用户提问、assistant 结论段或思维链：

```bash
python3 <skill_dir>/scripts/session_read.py /tmp/distill/<file>.txt --assistant --tail 4000
python3 <skill_dir>/scripts/session_read.py /tmp/distill/<file>.txt --thinking   # 只看思维链
```

一般一天精读 10-20 个会话足够覆盖主要主题。蒸馏标准与产物模板见 **references/analysis.md**——先读它再动手写。

### 5. 写产物

**先写层2（每人详录）再写层1（经验汇总）**——经验是从详录里长出来的，顺序反了容易凭印象写条目。

层2：按 `key_name` 分组会话文件（文件名前缀即归属人），逐个读该人当天的会话（全部，不止大的；同一个人的机器人碎片可合并略写），写 `<DAY>/<key_name>.md`，模板见 references/analysis.md。**当天无正文（全空壳）或纯机器人流量的人也要建文件**，一句话注明即可，保证"每个人当天是什么状态"可查证。

层1：基于层2 写 `<DAY>.md` 经验汇总，模板同 references/analysis.md。

写完后向用户汇报：本日覆盖情况、经验条数、亮点，以及下一天是哪个日期。

## 参考文件

- **references/extraction.md** — history.db 表结构、关键 SQL、session 去重原理、可选关键词过滤、机器人流量识别、已知坑（容器内查询 OOM 等）
- **references/analysis.md** — 精读方法（transcript 块结构）、经验条目（层1）与每人详录（层2）的质量标准与模板、质量自查清单
- **scripts/distill_extract.py** — 容器内两阶段提取脚本（参数：日期）
- **scripts/topic_index.py** — 宿主机话题索引生成（参数：distill 目录）
- **scripts/session_read.py** — 单会话读取器（--user / --assistant / --thinking / --tail N）
