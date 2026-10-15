# Skill Benchmark: vscode-as

**Model**: openai-codex/gpt-6-astra
**Date**: 2026-09-21T23:52:44Z
**Evals**: 1, 2, 3 (1 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 40% ± 40% | +0.60 |
| Time | 132.0s ± 17.1s | 141.8s ± 38.8s | -9.8s |
| Tokens | 61817 ± 6855 | 35098 ± 12945 | +26719 |

## Notes

- 三个只读方案题、每配置一次；这是接手资料可用性测试，不是实际 VSCode/UE 集成验收，也不是统计显著性结论。
- 有 skill 15/15，无 skill 6/15；主要分差来自项目固定配置名、源码路径、构建命令、包入口/许可证和隔离安装方法。
- 基线不能读取项目文档或源码；其一般定位与安全建议并非都错，不能把资料可访问性差异归因为模型通用能力。
- 所有六个会话已核对模型 gpt-6-astra；动作仅含允许的技能资料读取、答案文件写入和 Orca 生命周期命令，没有工程编译/安装/启动。
- pass rate 的 stddev 是三个不同场景间的差异，不是同场景重复实验的稳定性；没有重复运行评估方差。
- 时间为 dispatch 到 worker_done 的墙钟时间；token 包含 input、cacheRead 和 output，不能与纯生成延迟/唯一输入长度混为一谈。
- 无越权/不虚报运行结果等断言两组均较好，区分度主要依赖项目具体知识；结果不覆盖 skill 自动触发准确率。
