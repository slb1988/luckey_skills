# SQLite 写锁诊断：事务观测与跨进程归因

适用：SQL 锁 / sql锁、SQLite 写锁、`database is locked`、`SQLITE_BUSY` / `SQLITE_LOCKED`、长事务、持锁进程定位及 Memory Hub 审核队列停滞。服务端实现与命令均位于 **memory-hub 服务仓库**，不是本 skill 的客户端 `scripts/`。

## 共享写库与观测边界

Hub API 多进程、hub-worker 和独立 dream 进程共享同一 metadata SQLite；WAL 支持读写并行，但同一数据库同一时刻只有一个 writer。Python `sqlite3` 不提供“谁持锁”的查询 API，因此诊断由应用事务状态与操作系统锁证据共同组成。

| 层 | 职责 | 能回答什么 |
|---|---|---|
| `src/memory_hub/infrastructure/database.py` | 共享连接/事务入口接入观测 | 哪个连接、PID/线程在等待写锁或已成功进入写事务 |
| `src/memory_hub/infrastructure/sqlite_diagnostics.py` | 后台慢事务/等待快照、进程身份与独立 sidecar | 事务调用位置、等待/持有时长；事务尚未结束时的状态 |
| Linux `/proc/locks` | 按目标数据库文件身份关联实际锁 | 当前内核写锁主 PID；包括绕过共享连接层的外部写者 |
| `scripts/diagnose_sqlite_locks.py` | 只读汇总应用快照与内核锁 | 区分确认写者、等待者、未归因内核写者和历史记录 |

新增写入路径应使用共享 `Database` 连接层，才能关联到事务调用位置；原生 `sqlite3` 或外部程序绕过该层时，只能由 Linux 内核识别 PID，不能补造其线程/业务调用点。

## 快照与证据生命周期

- 默认启用，慢事务/锁等待阈值为 **5 秒**。后台在操作仍进行时留存快照，不依赖 commit/rollback 后才打印耗时。
- sidecar 位于 `<数据库路径>.lockdiag/`，按进程保存，文件权限为 `0600`。诊断不写入被锁的 SQLite，不记录记忆正文、凭证、SQL 绑定值或原始 SQL 体。
- PID 必须结合进程身份与存活状态判读；Linux 使用 `proc_starttime` 校验，避免 PID 重用导致误归因。
- 进程异常退出后的快照仍可作为历史证据，但**历史 `writer_confirmed` 不代表当前仍持锁**。应用快照与内核锁也需对齐采样时刻，不能把时间错开的状态当成同一现场。
- 共享层的观测覆盖依赖所有写库进程加载新代码；API 主进程健康或单个 worker 有 sidecar，不代表其它 API 子进程和 dream 已纳入观测。

## 持锁者与等待者的证据口径

| 输出/观察 | 正确含义 |
|---|---|
| `writer_acquire_pending` / `phase=begin-immediate` 重试 | 正在抢锁的等待方，不是持锁者 |
| `writer_confirmed` + `successful_begin_immediate` | 该连接成功获得过写事务；结合进程身份、快照时刻和内核证据判定是否仍持有 |
| `kernel.writer_pids` 与有效事务快照对应 | 可把内核写锁 PID 关联到该进程的事务/线程及 `writer_callsite` |
| `unattributed_kernel_writer_pids` 非空 | 内核确认存在写者，但应用快照不足；只能报告 PID，不虚构调用点 |
| 已退出进程的快照 / 未确认连接候选 | 历史或候选证据，不能冒充实时锁主 |
| 内核 READ 锁 | WAL 下的读锁不等于阻塞其它写者的写锁 |

WAL 的写锁可能落在 **`-shm`**，不能只查主 DB inode，也不能把任意 READ/WRITE 锁不加区分地视为事务写锁；使用诊断器对目标 DB / `-shm` 的写锁关联结果。

连续 busy timeout 只证明持续争用，**不证明同一个 writer 连续持锁整个窗口**；等待者日志中的栈也不能证明被指向的函数在持锁。预览 `llm.complete` 位于写事务外，不能从其邻近的 `BEGIN IMMEDIATE` 报错推断 LLM 持锁。没有现场或有效历史关联时，结论应保留未知，而不是归罪于日志最密集的进程。

## Dream 终态空转的锁边界

<memory category="core-rules">
Dream 按 `local_date` 幂等；到每日调度时间后持续 poll，但当天 run 为 `completed` / `failed` 时已无须 claim。旧 `_claim_run` 在检查终态前就 `BEGIN IMMEDIATE`，因此没有业务写入的空转也会争抢 writer。
只读终态预检负责跳过无工作的 poll；真正 claim 仍须在短写事务内复查 run 状态与全局租约。预检不能替代并发互斥，减少空转也不等于消除了其它持锁源。
</memory>

## 只读诊断入口

先按 `METADATA_DATABASE_PATH` 确认真实库路径。NAS 默认部署的命令：

```bash
cd /share/Container/memory-hub
.venv/bin/python scripts/diagnose_sqlite_locks.py --db data/memory-hub.sqlite3
```

默认诊断目录为 `data/memory-hub.sqlite3.lockdiag/`。争用发生时优先采集诊断，再决定恢复操作；重启会释放现场锁，不能用重启后的“无 writer”追溯事故锁主。无需读取业务正文或连接 Neo4j，也不要为验证埋点而人为锁生产库。

修改观测机制时，最小验证应使用临时 SQLite 的真实跨进程持锁/争锁：在释放前确认持锁 PID 与等待者可区分、调用位置可关联、异常退出只留下历史证据、诊断故障不破坏业务。Linux 内核归因必须在 Linux 实测；macOS 上应用层探针通过不能代替该层验证。权威实现说明见服务仓库 `scripts/README.md` 与 `src/memory_hub/workers/README.md`。
