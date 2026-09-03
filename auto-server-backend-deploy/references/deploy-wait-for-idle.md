# deploy.sh 等待空闲机制与双脚本分叉（2026-09-04 排查确认）

## 分叉现状（根因）

存在两份 deploy.sh，等待逻辑只进了 depot 版：

| 脚本 | `wait_for_idle` | 说明 |
|------|-----------------|------|
| depot 版 `/data/py_automation/backend/deploy.sh` | CL 1427（2026-09-03）起有 | 服务器已同步运行 |
| skill 版 `~/.pi/skills/auto-server-deploy/scripts/deploy.sh` | **至今没有**（停留 08-29 版） | 而两份 SKILL.md 的「快速开始」都指向它 |

后果：CL 1427 之前的所有部署本来就没有等待机制；之后只要按 skill 文档走一键部署，保护仍被完全绕过（sync 完直接 `kill -9`）。

## depot 版 `wait_for_idle` 机制

- 轮询 `GET /server_status/busy`，**连续 2 次空闲**才执行 kill，最长等 5 分钟。
- 已知缺陷 1：内有 PID 文件捷径——读到 `python3_pid.log` 的 PID 失效时会**跳过 busy 查询直接判空闲**；而该 PID 文件本身不可信（见 SKILL.md 陷阱 2，nohup 包装壳 PID）。
- 已知缺陷 2：最后一次空闲确认到 kill 之间有 ~1s TOCTOU 窗口，只能压缩不能归零（09-02 CL 128399 那类秒级竞态由 B 层 worker 守卫兜底，见陷阱 5）。

## busy 语义：AI review 等编译时服务器就是空闲（设计如此）

AI review 触发 TeamCity 构建后进入 `await_compile` 状态：**构建跑在 TC 上，服务器侧只是 DB 里的持久化状态**，无进程内在途工作。此时 `/server_status/busy` 返回空闲是正确判定——重启无损，新进程启动后正常接收 `tc_callback`，review 续跑（实测：06:26 重启，06:34 新进程收到回调，review 121 compile settle ✅）。

排查「重启时任务没结束是否造成损害」的正确姿势：对比重启前后日志里 review 的 `tc_callback` 是否被新进程正常接收，而不是纠结 kill 时 busy 状态。

## 修复实施（2026-09-04 已完成）

skill 版 deploy.sh 后端段已改为整体 `bash /data/py_automation/backend/deploy.sh` 委托执行（不再自行 kill），环境变量（/etc/environment + npm-global/pnpm PATH + FEISHU_ASSISTANT_PI_BIN）由父脚本在调用前 source/export，子进程继承；两份 SKILL.md 已同步 FORCE_DEPLOY=1 与 busy 语义说明。

**注意：修复在本机 skills 仓库提交后，还需同步服务器上的 `~/.pi/skills` 副本才真正生效**（那是 agent 实际执行的脚本）。
