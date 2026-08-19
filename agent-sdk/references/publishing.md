# 发布 pyauto-agent / pyauto-computer 新版本

在 `pyAutomation/agent-sdk/`（SDK）或 `pyAutomation/computer-cli/`（CLI）改完源码后：

1. **升版本号**：改 `pyproject.toml` 的 `version`（先 `p4 edit`）。pypiserver **拒绝同版本重传**。
2. **临时目录构建**（不要在 P4 只读目录里 build）：`uv build --out-dir dist`；公共 PyPI 不通时
   加 `--offline`（build backend 走 uv 缓存）。
3. **上传 pypiserver**（认证 `admin / sdk123456`；**务必绕过系统代理**）：
   ```bash
   NO_PROXY=192.168.2.13 uvx twine upload --repository-url http://192.168.2.13:8080 \
       --username admin --password sdk123456 dist/*
   ```
4. **同步平台托管 wheel**：`python computer-cli/scripts/build_packages.py`（仓库根执行）会重建
   `pyauto_agent` + `pyauto_computer` 两个 wheel 到 `backend/.../computer_install/packages/`
   （清旧换新），`p4 add/edit` 随版本改动同 CL 提交——这是 install.ps1/sh 的安装源。
5. **验证**：内网源列表页出现新版本 wheel + tar.gz；`/computer/packages` 列出新 wheel。
6. **收尾**：版本号 + 源码改动走正常 P4 流程提交。
