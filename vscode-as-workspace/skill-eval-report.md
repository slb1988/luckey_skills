## vscode-as

**Rating:** Healthy（8/8，结构检查通过）
**Path:** `.claude/skills/vscode-as/`

### Structural Validity

PASS：`quick_validate.py`；YAML 合法，description 381 字符，入口 81 行。20 个原始本地文档链接和 3 个 eval 定义检查通过。

### Description Quality [3/3]

非空且超过 50 字符；覆盖 .as/async-await、补全/符号/高亮、Launch Client/开发宿主、LSP/DAP 与 VSIX 触发；明确不取代引擎编译器或通用 VSCode 运维。

### Body Completeness [3/3]

按目标/真实样例/最小修改/分层验收的步骤执行；含 async FTask 与 await UISteps 示例；结果输出契约明确。

### Progressive Disclosure [2/2]

SKILL.md 81 行；架构、开发、分发分入 docs，历史 async 修复和 VSIX 包基线分入 references。

### Eval Coverage

3 个只读演练题，各 5 项要求。六个新上下文均用 Astra，禁用 skill/项目上下文/扩展自动加载；有技能组显式读本技能，无技能组不读项目资料。动作复核仅涉及许可资料、答案文件和 Orca 生命周期。

### Benchmark Results

| Config | 要求满足率 | 墙钟时间 | token（含 cacheRead） |
| --- | --- | --- | --- |
| with_skill | 100%（15/15） | 132.0s ± 17.1s | 61817 ± 6855 |
| without_skill | 40%（6/15） | 141.8s ± 38.8s | 35098 ± 12945 |

差异主要来自项目固定入口与流程细节。每场景/配置仅一次；标准差来自不同题目，不能理解为重复实验稳定性。基线无文档访问权，不能据此宣称通用能力提升 60%。不覆盖实际工程执行或触发准确率。

结果页：`iteration-1/review.html`，包含 Outputs 和 Benchmark；尚无用户人工反馈。

### Security

全 `.claude/` 范围扫描 4684 个文本文件（排除依赖/缓存和受保护环境文件，后者另用 Git 元数据 guard 检查）。3 个凭据形状候选人工复核为测试或反例；新增技能无密钥形状匹配或内网地址。模式扫描不是绝对无秘密的证明；其他既有基础设施文档不在本次提交范围。

### Recommendations

1. 按项目后续改动更新最窄 docs，不把历史 1.9.5 通过状态当作当前验收。
2. Windows 包的 Unix helper 执行位问题保留为分发门槛，目标平台验证前不承诺支持。
3. 用户有真实反馈后追加案例；真实修改/安装类评估必须使用授权隔离环境。
