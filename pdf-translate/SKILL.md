---
name: pdf-translate
description: 本机 PDFMathTranslate (pdf2zh) 论文 PDF 翻译工具的安装与使用。保留公式/图表/目录排版，走 build-api-proxy 网关的 kimi-k3 等自定义 LLM 翻译，输出 mono（纯译文）+ dual（中英对照）两个 PDF。当用户提到翻译PDF、论文翻译、pdf2zh、PDFMathTranslate、双语PDF、PDF翻译、把这篇论文翻成中文、装 pdf2zh、pdf2zh 报错时触发。即使用户只说「帮我翻译这个 PDF」「这篇论文翻一下」「pdf2zh 又挂了」也应触发。
---

# pdf-translate — PDFMathTranslate 本机翻译

本机已安装 pdf2zh（uv tool 隔离环境），命令 `pdf2zh`；封装脚本 `pdf2zh-kimi` 默认走 build-api-proxy 网关的 kimi-k3。

## 快速使用

```bash
pdf2zh-kimi paper.pdf          # 翻译，输出 paper-mono.pdf（纯中文）+ paper-dual.pdf（中英对照）
pdf2zh-kimi paper.pdf -p 1-5   # 只翻指定页
pdf2zh-kimi -i                 # Web GUI（http://localhost:7860）
```

输出文件生成在**当前工作目录**（不是输入 PDF 所在目录），运行前先 `cd` 到想要的输出目录。速度约 15–20 秒/页（kimi-k3 推理模型），长文档放后台跑。

## 详细参考（按需读取）

- **安装/重装/升级后修复**：[references/install.md](references/install.md)——uv tool 安装、两个必须钉版的依赖、temperature 补丁（升级后丢失须重打）、验证步骤
- **翻译配置与排障**：[references/translate.md](references/translate.md)——openailiked 服务环境变量、模型选择（kimi-k3 vs deepseek-v4-flash）、凭据来源、常见问题

## 关键事实（避免重复踩坑）

- 凭据从**仓库根目录 `.env`** 读取（`OPENAILIKED_*` / `PDF2ZH_OPENAI_TEMPERATURE`），不要硬编码进任何脚本；`.env` 已被仓库 .gitignore 忽略
- **kimi-k3 上游强制 temperature=1**，pdf2zh 源码硬编码 0 → 必须打补丁（见 install.md），否则 400 报错
- 默认 Google 翻译服务在国内不通，必须用 `-s openailiked`（或 bing）
- `uv tool upgrade pdf2zh` 会重置 site-packages，钉版和补丁都要重做——升级后先读 install.md
