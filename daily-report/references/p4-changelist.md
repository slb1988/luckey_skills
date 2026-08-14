# P4 提交记录查询参考

## 1. 服务器配置

| 名称 | 地址 | 用户名 | 说明 |
|------|------|--------|------|
| 公司项目仓库 | `192.168.2.236:1666` | `sunlaibing` | 主要项目代码 |
| 内网 CICD | `192.168.2.13:1666` | `admin_sun` | CI/CD 配置和脚本（Unicode 服务器，需 `P4CHARSET=utf8`） |
| 个人服务器 | `10.77.77.6:1666` | `admin` | 个人项目（Unicode 服务器，需 `P4CHARSET=utf8`） |

> **本机 `p4 set P4USER=admin_sun`**，连接用户默认取此值。访问 192.168.2.236 和 10.77.77.6 时必须用全局 `-u` 覆盖连接用户，否则在认证阶段就被 `p4 protect` 拒绝（`Access for user 'admin_sun' has not been enabled by 'p4 protect'`）。

---

## 2. 查询命令

### 2a. 获取当日 CL 列表

```bash
# 格式：p4 -p <server> -u <user> changes -u <user> -s submitted @YYYY/MM/DD,@YYYY/MM/DD+1
# 两个 -u 语义不同、缺一不可：
#   全局 -u（子命令前）：连接用户，覆盖本机 P4USER 配置
#   子命令 -u（changes 后）：按用户过滤结果，省略则列出该服务器所有人的 CL
# 示例（查询 2026/03/13 的提交）：

p4 -p 192.168.2.236:1666 -u sunlaibing changes -u sunlaibing -s submitted @2026/03/13,@2026/03/14
P4CHARSET=utf8 p4 -p 192.168.2.13:1666 -u admin_sun changes -u admin_sun -s submitted @2026/03/13,@2026/03/14
P4CHARSET=utf8 p4 -p 10.77.77.6:1666 -u admin changes -u admin -s submitted @2026/03/13,@2026/03/14
```

**典型输出：**
```
Change 12345 on 2026/03/13 by sunlaibing@WORKSTATION 'Fix crash in character controller'
Change 12346 on 2026/03/13 by sunlaibing@WORKSTATION 'Update animation blueprint'
```

### 2b. 获取 CL 详情

```bash
# 格式：p4 -p <server> -u <user> describe -s <CL>
# 全局 -u 同样必需（连接用户）；-s 参数：只显示 shelved files（精简输出，含描述和文件列表，不含 diff）

p4 -p 192.168.2.236:1666 -u sunlaibing describe -s 12345
P4CHARSET=utf8 p4 -p 192.168.2.13:1666 -u admin_sun describe -s 12345
P4CHARSET=utf8 p4 -p 10.77.77.6:1666 -u admin describe -s 12345
```

**典型输出：**
```
Change 12345 by sunlaibing@WORKSTATION on 2026/03/13 10:30:00

	Fix crash in character controller when jumping near walls

Affected files ...

... //depot/Project/Source/Character/CharacterController.cpp#42 edit
... //depot/Project/Source/Character/CharacterController.h#15 edit
... //depot/Project/Config/DefaultGame.ini#8 edit
```

---

## 3. 输出解析

### 从 `p4 changes` 提取 CL 信息

- **CL 号**：行首 `Change XXXXX`
- **日期**：`on YYYY/MM/DD`
- **描述**：行末单引号内的文本（可能被截断为前 31 字符）

### 从 `p4 describe -s` 提取详情

- **完整描述**：`Change XXXXX by ...` 之后的缩进段落（直到 `Affected files` 行）
- **文件列表**：`Affected files ...` 之后，每行 `... //depot/...` 格式
- **文件数量**：统计 `...` 开头的行数

---

## 4. 错误处理

| 错误类型 | 表现 | 处理策略 |
|----------|------|----------|
| 连接超时 | 命令挂起 > 10s 或 `TCP connect to ... failed` | 跳过该服务器，日记中标注 `（连接失败）` |
| Unicode 拒绝 | `Unicode server permits only unicode enabled clients` | 缺少 `P4CHARSET=utf8`，需在所有 192.168.2.13 和 10.77.77.6 命令前添加 |
| 用户过滤失效 | 返回全部用户的 CL | `changes -u` 才是过滤条件；全局 `-u` 只设连接用户、不过滤结果 |
| protect 拒绝 | `Access for user 'admin_sun' has not been enabled by 'p4 protect'` | 连接用户取自本机 `p4 set P4USER`，须加全局 `-u <该服务器用户>` 覆盖 |
| 权限拒绝 | `You don't have permission for this operation` | 跳过，标注 `（权限不足）` |
| 无提交记录 | 命令返回空 | 正常，不输出该服务器条目 |
| p4 未安装 | `'p4' is not recognized` | 跳过所有 P4 查询，日记中标注 `（p4 未安装）` |

**超时控制：**

```bash
# Windows 环境使用 timeout 命令包裹（或直接观察响应时间）
# 若 10 秒内无响应，Ctrl+C 并标记为连接失败
```

---

## 5. 输出格式（DailySucc 条目）

**单条 CL：**
```markdown
- ✅ **P4 提交 [服务器名] CL XXXXX**：[描述摘要，30字以内]（涉及 N 个文件）
```

**示例：**
```markdown
- ✅ **P4 提交 公司项目仓库 CL 12345**：修复角色控制器跳跃崩溃问题（涉及 3 个文件）
- ✅ **P4 提交 公司项目仓库 CL 12346**：更新动画蓝图（涉及 1 个文件）
- ✅ **P4 提交 内网 CICD CL 789**：更新构建脚本配置（涉及 2 个文件）
```

**连接失败时：**
```markdown
- ⚠️ **P4 个人服务器**：（连接失败）
```

**排列规则：**
- 同一服务器的 CL 条目相邻排列
- 服务器顺序：公司项目仓库 → 内网 CICD → 个人服务器
- 无提交的服务器不输出条目（连接失败除外）
