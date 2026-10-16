# 导表快车道（table_export_fastpath）白名单契约与归因

机制权威文档在 pyAutomation 仓：`pyAutomation/backend/server/applications/ai_review/references/table-export-fastpath.md`。
本页只沉淀「为什么某 CL 没走快车道」的归因契约；行号以 2026-10 线上版本为准。

## 入口与闸门

- 入口链：`ai_worker.py:696` → `try_complete()` → `enabled_for()`（要求 shelved + MainDev + `need_compile=false`）→ 对 shelf 取证快照 → `classify()`。
- 满足 `enabled_for()` 不代表会走快车道：只是"尝试了"，最终由 `classify()` 白名单判定。排查"没走快车道"先区分是闸门不满足（未 shelved / 非 MainDev / need_compile=true）还是分类 fail-closed。

## 白名单契约（`classify()` → `_allowed_paths`，:183）

仅放行以下五类，且**全部文件**都必须落在白名单内：

1. `Main/RawData/dt_metadata.json`；
2. 变化的工作簿 xlsx 本身（`Main/RawData/Editor/**.xlsx`）；
3. 仅由变化工作簿按命名契约可推导的既有产物：`{PIPELINE}{dir}DT_{tag}.uasset`（PIPELINE = `003_DataTablePipeline/Editor/`）；
4. 字符串表；
5. AutoGen 标签代码（另有独立开关与版本门，RULE_VERSION 变更作废旧证明）。

**Fail-closed**：任何一个文件落不出白名单 → `not_applicable: uncontrolled_file`（:307），`try_complete` 记 `table export <cl>: uncontrolled_file` 后返回 False，回落完整评审链（ai_analysis + Flow build）。日志里的 reason code 是归因第一手证据。

## 必然踢出快车道的常见手改资产

- `000_GlobalSettings/DataTables/**/PLID_*.uasset` 等手改 DataAsset：不在 PIPELINE 下、不符合 DT_/DA_ 命名契约，无法从变化工作簿推导；
- `007_Entities/**/BP_*.uasset` 等蓝图：不是导表产物；
- 任何不随 metadata 推导关系出现的其他路径。

设计意图：快车道摘要明示「未运行 AI/编译，**不审查业务行内容**」，只放行"每个文件都能被证明是受控再生产物"的 CL。正确用法是拆 CL——纯导表（metadata + xlsx + 可推导 DT/DA）单独一个 CL 走脚本秒过，手改资产另提 CL 走正常评审。

## 已确认根因案例

- Review 1553 / CL 138844（2026-10）：19 文件中 7 个 `PLID_Entity_*.uasset` + 8 个 `BP_Storage_*.uasset` 为手改资产，fail-closed 判 `uncontrolled_file` 回落完整链。属设计行为，不是 bug。

## 相关

- 快车道全生命周期约 2 秒 < 客户端 watcher 10 秒轮询，导致本地不收口（Review 1089 根因，见 SKILL.md 对应 memory）。
