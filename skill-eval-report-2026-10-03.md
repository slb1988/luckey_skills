# Skill Health Report — 2026-10-03

## 整改记录 — 2026-10-04（文档与本地静态校验）

相对报告提交 `1dee18f`，按 `.claude/plans/Skills静态健康整改.md` 的本轮范围整改。**下方 52 / 16 / 11 评级及逐项记录是 2026-10-03 历史基线，不是整改后的重新评分**；本轮没有重跑内容评分、Tier 2、A/B、线上运维或真实业务示例，不据结构通过宣称技能业务可靠或部署完成。

### 已完成

- `automerge-clean`：删除 SKILL 示例里的明文密码，改有效 P4 ticket / 仓库外受保护环境注入；保留账号和连接设置，未改真实密码、未轮换、未执行清理。基线中的轮换建议不是本轮操作授权。
- 三个 auto-server 发布入口：命令前要求核对 host/user/cwd，异机先路由；不再凭回环解析断言当前会话在目标机。backend 手动配方连续两次明确空闲才放行，HTTP/JSON/字段异常重置计数，5 分钟到期失败退出，不再继续停服；这不代表线上 deploy.sh 被修改或验证。前端回执区分“产物就绪”和“线上生效已核验”。
- 四个 vault 入口：按现行 `luckey/AGENTS.md`、routing/metadata 规则、Daily Notes 配置及已归位文件修正路径，不写 vault。日记为 `02_notes/daily`，书籍为 `04_sources/books`，学习计划为 `03_projects/personal/learning`；Violoop 继续写既有 `02_notes/software/violoop/user-feedback-20260702.md`，不另造日文件。新生成估值稿区分 `09_generated` 与确认保留的个人投资记录，旧稿保持稳定路径；学习阶段改为正文记录，不重引入废弃 YAML 字段。
- 修正 git-tool 重复 `git`、langfuse 多镜像单次 pull、memory-review 的 9287/9288 review 路由冲突、Flux 尺寸倍数/比例。diagram-design 将 4px 网格限定为主要节点布局，明确字体和 primitive 例外，不改视觉风格；Luckey 出图前检测工具，无 `image_gen` 时必须如实标注未出图。
- 11 份基线结构失败入口：展示元数据移入 `metadata`（保留原值、name、触发描述及已有 metadata），print compatibility 改字符串，orchestration-ops description 去尖括号。`skill-harvest` 的 `disable-model-invocation: true` 仍在顶层，人工触发语义不变。
- 四份长入口按需拆到 8 份 references，保留 Office cookbook 示例、Diagram 六条连线规则/风格门/交付契约、Huashu 三方向真实初稿→用户选择→Gate 文件及媒体安全契约、skill-creator 环境适配。澄清持久测试用 `evals[].expectations`、运行 metadata 用 `assertions`、评分用 `grading.json.expectations`，没有混改 schema。

### 结构校验口径与结果

本机安装的 Pi `docs/skills.md` 明确支持顶层 `disable-model-invocation: true`，`dist/core/skills.js` 以 `=== true` 读取。为保留该行为，`quick_validate.py` 默认使用**项目 Pi 兼容口径**：只额外接受这个具体键，并严格要求 YAML boolean；未知键仍拒绝。新增 `--strict` 保留原本地白名单口径，**不将任一口径冒称为上游标准全面认证**。

| 检查 | 实测结果 |
|---|---|
| 与历史报告相同的递归入口（含 6 份嵌套，不含 skill-eval 自身） | 79 份；兼容口径 79 通过；原严格白名单 78 通过 + 1 个明确例外（skill-harvest） |
| 加上 skill-eval 自身 | 全项目 80 份；兼容口径 80 通过；严格白名单 79 通过 + 上述 1 个例外 |
| 四份入口正文 / 整文件行数 | office-js 88 / 97；diagram-design 443 / 451；huashu-design 418 / 423；skill-creator 472 / 477；均 <500 |
| 新增本地回归 | validator 6 tests + scoped static 10 tests，全部通过；其中 busy gate 含 8 组 stub fixture |
| 移文保真 | Office 三本 cookbook、skill-creator 环境适配、Huashu 两段详细流程、Diagram primitive 示例及六条连线规则与基线逐段比对通过（仅引用迁移和明确整改条款除外） |
| 引用与矛盾检查 | 新增/改动 Markdown 链接目标存在；活动旧路径、重复命令、端口/尺寸/网格矛盾的局部断言通过 |
| 许可文件完整性 | 以下四份文件 SHA-256 与整改前一致，4/4；测试内固定基线哈希 |
| Git 空白检查 | `git -C .agent/skills diff --check` 通过 |

可重现命令（从 ObsidianVault 根目录运行；只执行本地校验，示例业务命令不执行）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .agent/skills/skill-creator/tests -p 'test_quick_validate.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .agent/skills/skill-eval/tests -p 'test_static_remediation.py' -v
python3 .agent/skills/skill-creator/scripts/quick_validate.py .agent/skills/skill-harvest
python3 .agent/skills/skill-creator/scripts/quick_validate.py --strict .agent/skills/skill-harvest
# 最后一条预期 exit 1：仅严格白名单不接受该宿主行为键，并非兼容回归失败。
git -C .agent/skills diff --check
```

busy fixture 只提取文档中的等待函数，以本地函数替代 curl 和时钟等待，停服门后仅打印哨兵；没有请求真实端点、kill、P4、Docker、部署、打印或外发。静态复核不是运行时/视觉验收。安全检查仅针对本次变更，报告只保留位置和处理边界，不记录凭据值；不声称完成全库 secrets 审计。

### 用户已接受的保留项（不列待修或提交阻塞）

本轮 Kimi K3 **新增**的凭据发现已获用户明确许可。以下原文件保持字节不变，不删除/脱敏改写、不轮换其中凭据，不把它们继续列为待修或提交阻塞，也不把实际值复制进本报告或新参考资料：

- `qnap-perforce/references/p4d-server.md`
- `frp-tunnel-setup/references/frp-setup-record.md`
- `frp-tunnel-setup/references/frp-client-binding.md`
- `memory-hub/references/deploy.md`

授权只覆盖本轮新增项，不扩展至原报告的 automerge-clean 明文示例或其他未获许可凭据。第三方 axton 子模块、生产服务/配置、vault 笔记、`.obsidian`、主库其他会话改动未修改；提交和推送由协调者另行执行。

### 未执行 / 后续范围

全量 benchmarks、标准 eval 覆盖扩充、其他低于 500 行入口的额外拆分、部署/清理算法的真实行为验证均未执行，不是本轮完成声明的一部分。原报告的测试覆盖数字及剩余建议仍作为历史记录保留；此处没有生成第二份总结报告。

---

## 以下为 2026-10-03 历史基线（原评级与证据保留）

**Skills scanned: 79 份 SKILL.md（78 个去重 name）；不含 skill-eval 自身。**

**结论：功能描述普遍清楚，但静态高分不等于实际可靠；当前优先级是凭据、危险操作门禁和过期路径，然后统一元数据与补评测。**

| Rating | Count | Skills |
|---|---:|---|
| Healthy | 52 | `a-stock-quant`, `ai-review`, `anki`, `asus-merlin-vpn`, `build-api-proxy`, `clash-verge`, `curate-luckey-vault`, `daily-report`, `extract-shirt-pattern`, `find-skills`, `frontend-slides`, `frp-tunnel-setup`, `game-char-art`, `game-dev`, `hearthstone-pack-analyzer`, `insight-daily`, `investment-monitor`, `jira`, `karpathy-guidelines`, `kid-learning-journey`, `kid-learning-princess-theme`, `lldap`, `llm-distill`, `mac-awake`, `memory-center`, `mermaid-diagrams`, `mihomo-proxy-setup`, `nginx-local-server`, `oss-upload`, `pi-agent`, `pyauto-aireview`, `pyauto-shared`, `qnap-git-setup`, `qnap-nas`, `qnap-perforce`, `ragflow`, `ragflow-deploy`, `skill-creator`, `sub2api-server`, `teamcity-extract-commandlet`, `teamcity-tool`, `temporal-server`, `ue-launcher-toolbox`, `video-downloader`, `vscode-as`, `wireguard-setup`, `write-article`, `zen-server`, `axton-obsidian-visual-skills/excalidraw-diagram`, `axton-obsidian-visual-skills/mermaid-visualizer`, `axton-obsidian-visual-skills/obsidian-canvas-creator`, `frontend-slides/plugins/frontend-slides/skills/frontend-slides` |
| Needs work | 16 | `auto-server-backend-deploy`, `auto-server-deploy`, `auto-server-frontend-deploy`, `automerge-clean`, `cli-anything-obsidian`, `git-tool`, `huashu-design`, `investment-analyzer`, `langfuse-server`, `learn-10x`, `luckey-illustration`, `memory-review`, `office-js`, `text-to-image-prompt`, `violoop-report`, `diagram-design/skills/diagram-design` |
| Incomplete | 11 | `agent-sdk`, `drawio-skill`, `memory-hub`, `merge-engine-skills`, `orchestration-ops`, `post-to-wechat`, `print`, `skill-harvest`, `skill-index-patrol`, `ue-blueprint-reflection`, `.claude/skills/add-github-submodule` |

## 范围、方法与评分口径

- 审计目录：`/Users/sun/Documents/ObsidianVault/.claude/skills`；源快照：`30250a85167ad93f177dda53d5485d71328391d0`。
- `scan_skills.py --exclude skill-eval` 找到 73 份顶层入口：48 Healthy / 15 Needs work / 10 Incomplete。
- 扫描器仅认 `<root>/<name>/SKILL.md`，故只读递归补查 6 份嵌套入口：4 Healthy / 1 Needs work / 1 Incomplete。实际活跃的 `diagram-design/skills/diagram-design/SKILL.md` 也属于该遗漏。未修改扫描器。
- 两份 frontend-slides/SKILL.md 字节级 SHA-256 相同，是根入口与插件镜像；按文件计 79、按 name 去重 78。存在镜像不证明运行时重复加载，本次未核查所有宿主的加载配置。
- 不包含用户全局 skills、`.pi/extensions/`、工作区业务模块文档或其他独立克隆；没有把“项目下”扩成整台机器。
- 对 79 份入口逐一运行现有 `skill-creator/scripts/quick_validate.py`，并统计 YAML、正文行数、测试文件、参考目录及本地 Markdown 链接存在性。描述与正文流程/示例/输出约定按 rubric 核对；长文按章节证据选段检查，不是所有代码和参考资料的逐行语义审计。
- 结构失败后停止内容打分，记 Incomplete。其余为描述 0–3、正文 0–3、渐进披露 0–2，共 8 分；7–8 Healthy，4–6 Needs work，低于 4 Incomplete。确认的安全/契约冲突可将 7–8 分降为 Needs work，理由逐项列出。
- 正文行数不含 frontmatter 与开头空白；“低于 500 行”按严格小于 500 计算。无 references 目录不自动扣分，短小自包含技能无需为了得分拆文件；只有大型内联参考扣分。
- 输出约定可以是返回值、文件名/内容结构或验收字段，不强制每个技能都生成报告。明确路由到的参考可作为证据，例如 ue-launcher-toolbox 的构建/交付规范。
- 所有入口的 name/description 均非空；不把 quick_validate 对空字符串的检查缺口当作合格证据。11 个失败主要是严格 schema 差异，不代表这些技能在当前 Pi 一定无法加载。
- 未运行 Tier 2、线上业务、部署、图像生成、真实通知或 benchmark；不报告通过率、时间/token 增益。不据历史 eval-workspace 产物声称本轮测试通过。
- 未修改任何技能正文、脚本或配置；本轮产物仅本报告。未穷举 secrets：下列明文凭据是在正文静态检查中发现，报告不包含其值。

## Skills Needing Immediate Attention

### P0：凭据暴露

- **automerge-clean**：已跟踪文件 `automerge-clean/SKILL.md` L33、45、53、61、69、76–78、88、94–97、108、111 直接写入 P4 密码。应改受保护配置注入，并由负责人确认轮换与历史暴露处理；本次未验证密码有效性，未改密码、删历史或强推。Git 对 .env 的忽略保护不会识别这种正文硬编码。

### P1：可直接误导执行的正文

- **auto-server-backend-deploy**：L111–121 手动等待到期后没有失败退出，仍执行 kill -9；一次空闲即可退出循环，与 L29 的连续两次空闲/超时放弃不符。此结论仅针对文档中的手动配方，不推断线上 deploy.sh 有同样问题。
- **auto-server-deploy / auto-server-frontend-deploy**：前者 L10、后者 L50 无条件声称当前机器就是 auto-server。后者还与 L8 的先确认主机规则冲突；需把 host/cwd 确认和异机路由放到命令前。
- **cli-anything-obsidian / investment-analyzer / learn-10x / violoop-report**：仍指向 `002 Cards`、`003 Books`、`301 Daily Notes`、`210 Learning & Reading` 或 `110 Utilities/violoop`。现行项目规则已使用 `02_notes`、`04_sources` 等；本次确认 `luckey/002 Cards`、`luckey/210 Learning & Reading`、`luckey/110 Utilities/violoop` 不存在。应按 `00_meta/rules` 与真实 Obsidian 配置路由，不能重建废弃目录。

### P1：11 份严格元数据校验失败

| 类型 | 入口 | 处理方向 |
|---|---|---|
| 不在校验器白名单的顶层字段 | agent-sdk、drawio-skill、memory-hub、merge-engine-skills、post-to-wechat、skill-harvest、skill-index-patrol、ue-blueprint-reflection、嵌套 add-github-submodule | 区分目标宿主支持的行为字段和展示元数据；title/tags/version 等可归 metadata，不应无脑删除行为键。 |
| description 含尖括号 | orchestration-ops | 把占位命令写成 `orca COMMAND --help` 等不含尖括号的形式。 |
| compatibility 类型是 list | print | 改字符串/折叠文本，保留平台能力信息。 |

特别注意：skill-harvest 的 `disable-model-invocation` 属行为语义，先确认宿主与校验器的兼容策略，不应为了“通过”而机械搬到 metadata 导致行为丢失。

### P2：清晰的文档冲突与环境缺口

- **git-tool**：失效 nested submodule 清理例多了一个 `git`，形成 `git -C ... git rm -f`。
- **langfuse-server**：L53 将两个镜像一次传给 `docker pull`，需拆成两次或改 compose pull 服务。
- **memory-review**：L193 给 :9287 review 入口，紧接着 L194–195 又说其 404、应走 :9288。需只保留当前有效指引；本次没有连线上做端口验证。
- **text-to-image-prompt**：L111 的 32 倍数限制与 1920×1080 示例冲突（1080 % 32 = 24）。
- **diagram-design**：强制 4px 网格与自身 7px/9px 字体样例冲突；先统一约束/例外再要求执行。
- **luckey-illustration**：强制内置 image_gen，但本次 Pi 工具列表没有它，需能力检测/替代入口或明确阻塞，不能把提示词当已生成图片。

### P2：入口减负

| 入口 | 正文行数 | 建议 |
|---|---:|---|
| office-js | 619 | 按 Excel/Word/PowerPoint 外置 cookbook。 |
| diagram-design | 574 | 外置 SVG primitives、布局与详细检查清单。 |
| huashu-design | 529 | 外置媒介流程、Fallback 与素材门禁细则。 |
| skill-creator | 503 | 略超线；外置环境适配段即可，其余渐进披露较好。 |

memory-center、qnap-nas 与嵌套 excalidraw-diagram 虽低于 500 行，仍存在长参考/重复模板内联，逐项建议见后文。

## Eval Coverage

**8 / 79 份入口存在 evals/evals.json（10.1%；按去重名称为 8 / 78，10.3%），共 28 个测试用例。**

| Skill | Cases | 带结构化 expectations 的 cases | Expectations 条数 |
|---|---:|---:|---:|
| ai-review | 3 | 0 | 0 |
| frp-tunnel-setup | 3 | 0 | 0 |
| game-dev | 3 | 0 | 0 |
| jira | 3 | 0 | 0 |
| pyauto-aireview | 7 | 7 | 27 |
| pyauto-shared | 2 | 2 | 8 |
| ragflow | 4 | 0 | 0 |
| vscode-as | 3 | 3 | 15 |

- 8 份 JSON 均可解析，28 例都有 prompt 和 expected_output。3 个技能的 12 例还含共 50 条结构化 expectations；其余 16 例是 prompt + 人读预期，不能视为已完成客观评分。
- 本地 `skill-creator/references/schemas.md` 将测试断言字段定义为 `evals[].expectations`；没有因为它们未命名 assertions 就报错。skill-creator 正文的字段称呼建议统一。
- 缺少这个标准测试文件不代表没有 pytest、自测脚本、视觉案例或历史 benchmark；本表仅度量标准化 skill eval 覆盖。
- 可通过 `/skill-creator` 补测试。优先为凭据/部署/清理类补安全负例，其次给高频技能补正常、异常、边界 2–3 例；真实运维、外发、付费 API 必须隔离或 mock。

## 完整逐项结果

以下先列顶层入口，再列补查的嵌套入口。N/A 表示结构门禁未过，未作内容评分。

---

## a-stock-quant

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/a-stock-quant`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：160 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L41–49：采集、复盘、周频执行与回测命令。
- ✅ 具体示例/场景：L30、48：带具体日期的回测示例。
- ✅ 输出格式/产物约定：L34：data/ 下 Markdown/JSON 报告与账户数据。

### Progressive Disclosure [2/2]
- ✅ 正文 83 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补模拟盘正常复盘、数据缺失和非调仓日的评测；明确 Windows 部署路径与当前执行机的区别。


## agent-sdk

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/agent-sdk`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: tags, title. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 180 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## ai-review

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/ai-review`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：257 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L10–68：定范围、准备证据、只读评审、获准后修复复审。
- ✅ 具体示例/场景：L24–27：Kimi 审 Codex、切换 reviewer 的具体场景。
- ✅ 输出格式/产物约定：L44–59：评审任务模板及文件/行号、证据、模型身份等返回字段。

### Progressive Disclosure [2/2]
- ✅ 正文 85 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 3 test cases；其中 0 例含结构化 expectations，共 0 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将现有 3 个 prompt 补成可判定的 expectations，覆盖指定模型不可用时不得静默替换。


## anki

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/anki`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：321 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L18–46：连接、发现牌组和字段、去重、写后回读。
- ✅ 具体示例/场景：L76–129：7+5、9+6 的 Basic 卡片及批量 JSON。
- ✅ 输出格式/产物约定：L98–129：addNotes 的 note/fields/tags 内容形态明确，L175–176 要求临时 payload 与回读。

### Progressive Disclosure [2/2]
- ✅ 正文 178 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补重复卡、模型字段不匹配和写后回读的 fixture 评测，避免直接污染用户牌组。


## asus-merlin-vpn

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/asus-merlin-vpn`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：518 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [2/3]
- ✅ 步骤级指引：L21–30：凭据、状态快照、订阅及网络诊断的顺序。
- ✅ 具体示例/场景：L36–50：安全停止、恢复管理访问及切换节点命令。
- ❌ 输出格式/产物约定：有验证命令，但未定义最终汇报应含哪些字段。

### Progressive Disclosure [2/2]
- ✅ 正文 54 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补简短交付约定：修改项、路由器侧连通证据、当前节点/模式、回滚方法，禁止回显凭据。
2. 为 DNS 故障和管理面失联设计无真实写入的评测。


## auto-server-backend-deploy

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/auto-server-backend-deploy`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：224 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L24–35：同步、空闲门禁、停服、归档、轮转、启动。
- ✅ 具体示例/场景：L102–140：完整手动部署示例。
- ✅ 输出格式/产物约定：L142–156：PID 与 HTTP 状态验证输出。

### Progressive Disclosure [2/2]
- ✅ 正文 241 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L111–121 的手动等待循环到期后仍继续 kill -9，且一次空闲即退出；与 L29 的连续两次空闲、超时放弃约定不一致。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 优先删除危险的手动等待副本，统一委托权威部署脚本；如保留，超时/探活失败必须退出并落实连续两次空闲。
2. 增加始终 busy、HTTP 失败、短暂空闲三种零副作用门禁评测。


## auto-server-deploy

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/auto-server-deploy`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：229 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L24–46：后端委托与前端同步构建流程。
- ✅ 具体示例/场景：L18–22：一键部署及显式跳过门禁的场景。
- ✅ 输出格式/产物约定：L117–136：后端/前端验证输出示例。

### Progressive Disclosure [2/2]
- ✅ 正文 175 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L10 无条件断言当前 pi 就在 auto-server 并禁止 SSH；本次实际 cwd 是 Mac，通用技能不能把目标机历史描述当当前运行事实。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 把先核实实际 host/cwd 写成入口门禁，异机时按项目路由执行；只有确认在 auto-server 后才使用本地部署命令。
2. 补非目标主机不得本地部署的评测。


## auto-server-frontend-deploy

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/auto-server-frontend-deploy`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：148 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [2/3]
- ✅ 步骤级指引：L18–35：P4 同步后构建。
- ✅ 具体示例/场景：L22–34：明确工作目录和同步/构建命令。
- ❌ 输出格式/产物约定：L37 只说构建产物生成即完成，未给产物路径和发布回执结构。

### Progressive Disclosure [2/2]
- ✅ 正文 49 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L8 要求先确认主机，但 L50 又断言当前机器就是 auto-server，入口与末尾相矛盾。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 删去无条件的当前主机断言，保留实际 host 检查。
2. 补 dist 产物、版本/构建结果、实际页面可达性及未验证项的简短回执。


## automerge-clean

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/automerge-clean`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：219 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L48–104：opened、revert、清理 add 文件、删除空 CL、核验。
- ✅ 具体示例/场景：L42–45：一键清理命令。
- ✅ 输出格式/产物约定：L104–111：no opened files / nothing to reconcile 验收形态。

### Progressive Disclosure [2/2]
- ✅ 正文 114 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** 已跟踪的 SKILL.md 在 L33、45、53 等多处内嵌明文 P4PASSWD；不在报告中复制其值，也未验证凭据是否仍有效。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 最高优先级移除文档和命令中的明文密码，改用受保护配置/凭据注入；由负责人确认轮换，评估历史暴露，勿擅自重写 Git 历史。
2. 补确认目标 client、只列清单与明确授权后清理的安全评测。


## build-api-proxy

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/build-api-proxy`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：313 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [2/3]
- ❌ 步骤级指引：主体是部署信息和独立查询命令，缺少从症状到定位、处置、复验的短序列。
- ✅ 具体示例/场景：L50–67：用量聚合及按 request_id 取记录示例。
- ✅ 输出格式/产物约定：L41–45 给出留档字段，L57–60 指定用量聚合输出。

### Progressive Disclosure [2/2]
- ✅ 正文 92 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补 3–5 步只读排障流程：核主机、取元数据、定位异常、获准处置、复验；不要默认读取完整团队会话。
2. 增加隐私脱敏和留档保留窗口的评测。


## clash-verge

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/clash-verge`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：226 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L28–39：端口、对照请求、出口、节点、持久化五步排障。
- ✅ 具体示例/场景：L40–51：目标与对照站点返回码的场景表。
- ✅ 输出格式/产物约定：L109–114：API 字段 now/all 和请求体形态。

### Progressive Disclosure [2/2]
- ✅ 正文 112 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补直连/代理/TUN 假通对照评测；将 TLS 超时等现象写成待对照验证的假设，避免单一现象直接定因。


## cli-anything-obsidian

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/cli-anything-obsidian`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：493 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L11–28：CLI 可用性检查、vault 与路径参数选择；L65–78 给 fallback。
- ✅ 具体示例/场景：L33–53：读写、每日笔记、检索与任务操作示例。
- ✅ 输出格式/产物约定：L57–78：笔记目录和 Python 创建笔记的内容形态。

### Progressive Disclosure [2/2]
- ✅ 正文 132 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L57–78 仍把 002 Cards、003 Books、301 Daily Notes 当现行目录，并在创建示例中使用旧路径；与项目现行 02_notes/04_sources 等规则冲突。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 优先从 luckey 的现行规则和 Obsidian daily-notes 配置解析目录，替换旧目录表及创建示例。
2. 把 UE 工具安装清单与 cli-hub 兼容性记录移到相关参考，避免每次操作笔记都加载无关内容。


## curate-luckey-vault

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/curate-luckey-vault`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：517 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L12–26、42–50：先读规则/扫描再归位，保护并行修改。
- ✅ 具体示例/场景：L19–23 的扫描示例、L69–71 的知识归档映射。
- ✅ 输出格式/产物约定：L83–87：目的地、知识与实际校验结果的回报。

### Progressive Disclosure [2/2]
- ✅ 正文 82 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 增加旧链接修复、只读请求不写入、重复笔记合并的 fixture 评测；统一 .agent/.agents 入口示例。


## daily-report

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/daily-report`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：126 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L34–201：日期、AW、P4、合并、工时、表格、写入与回报。
- ✅ 具体示例/场景：L97–101：DailySucc 与 CL 子项示例。
- ✅ 输出格式/产物约定：L149–173：工时/应用表格式；L201：路径、数量和覆盖时段。

### Progressive Disclosure [2/2]
- ✅ 正文 196 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 优先补跨午夜、数据源缺失和已有日记合并评测；去重重复的 CL 号纠错规则。


## drawio-skill

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/drawio-skill`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: homepage, platforms, version. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 475 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## extract-shirt-pattern

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/extract-shirt-pattern`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：403 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L16–21：看图、定向、裁剪、运行、复看、交付。
- ✅ 具体示例/场景：L27–33：带裁剪和旋转参数的脚本示例。
- ✅ 输出格式/产物约定：L44–51：PSD/PNG 产物名明确。

### Progressive Disclosure [2/2]
- ✅ 正文 59 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补小尺寸合法图片 fixture，检查透明通道、PSD 可读性与图层产物，而非仅凭主观美观评分。


## find-skills

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/find-skills`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：156 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L52–79：理解、搜索、呈现安装入口及无结果兜底。
- ✅ 具体示例/场景：L62–65：React 性能、PR review、changelog 三个查询例。
- ✅ 输出格式/产物约定：L69–73：返回相关技能和可复制安装命令。

### Progressive Disclosure [2/2]
- ✅ 正文 74 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补有结果、无结果和发现安装风险时的评测；区分提供安装命令与实际获准安装。


## frontend-slides

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/frontend-slides`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：311 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L67–261：新建/转换/修改分流，内容发现、预览选择、生成与交付。
- ✅ 具体示例/场景：L60–61：演讲型与阅读型 deck 场景；L305–307：部署示例。
- ✅ 输出格式/产物约定：L222、261 起：单文件 HTML、浏览器检查与交付；导出 PDF 有独立命令。

### Progressive Disclosure [2/2]
- ✅ 正文 375 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补修改既有 deck、手机视口和 PPT 转换的评测；维持按选择加载模板，不一次性读模板库。


## frp-tunnel-setup

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/frp-tunnel-setup`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：348 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L17–81：识别任务、服务端、客户端、映射与两侧验证。
- ✅ 具体示例/场景：L72–79：TOML 端口映射模板。
- ✅ 输出格式/产物约定：L92–94：分别给 VPS/本地命令，以验证与回滚收尾。

### Progressive Disclosure [2/2]
- ✅ 正文 89 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 3 test cases；其中 0 例含结构化 expectations，共 0 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 为现有 3 个 prompt 补可判定 expectations，优先覆盖未认证服务不得暴露公网和端口冲突。


## game-char-art

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/game-char-art`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：204 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L17–30：读设定、拼 prompt、生成、逐图校对、用户选择。
- ✅ 具体示例/场景：L23–26：四张 2048×2048 角色图生成命令。
- ✅ 输出格式/产物约定：L25–30、55–59：目录、prompt.md、selected 和角色 PNG 命名。

### Progressive Disclosure [2/2]
- ✅ 正文 54 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补无 API key 不出网、设定拼接和产物清单评测，图像品质保留人工判断。


## game-dev

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/game-dev`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：246 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L30–36：锁目标、最小证据、玩法、创作实现、试玩、验证与发布。
- ✅ 具体示例/场景：L18：save_one_stroke 真实游戏路由；L33–35 区分关卡数据与新增引擎机制。
- ✅ 输出格式/产物约定：L38–42：修改路径、验证、试玩入口、边界，并明确 prompts 尚待确认。

### Progressive Disclosure [2/2]
- ✅ 正文 33 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 3 test cases；其中 0 例含结构化 expectations，共 0 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 先确认现有 3 个候选场景，再补规则支持性、不得擅自发布等 expectations；不要把候选 prompts 写成已通过测试。


## git-tool

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/git-tool`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：249 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L24 起：commit、sync、嵌套 submodule 和 scoped 提交流程。
- ✅ 具体示例/场景：L46–50：正确/错误的嵌套 submodule 定位例。
- ✅ 输出格式/产物约定：L65–66：只暂存指针并提交的命令；commit-flow 定义提交哈希回执。

### Progressive Disclosure [2/2]
- ✅ 正文 193 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** 移除失效 nested submodule 的示例写成 git -C <parent_submodule_path> git rm -f，重复的 git 子命令会使该步骤失败。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 修正重复 git 的命令示例，并以临时本地 Git 仓测试清理流程。
2. 优先补 detached HEAD、主库无关 untracked 文件、嵌套 submodule 的 scoped 提交评测。


## hearthstone-pack-analyzer

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/hearthstone-pack-analyzer`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：165 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L12–50：登录、数据、收藏匹配、使用率、报告五步。
- ✅ 具体示例/场景：L25–39：收藏 API 和普通卡数量计算示例。
- ✅ 输出格式/产物约定：L52–65：缺失、多余尘、评级和购买建议四块报告。

### Progressive Disclosure [2/2]
- ✅ 正文 60 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补收藏类型/金卡、缺失使用率数据的 fixture 评测，避免请求真实账号作为默认 benchmark。


## huashu-design

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/huashu-design`
**Score:** 6/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：163 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L24–38 路由，L203 起七阶段，L316 起标准流程。
- ✅ 具体示例/场景：L60：具名产品材料验证反例；L243：取图脚本。
- ✅ 输出格式/产物约定：L522–529：文件、状态保持、路径和视觉验证要求。

### Progressive Disclosure [0/2]
- ❌ 正文 529 行；要求 <500。
- ❌ 存在可外置的大型内联参考/重复模板。
- 证据：正文 529 行；Fallback、标准流程、资产门禁与技术细则大段同载，已有 references 但入口仍重。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 保留路由、三个方向的批准门和最短交付链，把 Fallback、资产协议、各媒介流程移到按需 reference。
2. 用评测检查无子 agent/无专用图像工具时能否按既定降级流程交付。


## insight-daily

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/insight-daily`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：167 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L37–43：路径、分节、哈希、input、run、轮询和回执。
- ✅ 具体示例/场景：L49–61：离线验证与 done 输出示例。
- ✅ 输出格式/产物约定：L43–45：run/input id、manifest 和 dashboard 链接。

### Progressive Disclosure [2/2]
- ✅ 正文 68 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补 dry-run 零网络、重复 H2、路径越界、超时保留 run id 的技能行为评测；与脚本单测区分。


## investment-analyzer

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/investment-analyzer`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：179 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L20–94：需求、数据、估值、报告、保存。
- ✅ 具体示例/场景：L36–40：带年月的估值查询场景。
- ✅ 输出格式/产物约定：L56–87：报告及估值地图模板；L93–94：路径与 frontmatter。

### Progressive Disclosure [2/2]
- ✅ 正文 121 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L93 把报告保存到已不存在的 luckey/002 Cards，违背现行 vault 归位规则。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 改为先读 vault routing/metadata 规则后选目录，不重建旧目录。
2. 补数据日期、来源冲突、缺失估值和用户风险条件未明的评测。


## investment-monitor

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/investment-monitor`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：312 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L34–69：运行、无通知模式、调整配置、计划任务与运行记录。
- ✅ 具体示例/场景：L63–66：工作日 18:00 计划任务示例。
- ✅ 输出格式/产物约定：L21、49：每日 Markdown 快照和 monitor_state.json。

### Progressive Disclosure [2/2]
- ✅ 正文 82 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补首次只建基线、阈值跨越、数据源滞后的 fixture 评测，默认禁真实飞书通知。


## jira

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/jira`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：227 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L21–38：解析 Box、缓存、刷新、保存 focus/assist。
- ✅ 具体示例/场景：L60–65：首次、重复查询、链接、序号选择四种场景。
- ✅ 输出格式/产物约定：L26、32–37：任务快照/风险/计划/协作项及工单 Key。

### Progressive Disclosure [2/2]
- ✅ 正文 60 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 3 test cases；其中 0 例含结构化 expectations，共 0 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 为现有 3 个 prompt 补缓存隔离、显式刷新和序号到 Key 映射的 expectations。


## karpathy-guidelines

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/karpathy-guidelines`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：53 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L13–67：澄清、最小实现、小范围改动、验证目标的阶段性指引。
- ✅ 具体示例/场景：L55–58：验证/bug/重构转换成可检查目标。
- ✅ 输出格式/产物约定：L60–65：[Step] → verify: [check] 的简短计划模板。

### Progressive Disclosure [2/2]
- ✅ 正文 61 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 保持简洁；如补评测，重点检查不扩范围、明确假设和失败测试先行，而非强制产出长文档。


## kid-learning-journey

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/kid-learning-journey`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：325 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [2/3]
- ✅ 步骤级指引：L46–50：模块、源码/契约、修改、测试、稳定知识更新。
- ✅ 具体示例/场景：L20–23：正常保存与失败重试 UI 的真实问题场景。
- ❌ 输出格式/产物约定：有目录/契约不变量，但没有最终交付摘要或验证状态的输出约定。

### Progressive Disclosure [2/2]
- ✅ 正文 45 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 保留 45 行索引式正文，补一句交付契约：修改/契约/实际测试/未验证项/是否部署。
2. 优先补 pending_review、家长发布与幂等的行为评测。


## kid-learning-princess-theme

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/kid-learning-princess-theme`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：355 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L12、34–38：读基准、保留批准版、用共享 tokens、验证状态并截图。
- ✅ 具体示例/场景：L30–31：拼音布局与 star-wallet 重叠的具体场景。
- ✅ 输出格式/产物约定：L26、38：desktop/Pad/390×844 适配与桌面/移动截图。

### Progressive Disclosure [2/2]
- ✅ 正文 31 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补儿童端与家长端不混用主题、reduced-motion 和角色遮挡的视觉评测。


## langfuse-server

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/langfuse-server`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：223 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [2/3]
- ✅ 步骤级指引：L45–54：先容器/Worker/队列，再日志和版本诊断。
- ✅ 具体示例/场景：L35–58：凭据、容器连通、RAGFlow 配置、500 等场景。
- ❌ 输出格式/产物约定：没有统一的定位结论、变更/验证结果回执格式。

### Progressive Disclosure [2/2]
- ✅ 正文 65 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L53 的 docker pull 命令一次给出两个镜像参数；docker pull 只接受一个镜像引用，此示例不能按原样执行。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将示例拆为两次 pull，或在正确 compose 目录使用 docker compose pull 指定服务，再重建。
2. 为 431 行 references/langfuse.md 增加按场景读取的章节路由，替换每次完整读取要求；补回执字段。


## learn-10x

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/learn-10x`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：410 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L20–161：先已有知识扫描，再路径、资源、测验、压缩与解释。
- ✅ 具体示例/场景：L83–88：学习 Session 清单示例。
- ✅ 输出格式/产物约定：L67–89：学习计划路径、YAML 和任务格式。

### Progressive Disclosure [2/2]
- ✅ 正文 194 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L67–70 等保存约定仍指向不存在的 luckey/210 Learning & Reading，需对齐现行 vault 结构。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 更新所有旧目录与元数据约定，按 00_meta/rules 分流，不恢复历史目录。
2. 增加继续学习与实际测验场景；不要仅凭笔记 evergreen 状态断言用户已经掌握。


## lldap

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/lldap`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：65 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L30–44：加载受保护配置、bind、查组、unbind 的完整查询例。
- ✅ 具体示例/场景：L53–55：Jira 不同步某组不等于 LLDAP 无该组的场景。
- ✅ 输出格式/产物约定：查询示例给出返回属性/打印结果；部署与查询分别链接 reference。

### Progressive Disclosure [2/2]
- ✅ 正文 55 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补只读查询、组不存在和凭据缺失场景，保证不回显密码、不自行改组。


## llm-distill

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/llm-distill`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：286 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L36–91：选日期、提取、索引、精读、保存与回报。
- ✅ 具体示例/场景：L38–46、54–59：只读完整率查询及提取命令。
- ✅ 输出格式/产物约定：L21–31：日汇总和逐人详录双产物；L91：覆盖/条数/下一日期。

### Progressive Disclosure [2/2]
- ✅ 正文 94 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补正文过期、低覆盖率和隐私脱敏的合成会话评测；不以真实团队原文作为公开测试 fixture。


## luckey-illustration

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/luckey-illustration`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：205 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L27–95：读正文、shot list、单张生成、校对、保存。
- ✅ 具体示例/场景：L36：断点/分流/前后对比等具体配图场景。
- ✅ 输出格式/产物约定：L84–104：目录、编号 PNG、用途和保存路径。

### Progressive Disclosure [2/2]
- ✅ 正文 101 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L54 强制调用内置 image_gen，但本次 Pi 可用工具中没有该工具，正文未给能力检测或替代生成入口。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 增加能力门禁：可用时接真实图像工具/已配置 provider，不可用时明确阻塞并只交提示词或请求用户选入口；不冒称已出图。
2. 补只要配图策略时不生成、已授权生成时确有图片产物的评测。


## mac-awake

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/mac-awake`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：288 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L12–45：self-test、只读状态、dry-run、获准安装、权限、复验。
- ✅ 具体示例/场景：L27–34：预览/安装示例。
- ✅ 输出格式/产物约定：L22、45：JSON 状态与 keep_awake true/false 验收。

### Progressive Disclosure [2/2]
- ✅ 正文 67 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补仅应用打开不保活、任务结束释放、安装需授权的行为评测；现有 self-test 不等于 skill A/B 基准。


## memory-center

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/memory-center`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：379 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L263–270：重部署与写入/检索端到端核验。
- ✅ 具体示例/场景：L222–236：messages/search/episodes 请求示例。
- ✅ 输出格式/产物约定：L86：LLM JSONL 字段；L223：异步 202 与后续检索结果。

### Progressive Disclosure [1/2]
- ✅ 正文 272 行；要求 <500。
- ❌ 存在可外置的大型内联参考/重复模板。
- 证据：虽低于 500 行，L72–88 的补丁细节、L92–127 的日志配方与运维/API 参考大量直接内联，已有对应 references 可承接。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 把补丁清单和长日志/运维配方移到已存在的 architecture/operations/api references，正文只保留路由和安全边界。
2. 补异步入库未完成不得报成功的评测。


## memory-hub

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/memory-hub`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: tags. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 194 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## memory-review

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/memory-review`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：319 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L27–44：scan、逐条判断、dry-run、apply 和批量驱动。
- ✅ 具体示例/场景：L131–146：决策 JSON 示例。
- ✅ 输出格式/产物约定：L30–32、38–44：packet、诊断包、receipt 与 run 目录。

### Progressive Disclosure [2/2]
- ✅ 正文 191 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L193 建议直连 :9287/v1，L194–195 又明确 review 接口在该端口 404、应走 :9288；新旧入口同时保留。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 删除失效的 :9287 review 操作指引，保留 BFF 权威入口，并区分其他 Hub API；本次未连线上核验端口。
2. 优先补快照失效、部分失败、并发 already_processed、回执未知不重发的评测。


## merge-engine-skills

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/merge-engine-skills`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: tags, title. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 99 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## mermaid-diagrams

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/mermaid-diagrams`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：658 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L12–25：读源、选类型、保存、验证、预览与返回。
- ✅ 具体示例/场景：L15–19：流程/消息/生命周期/排期场景；L27：只要内联块时的分支。
- ✅ 输出格式/产物约定：L20、25、27：独立 .mmd 与可点击路径，内联请求用代码围栏。

### Progressive Disclosure [2/2]
- ✅ 正文 24 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 增加读图不得改源、创建后解析校验、只要内联不落文件的评测；明确无 PowerShell 时的校验入口。


## mihomo-proxy-setup

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/mihomo-proxy-setup`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：231 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L21–119：架构、安装、数据、配置、服务、验证的顺序。
- ✅ 具体示例/场景：L72–80：订阅被阻断时 file provider 示例。
- ✅ 输出格式/产物约定：L228–237：二进制/配置/缓存/systemd 产物路径。

### Progressive Disclosure [2/2]
- ✅ 正文 232 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补已有代理不得无授权卸载、订阅失败与端口冲突的隔离评测。


## nginx-local-server

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/nginx-local-server`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：237 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L135–149：查路径、nginx -t、reload、验证 gzip。
- ✅ 具体示例/场景：L40–86：完整站点配置示例。
- ✅ 输出格式/产物约定：L112–118、147–149：.gz 成对产物和 Content-Encoding 验收。

### Progressive Disclosure [2/2]
- ✅ 正文 152 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 把站点完整配置作为按需参考，并补实际主机确认、配置验证失败不 reload 的评测。


## office-js

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/office-js`
**Score:** 6/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：364 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L21–35：load → sync → read，以及优先专用 Office 工具的路由。
- ✅ 具体示例/场景：L94 起：Excel/Word/PowerPoint 的完整代码示例。
- ✅ 输出格式/产物约定：L25：返回 string/JSON.stringify；各示例有明确返回值。

### Progressive Disclosure [0/2]
- ❌ 正文 619 行；要求 <500。
- ❌ 存在可外置的大型内联参考/重复模板。
- 证据：正文 619 行且无 references/；Excel、Word、PowerPoint 对象模型和大量代码全量内联。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将三个 Office 应用各拆一个 reference，正文保留工具选择、上下文规则与最小共同示例。
2. 补 load/sync 顺序、返回类型和批量调用的 mock 工具评测。


## orchestration-ops

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/orchestration-ops`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Description cannot contain angle brackets (< or >)

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 41 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. description 的命令占位符去掉尖括号，例如 orca COMMAND --help；正文命令说明可保持，随后重跑校验。


## oss-upload

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/oss-upload`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：247 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L81 起：扫描、下载、上传、替换的 Markdown 迁移流程。
- ✅ 具体示例/场景：L12–31：单文件和跨平台提取 URL 示例。
- ✅ 输出格式/产物约定：L16–21：OSS_URL 行协议及公网地址形态。

### Progressive Disclosure [2/2]
- ✅ 正文 167 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补已是 OSS 链接跳过、下载/上传失败不替换和重复图片去重的 fixture 评测。


## pi-agent

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/pi-agent`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：222 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L117–125：先无扩展启动区分故障，再日志和对应参考。
- ✅ 具体示例/场景：L45–50：a2a 401 探活与 index_missing 场景。
- ✅ 输出格式/产物约定：L80–87：事务外发状态与持久化责任明确，给出可核验日志/状态证据。

### Progressive Disclosure [2/2]
- ✅ 正文 120 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 把会话/版本快照移到个人记忆或专题参考；核对 L122 的必须特定 cwd 约定与 git-tool 当前自动定位说明。
2. 补成功外发后不得再发失败消息的场景评测。


## post-to-wechat

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/post-to-wechat`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: version. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 285 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## print

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/print`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Compatibility must be a string, got list

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 60 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 把 compatibility 的 YAML 列表改为字符串/折叠文本，保留平台依赖信息，然后重跑 quick_validate。


## pyauto-aireview

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/pyauto-aireview`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：416 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L52–58：按具体故障、慢问题、warning、提交未知分诊并及时停止。
- ✅ 具体示例/场景：L54–57：明确的 Review/Flow/Task 故障场景。
- ✅ 输出格式/产物约定：L123–127：对象映射、根因证据、修改/测试/CL、部署与验证状态。

### Progressive Disclosure [2/2]
- ✅ 正文 120 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 7 test cases；其中 7 例含结构化 expectations，共 27 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 现有 7 例已有 expectations；后续挑一个高频场景做隔离 A/B，区分脚本/模型/编译/提交的独立成功证据。


## pyauto-shared

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/pyauto-shared`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：296 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L35–39：选领域、稳定 ID、路由、最小证据、分层回报。
- ✅ 具体示例/场景：L15–20：AI Review、TC、部署等具体入口场景。
- ✅ 输出格式/产物约定：L39、58–61：分别回报源码、部署与本轮业务事实，不冒称成功。

### Progressive Disclosure [2/2]
- ✅ 正文 55 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 2 test cases；其中 2 例含结构化 expectations，共 8 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 现有 2 例已有 expectations；扩展未知系统归属和未授权重跑/部署的负例即可，不扩大共性正文。


## qnap-git-setup

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/qnap-git-setup`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：307 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L56–79：安装、PATH、key、host、remote、agent、验证。
- ✅ 具体示例/场景：L33–37：正确/错误型号固件 URL 对照。
- ✅ 输出格式/产物约定：L31、63：固件命名模式及 key 文件路径；测试拉取作为验收。

### Progressive Disclosure [2/2]
- ✅ 正文 83 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补相近型号误选固件、已有 key 不覆盖和 SSH agent 缺失的评测。


## qnap-nas

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/qnap-nas`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：260 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L314–340：dry-run、同步、完整性报告、修复与查询顺序。
- ✅ 具体示例/场景：L102–145、279–282：CacheMount 与 HBS 修复示例。
- ✅ 输出格式/产物约定：L206、247、279–281：远程 JSON 列表、检查与修复 CSV 路径。

### Progressive Disclosure [1/2]
- ✅ 正文 432 行；要求 <500。
- ❌ 存在可外置的大型内联参考/重复模板。
- 证据：正文 432 行；L39–85 与 L191–342 等完整命令/参数参考大段内联。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 按 HybridMount、HBS3、189 三域拆 reference，正文保留选择入口、dry-run 和破坏性操作授权边界。
2. 补源目标反转、防误删与报告归属的 fixture 评测。


## qnap-perforce

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/qnap-perforce`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：222 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [2/3]
- ✅ 步骤级指引：L81–114：watchdog、自启与手动启停步骤；L125–133：备份恢复。
- ✅ 具体示例/场景：L83–91：幂等启动脚本示例。
- ❌ 输出格式/产物约定：有运维命令和路径，但缺少启动/恢复后的状态证据及回报结构。

### Progressive Disclosure [2/2]
- ✅ 正文 135 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补服务身份、p4 info、checkpoint/journal 路径、恢复验证和未验证项的短回执。
2. 为误连旧 Docker 实例、恢复前未停库设计禁止执行的评测。


## ragflow

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/ragflow`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：497 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L16–26 分流；L78–83：提炼、写前基线、写入、等待、召回验证。
- ✅ 具体示例/场景：L49–60：同义词淹没、结果抖动、重解析降排名等具体症状。
- ✅ 输出格式/产物约定：L85–90：参数组合、原因、写入前后差异与是否通过。

### Progressive Disclosure [2/2]
- ✅ 正文 88 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 4 test cases；其中 0 例含结构化 expectations，共 0 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 现有 4 个 prompt 补 expectations，优先覆盖先保存检索基线、异步等待和没有召回不得报成功。


## ragflow-deploy

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/ragflow-deploy`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：365 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L28–74：分诊、读对应参考、部署、启动验证与告知。
- ✅ 具体示例/场景：L19–22：端口冲突、限流、复用存储场景。
- ✅ 输出格式/产物约定：L63–77：ready/HTTP 验收与面向用户的部署信息。

### Progressive Disclosure [2/2]
- ✅ 正文 125 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 在报告中区分服务启动成功与真实解析/检索通过；补端口冲突、保留已有数据和禁止无授权重建的评测。


## skill-creator

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/skill-creator`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：319 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：已加载正文：访谈、写技能、构造场景、运行/分级/汇总、人工反馈迭代。
- ✅ 具体示例/场景：已加载正文：evals.json、eval_metadata.json、timing.json 示例。
- ✅ 输出格式/产物约定：已加载正文：grading.json 字段、benchmark 与 viewer 交付约定。

### Progressive Disclosure [1/2]
- ❌ 正文 503 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。
- 证据：正文 503 行，略超 500；grader/analyzer/schemas 等大型支持文档已经外置。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将 Claude.ai/Cowork 等环境适配段按需外置即可压回 500 行，不必重构主流程。
2. 统一正文的 assertions 用词与 schemas.md 中 evals[].expectations 的字段约定，避免作者误写字段。


## skill-harvest

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/skill-harvest`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: disable-model-invocation, tags, title. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 148 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. title/tags 等展示信息可归 metadata；disable-model-invocation 先按实际宿主的行为语义确认兼容策略，不为了过校验直接删掉或移到 metadata。
2. 统一后重新校验，再评正文和评测覆盖。


## skill-index-patrol

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/skill-index-patrol`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: tags, title. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 147 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## sub2api-server

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/sub2api-server`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：199 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L82–104：保留本地定制、拉取、构建/镜像与 compose 更新说明。
- ✅ 具体示例/场景：L43–56：compose 与 nginx 管理示例。
- ✅ 输出格式/产物约定：L108–113：内外层 health 的 HTTP 200/healthy 验收形态。

### Progressive Disclosure [2/2]
- ✅ 正文 108 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补当前执行主机确认、保留本地定制和升级失败回滚的隔离评测；不要把 healthy 当 API 业务验收。


## teamcity-extract-commandlet

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/teamcity-extract-commandlet`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：358 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L21–34：URL/BuildId → 原始命令 → 本地化参数。
- ✅ 具体示例/场景：L25–29：LocalRoot 为构建机 sandbox 的示例。
- ✅ 输出格式/产物约定：L45–49：构建上下文、分支告警、RawCommand、VsArgs。

### Progressive Disclosure [2/2]
- ✅ 正文 62 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补不同 commandlet、分支不一致和日志无命令的 fixture 评测；脚本路径改为 skill-dir 定位。


## teamcity-tool

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/teamcity-tool`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：819 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L24–40：先主机指纹；L132–135：链展开、参数归属、echo-only、真实验证。
- ✅ 具体示例/场景：L73–81、98–101：服务与 LDAP 配置示例。
- ✅ 输出格式/产物约定：L135：Agent、stream/CL/Root、revision 和分阶段状态回执。

### Progressive Disclosure [2/2]
- ✅ 正文 183 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 优先补多层参数传递、No agent、绿色但无真实评审证据的评测；将历史 build 事故叙述移到 reference。


## temporal-server

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/temporal-server`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：221 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L106–139：绑定、主机防火墙、云安全组、代理与安全。
- ✅ 具体示例/场景：L32–60：本地、远端、后台及持久化启动例。
- ✅ 输出格式/产物约定：L36、88–99：监听地址/端口、进程与 HTTP 状态验收。

### Progressive Disclosure [2/2]
- ✅ 正文 152 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补无认证 dev server 不得无约束暴露、持久化文件保留与端口占用的安全评测。


## text-to-image-prompt

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/text-to-image-prompt`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：199 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L8–29：收集用途/比例/风格，再生成差异化三套。
- ✅ 具体示例/场景：L100–109：封面、方图、壁纸的具体比例场景。
- ✅ 输出格式/产物约定：L48–96：三套中英 prompt、感觉说明与平台参数模板。

### Progressive Disclosure [2/2]
- ✅ 正文 112 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L111 要求 Flux 宽高均为 32 的倍数，却给出 1920×1080；1080 不能被 32 整除，内部规则和示例冲突。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 先核对目标模型真实尺寸约束，再统一规则与样例；若坚持 32 倍数，1080 必须改为合法高度并说明比例近似。
2. 补三套确有差异、参数匹配平台、尺寸满足约束的评测。


## ue-blueprint-reflection

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/ue-blueprint-reflection`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: tags, title. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 97 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## ue-launcher-toolbox

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/ue-launcher-toolbox`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：359 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L23–31 按任务路由；所指 references/client-build.md L5–19、31–45 给出构建、验证、分发、CL 收尾。
- ✅ 具体示例/场景：L37–41：exe 占用、新包型旧客户端不兼容及 740 等具体场景。
- ✅ 输出格式/产物约定：L19、36 与 client-build.md L21–29、43–45：exe 位置、源码/二进制同 CL 的明确交付。

### Progressive Disclosure [2/2]
- ✅ 正文 35 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 维持薄入口与按模块引用；补 portable/zip 消费者兼容性、占用不杀进程和 no-UAC 测试边界的评测。


## video-downloader

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/video-downloader`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：181 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L17–21：平台、reference、cookie、下载与已存在处理。
- ✅ 具体示例/场景：L49、87–89：分离视频/音频的具体合并例。
- ✅ 输出格式/产物约定：L49、88、96：完整 mp4、output.mp4 和下载目录约定。

### Progressive Disclosure [2/2]
- ✅ 正文 92 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 澄清“已存在自动跳过”与 you-get 会覆盖的差异，给出可复用存在性检查；补无 cookie、无 ffmpeg、重复下载评测。


## violoop-report

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/violoop-report`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：217 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L23–94：识图、上传、空 URL 停止、头部插入记录、回报。
- ✅ 具体示例/场景：L30–36：缓存找图；L96 起：带图/纯文字回执例。
- ✅ 输出格式/产物约定：L10–13、64–66、115–120：固定记录文件与分隔线、时间戳、图片格式。

### Progressive Disclosure [2/2]
- ✅ 正文 115 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

**Notable issue / 降级依据：** L12、66 强制写入已不存在的 luckey/110 Utilities/violoop/user-feedback.md，可能重建废弃目录并分叉原有记录。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 按现行规则定位唯一记录文件并更新两个重复路径，不直接新建旧目录。
2. 补纯文字、上传失败不写入、顶部追加且不覆盖旧记录的 fixture 评测。


## vscode-as

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/vscode-as`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：381 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L29–61：确认边界、真实样例定位、最窄实现、分层验证。
- ✅ 具体示例/场景：L72–74：async FTask 正常运行但无大纲/补全的具体样例。
- ✅ 输出格式/产物约定：L76–81：根因、验证、使用/VSIX 元数据、安装/发布状态。

### Progressive Disclosure [2/2]
- ✅ 正文 71 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
✅ Has evals/evals.json with 3 test cases；其中 3 例含结构化 expectations，共 15 条。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 现有 3 例已有 expectations；后续验证真实模块回归与 TextMate 证据，不把构建成功当安装版已生效。


## wireguard-setup

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/wireguard-setup`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：239 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L18–186：环境、参数、安装、key、配置、网络、服务、客户端、二维码。
- ✅ 具体示例/场景：L56–57：私网分流与全隧道对照；L207 起：增客户端分支。
- ✅ 输出格式/产物约定：L131、153、155–197：转发、监听、配置/二维码、handshake 验收。

### Progressive Disclosure [2/2]
- ✅ 正文 290 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补不中断已有 peer、AllowedIPs 冲突和密钥不回显的评测；二维码同样包含私钥，不应视为天然更安全。


## write-article

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/write-article`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：171 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L26–94：文章、封面、公众号草稿箱。
- ✅ 具体示例/场景：L34–55：文章 Markdown 模板；L69–72：封面生成例。
- ✅ 输出格式/产物约定：L12–18：writing 日期目录、文章名和 cover.png/尺寸。

### Progressive Disclosure [2/2]
- ✅ 正文 100 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补仅写草稿、要求先审阅即暂停、封面缺失不发布的 mock 评测，禁止 benchmark 触发真实外发。


## zen-server

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/zen-server`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：99 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：L57–69：stop、复制、chmod、启动、验证的更新序列。
- ✅ 具体示例/场景：L106–138：缓存/GC 查询、dry-run 与清理例。
- ✅ 输出格式/产物约定：L106–110、168–180：命名空间/大小/条目数、健康和磁盘输出。

### Progressive Disclosure [2/2]
- ✅ 正文 176 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补明确授权后才 drop namespace、先 dry-run、确认端口与服务器身份的评测。


## .claude/skills/add-github-submodule

**Rating:** Incomplete
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/.claude/skills/add-github-submodule`
**Score:** N/A（结构门禁未过）

### Structural Validity
❌ FAIL: Unexpected key(s) in SKILL.md frontmatter: tags, title. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name

### Description Quality [N/A]
- 结构校验失败，暂不评分。

### Body Completeness [N/A]
- 结构校验失败，暂不评分。

### Progressive Disclosure [N/A]
- 仅记录正文 126 行，不作内容判分。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将校验器拒绝的展示字段归入 metadata，或先明确目标宿主允许字段与校验器的兼容策略；不要把严格校验失败直接当运行时无法加载。
2. 元数据通过后，再继续正文质量与行为评测。


## axton-obsidian-visual-skills/excalidraw-diagram

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/axton-obsidian-visual-skills/excalidraw-diagram`
**Score:** 7/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：304 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：Workflow 与 Implementation Notes：模式、布局、JSON、写文件、回报。
- ✅ 具体示例/场景：Example Output Messages：Obsidian/Standard/Animated 三类交付例。
- ✅ 输出格式/产物约定：Output Formats 与文件名表：.md/.excalidraw/.animate.excalidraw 和必要字段。

### Progressive Disclosure [1/2]
- ✅ 正文 469 行；要求 <500。
- ❌ 存在可外置的大型内联参考/重复模板。
- 证据：正文 469 行；Element Template、Required Fields 与文本属性重复，完整字段规范可转交现有 references/excalidraw-schema.md。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 将重复 JSON 字段/模板移到 schema reference；补三种模式可打开、唯一 ID 和动画顺序的评测。


## axton-obsidian-visual-skills/mermaid-visualizer

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/axton-obsidian-visual-skills/mermaid-visualizer`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：300 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：Quick Start 与 Workflow：分析、选型、配置、生成、交付五步。
- ✅ 具体示例/场景：Example Usage Patterns 与 Common Patterns：流程、对比、循环、hub-and-spoke。
- ✅ 输出格式/产物约定：输出 Mermaid 代码围栏、结构解释与渲染兼容性。

### Progressive Disclosure [2/2]
- ✅ 正文 271 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补解析器评测和特殊字符用例；与 mermaid-diagrams 明确独立源文件/内联展示的路由边界。


## axton-obsidian-visual-skills/obsidian-canvas-creator

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/axton-obsidian-visual-skills/obsidian-canvas-creator`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：243 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：Core Workflow 六步：分析、布局、结构、生成、定位、验证。
- ✅ 具体示例/场景：Examples：太阳系 MindMap 与文章转 freeform canvas。
- ✅ 输出格式/产物约定：Output Format/JSON Structure：有效 nodes/edges JSON、无额外包裹。

### Progressive Disclosure [2/2]
- ✅ 正文 206 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 补重叠、悬空 edge、中文转义与可导入 .canvas 的 fixture 评测。


## diagram-design/skills/diagram-design

**Rating:** Needs work
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/diagram-design/skills/diagram-design`
**Score:** 6/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：747 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：§0、§3、§10–11：品牌门禁、选型、模板、检查与导入。
- ✅ 具体示例/场景：§6：SVG 节点/箭头/标签的完整示例。
- ✅ 输出格式/产物约定：§11–12：HTML/SVG/PNG 输出、尺寸、fidelity ledger 和可访问性契约。

### Progressive Disclosure [0/2]
- ❌ 正文 574 行；要求 <500。
- ❌ 存在可外置的大型内联参考/重复模板。
- 证据：正文 574 行；39 类型表、完整 SVG primitives、详细布局/检查清单仍同时内联。

**Notable issue / 降级依据：** §7 要求所有字体尺寸/坐标为 4 的倍数，但 §5/§6 自带 7px、9px 等字体示例；严格约束与示例需统一。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 保留选型路由与交付门，把 SVG primitives、布局和详细 checklist 外置，缩短入口。
2. 统一 4px 网格规则与文字/坐标例外；补几何检查、导入不丢语义和指定导出格式的评测。


## frontend-slides/plugins/frontend-slides/skills/frontend-slides

**Rating:** Healthy
**Path:** `/Users/sun/Documents/ObsidianVault/.claude/skills/frontend-slides/plugins/frontend-slides/skills/frontend-slides`
**Score:** 8/8

### Structural Validity
✅ PASS — quick_validate.py

### Description Quality [3/3]
- ✅ 非空且 >50 字符：311 字符。
- ✅ 描述功能/目标产物。
- ✅ 包含具体触发词、用户意图或适用上下文。

### Body Completeness [3/3]
- ✅ 步骤级指引：与根 frontend-slides/SKILL.md 的 SHA-256 完全相同，阶段流程相同。
- ✅ 具体示例/场景：相同的密度选择、修改约束、部署/PDF 命令示例。
- ✅ 输出格式/产物约定：相同的单文件 HTML、视觉校验与可选 PDF 交付。

### Progressive Disclosure [2/2]
- ✅ 正文 375 行；要求 <500。
- ✅ 大型资料已按需外置，或本身短小自包含。

### Eval Coverage
⚠️ No evals/evals.json — 可通过 /skill-creator 添加；不等于没有其他测试。

### Benchmark Results
未运行（项目级 Tier 1）。

### Recommendations
1. 这是插件打包镜像，不据此断言运行时重复加载；建立生成/同步检查，避免两个相同入口日后漂移。
