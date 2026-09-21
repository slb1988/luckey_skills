# vscode-as 评估说明

`evals.json` 包含三个只读接手题：contextual async 编辑器支持、附加现有开发宿主、VSIX 跨平台分发。每题 5 条要求；答案应该给出路线和证据标准，不实际修改、构建、安装、启动或发布工程。

## 执行约定

- 有 skill：仅读本 skill 入口及按需 docs/references，不读评分要求或目标工程。
- 无 skill：仅依题干和通用知识，不读本 skill、工程文档/源码或历史记忆；不知道的专用路径/配置名应说明未知，不编造。
- 使用相同模型、独立上下文，各自仅写答案；遵守所用编排系统的生命周期。模型按用户指定，不使用未经授权的默认替代模型。
- 对照结果放 skill 的同级 `<name>-workspace/iteration-N/`，不把会话、能力凭证和大批生成结果提交到 skill 仓库。
- 用 skill-creator 的 grader 格式保存逐条 evidence，再生成 benchmark 与官方 `eval-viewer/generate_review.py` 页面供人工查看。

## 初始版本检查记录

- YAML/frontmatter 合法，description 381 字符；入口 81 行；当次 20 个本地 Markdown 链接均可解析。
- 三对独立 Astra（`openai-codex/gpt-6-astra`）只读运行：有 skill 15/15，无 skill 6/15。
- 所有会话核验模型与工具动作；无目标工程编译/安装/进程操作。详细结果保存在本机 `vscode-as-workspace/iteration-1/`，不要求后来人拥有该生成目录。
- 主要价值是快速提供项目专用源码入口、调试配置、构建/打包命令、许可/helper 及隔离安装要点。

## 不能外推的结论

这是三个场景各一次的资料可用性测试，不是 live VSCode/UE 验收、触发准确率测量或统计显著性证明。无 skill 基线没有工程资料访问权，其通用定位和安全建议并非都错；按全部条件满足才算通过的复合要求会放大具体信息缺失。

若后续比较文档版本，基线应能读取旧 skill；若要比较真实实施效果，应授权独立环境与实际验收，再重新设计测试，不复用本轮通过率冒充生产成功率。
