# 客户端构建与 exe 分发

客户端：`ws:maindev` `Tools/ue-launcher/`（Tauri）。MainDev 是**非 Unicode** P4（192.168.2.236:1666），不要设 utf8 charset。

## 构建入口

```bash
cd Tools/ue-launcher
bun run build:exe        # 前端 build + tauri build --no-bundle，产出 release exe
```

- **prebuild 副作用**：会 P4 checkout tracked exe（`src-tauri/target/release/ue-launcher.exe`）。若该 exe 正被运行中的 launcher 占用，Cargo 删除失败（os error 5），整个构建卡住。
- 构建前确认无 launcher 进程占用；有占用**不要杀进程**，改用独立 target：

```bash
CARGO_TARGET_DIR=src-tauri/target-portable-<时间戳> bun run build:exe
```

独立目录可复用依赖缓存；产物在 `<target>/release/ue-launcher.exe`。验证产物：构建退出码 + hash + 关键能力字符串 + x64 GUI 子系统核实（Tauri release 两次构建 hash 可不同，hash 一致不是必须的，内容核实才是）。

## exe 的三个位置

| 位置 | 性质 | 更新方式 |
|---|---|---|
| 独立 target 产物 | 编译输出 | 构建产生 |
| `src-tauri/target/release/ue-launcher.exe` | **P4 tracked**，团队分发/构建系统用 | `p4 edit` 后覆盖，reopen 进同源功能 CL（跟随"exe 与源码同 CL"惯例） |
| `%LOCALAPPDATA%\UnrealGameSync\Tools\UeLauncher\ue-launcher.exe` | 用户实际运行的已安装副本 | 确认无进程占用后备份旧版到 `backups/<时间戳>/` 再替换 |

更新 tracked exe **不等于**用户机器生效——已安装副本是独立文件，两处都要管。替换前必须再次探测进程占用；占用就报告等用户关闭，不杀进程。只改程序二进制：不改 settings/HKCU/快捷方式，不启动 GUI 验收（GUI setup 有协议注册副作用）。

## 测试入口

```bash
cd Tools/ue-launcher
bun run test              # 前端（也可 bun test ./tests 指定目录；不要在 MainDev 根跑 bun test，会扫全仓）
cargo test --manifest-path src-tauri/Cargo.toml   # Rust
```

- 安装/便携/ZIP 测试用临时目录 + fixture EXE，真实 spawn→检测→打开/取消，无副作用。
- 740 回归是**无 UAC** 的分支/命令构造测试（不执行 PowerShell RunAs）；真实 UAC 批准/取消需单独授权的隔离环境。
- 部分 SMB/现场/helper 测试是显式 ignore 的，不算失败。

## P4 收尾

源码+测试+文档+tracked exe 建专用英文 pending CL，`p4 opened`/`describe` 核实，不 submit。改了 SKILL.md 时用 `node .claude/build-index-unreal.js`（MainDev 仓库根）安全重建索引——**不运行含全局 revert 的 bat 脚本**；GUI 派生文件不 checkout，与本任务无关的存量漂移只报告不代清理。
