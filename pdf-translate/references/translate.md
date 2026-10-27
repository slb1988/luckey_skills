# 翻译使用与排障

## 凭据与配置

凭据统一放**仓库根目录 `.env`**（`/Users/sun/Documents/ObsidianVault/.env`，已被 .gitignore 忽略）：

```bash
OPENAILIKED_BASE_URL=http://10.77.77.4:8600/v1   # build-api-proxy 网关，OpenAI 兼容端点
OPENAILIKED_API_KEY=ik_...                        # 网关虚拟 key（与 pi 同一把）
OPENAILIKED_MODEL=kimi-k3                         # 或 deepseek-v4-flash
PDF2ZH_OPENAI_TEMPERATURE=1                       # kimi-k3 必需；deepseek-v4-flash 可删
```

- 网关可用模型列表：`curl --noproxy '*' http://10.77.77.4:8600/v1/models -H "Authorization: Bearer $OPENAILIKED_API_KEY"`
- `openailiked` 是 pdf2zh 内置服务名，专接任意 OpenAI 兼容端点
- 网关在内网（10.77.77.0/24），本机 shell 的 `no_proxy` 已含 10.77.77.4；wrapper 脚本里也有兜底

## 日常使用

统一走封装脚本 `pdf2zh-kimi`（本体在本 skill `scripts/pdf2zh-kimi`，`~/.local/bin/pdf2zh-kimi` 是指向它的符号链接；自动 source 根 .env）：

```bash
cd <想要的输出目录>          # 输出生成在当前目录，不是输入 PDF 所在目录
pdf2zh-kimi paper.pdf        # 全本翻译
pdf2zh-kimi paper.pdf -p 1-5 # 指定页
pdf2zh-kimi -i               # Web GUI
```

输出两个文件：`<名>-mono.pdf`（纯译文）和 `<名>-dual.pdf`（中英对照，页数翻倍）。

## 性能基线

- 首次运行下载 ONNX 版面分析模型（走系统代理），之后有缓存
- kimi-k3 是推理模型：约 15–20 秒/页，15 页 ≈ 4.5 分钟；长文档 `nohup ... &` 放后台
- deepseek-v4-flash 非推理模型，更快更便宜，翻译质量对一般文档够用

## 常见问题

| 症状 | 原因与处理 |
|---|---|
| `400 invalid temperature: only 1 is allowed` | kimi-k3 + 未打 temperature 补丁或缺 `PDF2ZH_OPENAI_TEMPERATURE=1`，见 install.md 第 3 步 |
| `ImportError: TextTranslateRequest / BitStream` | 升级 pdf2zh 后钉版被重置，重跑 install.md 第 2 步 |
| 翻译结果空白/报错连接超时 | 默认服务是 Google（国内不通）；确认用了 `-s openailiked`（wrapper 已带） |
| GUI 里 openailiked 不生效 | GUI 从启动它的 shell 继承环境变量；用 `pdf2zh-kimi -i` 启动而不是裸 `pdf2zh -i` |
| 公式被翻译成中文 | 换 deepseek-v4-flash 时把 `PDF2ZH_OPENAI_TEMPERATURE` 删掉（恢复 0），低温度更守公式占位符 |

## 快速端到端验证（不消耗整本 PDF）

```bash
set -a; source /Users/sun/Documents/ObsidianVault/.env; set +a
~/.local/share/uv/tools/pdf2zh/bin/python -c "
from pdf2zh.translator import OpenAIlikedTranslator
t = OpenAIlikedTranslator('en','zh',model=None)
print(t.translate('We propose a novel layout-preserving translation method.'))"
```
