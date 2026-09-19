# 排障速查

按症状定位，每条给根因与处置。未列出的先按 architecture.md 的契约逐项核对（包装、schemaVersion、包型、entryPoint）。

## 客户端

| 症状 | 根因与处置 |
|---|---|
| `Cannot fetch toolbox manifest 192.168.2.13:5000: builder error` | 设置里是裸 `IP:端口`，缺协议和路径。已修：自动规范化为 `http://<IP:端口>/ue-launcher/tools`。遇到先确认运行的 exe 是否含规范化逻辑（tracked/LocalAppData 两个位置都可能还是旧版）。 |
| 工具箱整份报 "Invalid toolbox manifest JSON" | 可能原因：响应非 JSON（代理/错误页）、schemaVersion≠1、目录含旧客户端不认识的 installerType（portable/zip）。先看服务端返回原文，再确认客户端版本。 |
| 点击安装报 `os error 740 请求的操作需要提升` | 安装器 manifest 要求管理员。现有代码有 PowerShell RunAs 回退；先核实运行的 exe 是否含回退（构建来源/hash），再复现看是普通错误还是回退本身失败。UAC 取消=用户操作，不算失败。 |
| 安装完成但仍灰色 | 就绪检测只看 launchCandidates/绑定/登记；自定义安装目录不在候选里时用"选择已安装程序"手选绑定。安装器是引导器提前退出时等检测或手动重检。 |
| 编译卡 os error 5 无法删除 target exe | 旧 launcher 进程占用 tracked exe。不杀进程；`CARGO_TARGET_DIR` 独立目录编译，替换等进程退出。 |
| 改了代码但行为没变 | 用户跑的是 LocalAppData 已安装副本，tracked exe/源码改动不会自动到那。三个 exe 位置见 client-build.md。 |
| 离线时工具箱消失 | 不应该：拉取失败须保留最后有效缓存，已安装仍可启动。若复现说明缓存保护被破坏。 |

## 服务端 / 部署

| 症状 | 根因与处置 |
|---|---|
| `/ue_launcher/...` 404 | 前缀是连字符 `/ue-launcher`。下划线路径全 404 不代表未部署。 |
| 配置重启后丢失 | UE_LAUNCHER_DATA_ROOT 等写在 `venv/bin/activate` 标记块；**重建 venv 会丢**。重建前备份恢复，或迁受管持久配置。 |
| deploy.sh sync 报 "Can't clobber" | 目标文件带 writable 位（历史 unshelve 遗留）：`chmod u-w` 后重新 sync。 |
| deploy.sh 权限拒绝 | sync 后脚本丢 +x，用 `bash deploy.sh` 跑。 |
| deploy 失败 P4 charset | auto-server 的 P4 是 unicode 服务器：必须 `P4CHARSET=utf8`/`p4 -C utf8`。 |
| 迁移 head 对不上 | `database_migration_guide` 文档里的 head 记录可能过时；以 migrations 目录实测唯一 head 为准。 |
| 回滚时 alembic 报 "Can't locate revision" | 删了迁移文件但 alembic_version 还指向它。正确回滚：只回滚代码、保留新增 nullable 列和迁移文件。 |
| 上传 .exe 后类型变了 | 已修：显式 portable 保留；老版本服务端按扩展名强制改写。manifest 里核对 installerType。 |
| CLI 一跑就起调度器/副作用 | 缺 `DISABLE_SCHEDULER=1` 前缀。 |
| 外链包 hash 与源不符 | 外链只在发布时抓取计算一次；上游同 URL 换内容后必须重新发布。建议优先服务器托管。 |

## P4 协作

| 症状 | 根因与处置 |
|---|---|
| 需要把未提交改动弄到 auto-server | **不要 shelf**（用户硬性规则）。建专用 pending CL 后报告用户，由用户决定提交后 sync 或其他传输方式。 |
| `p4 describe -s` 看不到 shelf 文件 | `-s` 只看 opened 文件；shelved 文件用 `describe -s -S`。shelved-only CL 的 describe -s 无 Affected files。 |
| 用户手动提交了 worker 的 pending CL | 提交后原编号可能重编号；worker 后续改动不再被跟踪，需重新 `p4 edit` + 新 CL。收尾前必须 `p4 opened` 核实。 |
