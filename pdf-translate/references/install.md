# 安装 PDFMathTranslate (pdf2zh)

本机 macOS arm64 实测流程（2026-10，pdf2zh v1.9.11）。官方要求 Python 3.11–3.12。

## 1. 安装（uv tool 隔离环境，不污染 conda）

```bash
uv tool install --python 3.12 pdf2zh
```

- 依赖多且大（onnxruntime、opencv 等），PyPI 直连可能超过 10 分钟；建议放后台跑并轮询日志
- 装完命令在 `~/.local/bin/pdf2zh`，环境在 `~/.local/share/uv/tools/pdf2zh/`

## 2. 两个必须钉版的依赖

上游元数据未锁版本，直接装到新版会启动即挂。装完立刻钉版：

```bash
uv pip install --python ~/.local/share/uv/tools/pdf2zh/bin/python \
  "tencentcloud-sdk-python-tmt==3.0.1478" "bitstring==4.3.1"
```

| 包 | 症状 | 根因 |
|---|---|---|
| tencentcloud-sdk-python-tmt | `ImportError: cannot import name 'TextTranslateRequest'` | 3.1.x 移除了该类，最后可用 3.0.x = 3.0.1478 |
| bitstring | `ImportError: cannot import name 'BitStream'`（来自 babeldoc） | 5.0.0 移除 `BitStream`，babeldoc 只要求 `>=4.3.0` 无上限 |

## 3. temperature 补丁（kimi-k3 必需）

kimi-k3 上游强制 `temperature=1`，而 pdf2zh 源码硬编码 0 → 400 `invalid temperature`。
给已安装的 `translator.py` 打补丁，改为从环境变量读取：

文件：`~/.local/share/uv/tools/pdf2zh/lib/python3.12/site-packages/pdf2zh/translator.py`，
`OpenAITranslator.__init__` 中（在 `model = self.envs["OPENAI_MODEL"]` 之后）：

```python
# 改前
self.options = {"temperature": 0}  # 随机采样可能会打断公式标记
# 改后
self.options = {"temperature": float(os.environ.get("PDF2ZH_OPENAI_TEMPERATURE", "0"))}
```

注意文件里有**两处**相同的 `self.options = {"temperature": 0}`（另一处在 XinferenceTranslator），
靠上文 `self.envs["OPENAI_MODEL"]` 区分，只改 OpenAI 这处。`os` 模块 translator.py 已导入。

用 deepseek-v4-flash 等接受 temperature=0 的模型则可不打补丁（根 .env 里删掉 `PDF2ZH_OPENAI_TEMPERATURE` 即可）。

**`uv tool upgrade pdf2zh` 会重置 site-packages，钉版和补丁全部丢失，升级后重跑本节第 2、3 步。**

## 4. 验证

```bash
pdf2zh --version   # 应输出版本号，无 ImportError
```

端到端翻译验证见 [translate.md](translate.md)。
