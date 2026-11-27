# 合成书库演练

三个用例（依次为 `intake`、`replace`、`index`）对应 `evals.json`。每次为每个运行创建**不同、尚不存在**的目录；不要用真实书库做对照实验。

```sh
python3 make_fixture.py intake "$tmp/with-skill/Books" --tool "$trusted_tool"
```

`trusted_tool` 是书库自带的可信 `书库工具.py`。生成器只复制这一个程序，书、作者、分类、书目和指纹均在临时目录构造。把生成的 Books 路径和该用例的用户原话交给执行者。有 skill 组额外提供本 skill；基线组不提供，其余条件相同。依据原文件和最终书目、指纹、导航、报告或迁移清单核对结果，而不是只看文字答复。
