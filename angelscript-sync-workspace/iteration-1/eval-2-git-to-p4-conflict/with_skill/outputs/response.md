仅桌面演练；方向为 unrealengine-angelscript → maindev，未迁移、未编译，不读写真实基线。

**回灌清单**：固定G1，仅取G0→G1的插件范围增量，不整目录复制、不重复回灌P4导入内容。VM新源记add；绑定文件记modify/conflict；旧源记delete，须有删除历史且目标未独立修改，否则转冲突。G0已有专属说明文档不自动新增到P4；目标独有文件preserve，缓存exclude，不误排有效ThirdParty源码。逐项记相对路径、源版本/哈希及目标原版本/哈希、opened状态。

**冲突处理**：以G0对应内容为基底，对G1与MainDev独立提交后的内容做三方比较，合并保留双方改动；不能兼容则请用户裁决，不因方向明确而覆盖。用户default opened原样保留，重叠时暂停该项确认，不覆盖、回滚或擅自reopen。解决冲突后冻结清单，复核未漂移再批量复制，更新mtime、核验哈希；合并差异记原因。

**P4边界**：核实真实映射与have/head，字符集仅命令/连接级设置。建立独立编号pending CL，既有文件先edit -c <CL>再复制，新增/删除用add/delete -c <CL>，不绕过checkout；仅对清单reconcile并核对opened。本次改动不留default，不动用户default及其他CL，不shelf、不submit。

**编译与记账**：按MainDev现行规则构建实际Editor/项目目标，不照搬Git侧命令。验收清单，保存真实退出码、Result: Succeeded、日志路径，区分实际编译/链接与no-op；直接兼容问题最小修复后重建，超范围先确认。仅文件与构建均通过才记“工作区已验证、待提交”，按方向分别记录范围、G0/G1哈希、目标原版本、pending CL、适配、构建证据与日期。pending不等于submitted；失败只记失败/阻塞与pending，不推进成功游标。用户日后提交后核对实际内容，再补最终submitted CL。本题仅说明记账原则，真实状态不更新。
