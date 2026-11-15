# Claude Code Bundle 提取原理

本文解释 `scripts/extract_bundle.py` 的工作原理、为什么简单方案会失败、以及新版本失效时怎么修。
方法论源自社区（mandersogit/agent-tools-and-skills，v2.1.63 验证），本仓库在 v2.1.321（Windows x64）上重新验证。

## 二进制结构

Claude Code 是 Bun standalone executable（Windows 上 ~350MB PE）。JS 应用以明文嵌入，但**与二进制 blob 交错**：
原生 `.node` 模块、WASM、ICU 数据表、以及 `bun build --compile --bytecode` 产生的 JSC 字节码块
（每个模块以 `// @bun @bytecode` 头开始）。JS 区域约 100MB，其中约半数字节是不可打印的交错 blob。

二进制带有 `\n---- Bun! ----\n` trailer。**注意 trailer 不一定在文件末尾**：
Windows 版 trailer 后还有 ~10KB 全零 padding（疑似 Authenticode 签名填充），aarch64 ELF 版 trailer 后有 ~106KB section headers。
定位必须 `rfind` 而不能读文件尾固定偏移——这也是 lafkpages/bun-decompile（严格按 trailer-at-EOF 解析 module graph）
直接跑会失败的原因。

## 被否决的方案

### `strings` 提取

`strings -n 500` 产出看似 JS 的 ~23MB 文本，但 strings 在不可打印字节处切断，交错 blob 会把 JS 在语句中间撕碎。
tree-sitter 解析结果出现 **46,378 个 ERROR 节点**，identifier/表达式在碎片边缘被拦腰截断。

### 花括号配对找模块边界

字符串字面量和模板字符串里的 `{`/`}` 会污染计数（如模块内含 `"{"`），导致配对器吞掉后续几十个模块，
产出明显错误的「巨型模块」。区分结构性括号与字符串内括号必须靠真正的 parser。

## 采用的方案：直接文本 run 提取

1. **定位 JS 区域**：起点 = 众数 wrapper 的**第一个** `var X=<wrapper>(()=>` 模块声明出现处。
   **不要**向前回溯到可打印 run 的起点——那会落进前一个模板字符串里，未闭合的反引号会让 tree-sitter
   静默吞掉整个文件返回 0 模块。终点 = `rfind("\n---- Bun! ----\n")`。
2. **提取可打印文本 run**：逐字节走，可打印 ASCII（32-126）加 tab/LF/CR 累积成 run；
   遇到不可打印字节，若当前 run >20 字节则保存。20 字节阈值滤掉 blob 边缘的小碎片。
3. **`;\n` 缝合**：run 之间用 `;\n` 连接。分号在 blob 打断处制造合法的 JS 语句边界——
   不需要知道 blob 是什么，只要保证两侧 JS 不粘连。

效果（v2.1.321）：54MB 干净 JS，tree-sitter 解析出 2207 个模块，ERROR 节点只剩 blob 边界的少量碎片（v2.1.63 时 558 个）。

## 模块解析

tree-sitter + tree-sitter-javascript 解析后，顶层模块是两种形态：

- `var X = p((exports, module) => { ... })` — CommonJS 风格
- `var X = p(() => { ... })` — init/副作用模块

wrapper 名（`p`、`El` 等）是 minified 标识符，**几乎每个版本都重排**
（观测：2.1.91=`A`，2.1.170=`V`，2.1.217=`b`，2.1.220=`S`，2.1.321=`p`/`El`）。
探测方法：正则 `var [A-Za-z0-9_$]{1,8}=([A-Za-z0-9_$]{1,3})\(\(\)=>` 取众数（真 wrapper 出现数千次，偶然匹配只有个位数）。
众数出现 <500 次时判定探测不可靠，报错而不是产出不可信结果。

## 分类

正则信号把模块分为 vendored（highlight.js、AWS SDK、zod、lodash 等，默认不进美化产物）/
app（含 `CLAUDE.md`、`systemPrompt`、`tengu_` 等信号）/ infra（<200B 的胶水）/ unknown（大多数 app 代码在这里）。
分类只影响清单标注和 vendored 过滤，**所有非 vendored 模块都会进 `claude-app.js`**。

## 已知盲区：ESM chunk 模块不进 claude-app.js

v2.1.321 实测发现：`claude-app.js` 只覆盖 tree-sitter 能捕获的 `var X=<wrapper>(()=>{...})` 顶层声明模块。
Bun 的 ES 模块 chunk（源码路径形如 `B:/~BUN/root/chunk-*.js`）不以这种形态出现，**只存在于原始 `bundle.js`**。
多个新 feature 的实现主体恰恰都在 chunk 区（Code Mode 引擎、MCP tasks、子代理进度摘要、权限判定、Remote Control 全部命中此盲区）。

实务做法：分析时先 grep `claude-app.js`；零命中或只有 schema/描述性命中时，直接 grep `bundle.js`（行号是缝合后偏移），
命中段用 jsbeautifier 现场美化后通读。后续可增强 `extract_bundle.py`：识别 chunk 形态并纳入模块化输出。

## 性能

346MB 二进制（v2.1.321，Windows）：提取 ~10s，tree-sitter 解析 ~10s，美化 ~2min。

## 新版本失效排查

1. **wrapper 名变了**：自动探测覆盖此情况；若报错「No module declarations found」，手工
   `strings -n 1000 <binary> | head` 找新的模块声明形态，更新 `MODULE_DECL_RE`。
2. **trailer 没了**：`rfind("---- Bun! ----")` 为空 = Bun 改了嵌入格式（如压缩），文本 run 方案整体需要重评。
3. **分类漂移**：信号串被改名/移除时模块退化为 unknown，不影响产出完整性，只影响清单可读性。
