# SSH Key 生成与 GitHub 绑定

## 生成 SSH Key（Ed25519）

```bash
ssh-keygen -t ed25519 -C "your-label@nas" -f ~/.ssh/id_ed25519 -N ""
```

参数说明：
- `-t ed25519` — 使用 Ed25519 算法（更安全、更快）
- `-C "your-label@nas"` — 注释标签，方便在 GitHub 上识别
- `-f ~/.ssh/id_ed25519` — 私钥路径
- `-N ""` — 不设密码（空 passphrase）

生成后得到：
- `~/.ssh/id_ed25519` — 私钥（保密，不要分享）
- `~/.ssh/id_ed25519.pub` — 公钥（粘贴到 GitHub）

查看公钥内容：
```bash
cat ~/.ssh/id_ed25519.pub
```

## 添加到 GitHub

打开 https://github.com/settings/ssh/new ，粘贴公钥内容。

- Title 可填 "QNAP NAS" 或 "NAS453D" 方便识别
- Key type 选 "Authentication Key"

## 信任 GitHub 主机（添加 known_hosts）

QNAP 可能没有 `ssh-keyscan` 命令（需 `openssh-client` 包，又需要 admin 权限安装）。**绕过方法：直接用系统 ssh 的 accept-new 模式**：

```bash
/usr/bin/ssh -o StrictHostKeyChecking=accept-new -T git@github.com
```

预期输出：
```
Warning: Permanently added 'github.com' (ED25519) to the list of known hosts.
Hi slb1988! You've successfully authenticated, but GitHub does not provide shell access.
```

这条命令以后 `git fetch / push / clone` 就不会再报 host key verification 错误了。

如果 `/usr/bin/ssh` 也不可用，手写 known_hosts：

```bash
# 从另一台能连 GitHub 的机器获取
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
```

或手动从 https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints 获取指纹信息。

## 启动 SSH Agent

QNAP 环境可能没有自动启动 ssh-agent，导致 git 操作报错 `sign_and_send_pubkey: no mutual signature algorithm`。

**每次重新登录后执行**：

```bash
eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519
```

验证 agent 中的 key：

```bash
ssh-add -l
```

### 自动化：写入 ~/.profile

```bash
cat >> ~/.profile << 'EOF'

# Start ssh-agent and add key if not already running
if ! pgrep -u "$USER" ssh-agent > /dev/null; then
    eval $(ssh-agent -s) > /dev/null
    ssh-add ~/.ssh/id_ed25519 2>/dev/null
fi
EOF
```

这样每次 SSH 登录自动启动 ssh-agent 并加载 key。

## 测试 SSH 连接

```bash
ssh -T git@github.com
```

成功输出：
```
Hi USERNAME! You've successfully authenticated, but GitHub does not provide shell access.
```

## 常见问题

### Host key verification failed

```
Host key verification failed.
fatal: Could not read from remote repository.
```

**原因**：GitHub 的公钥指纹不在 `~/.ssh/known_hosts` 中。

**解决**：执行 `ssh -o StrictHostKeyChecking=accept-new -T git@github.com`。

### Permission denied (publickey)

```
git@github.com: Permission denied (publickey).
```

**原因**：SSH key 未添加到 GitHub 或本地未加载。

**排查**：
1. `ssh-add -l` — 看 agent 里有没有 key
2. 没有则先 `eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519`
3. `ssh -T git@github.com` — 验证认证
4. 确认公钥确实绑定到了 https://github.com/settings/keys

### sign_and_send_pubkey: no mutual signature algorithm

```
sign_and_send_pubkey: no mutual signature algorithm
git@github.com: Permission denied (publickey).
```

**原因（可能多个）**：
1. **ssh-agent 未启动或未加载 key** — 最常见的 QNAP 场景
2. **known_hosts 中 github.com 使用了旧算法**（如 RSA），但服务器返回 Ed25519 造成不匹配

**排查步骤**（按顺序）：

```bash
# 1. 查看 agent 是否运行
echo $SSH_AUTH_SOCK
# 若为空 -> ssh-agent 未运行

# 2. 查看 agent 里有没有 key
ssh-add -l
# 若报 "Could not open a connection..." -> ssh-agent 没启动
# 若报 "The agent has no identities" -> key 没加载

# 3. 启动 agent 并加载 key
eval $(ssh-agent -s)
ssh-add ~/.ssh/id_ed25519

# 4. 排除 known_hosts 问题
ssh-keygen -R github.com                                   # 删掉旧记录
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts    # 重新添加（需 openssh-client）
# 如果没有 ssh-keyscan，手动删 / 文件后重新 accept：
ssh -o StrictHostKeyChecking=accept-new -T git@github.com

# 5. 再次测试
ssh -T git@github.com
```

**终极方案**（若上面都不行）：
```bash
# 清理环境后重新加载
killall ssh-agent 2>/dev/null
eval $(ssh-agent -s)
ssh-add ~/.ssh/id_ed25519
ssh-keygen -R github.com
ssh -o StrictHostKeyChecking=accept-new -T git@github.com
```

## 如何为多个仓库配置不同的 Deploy Key

如果某些仓库需要使用 Deploy Key 而不是个人 SSH key，通过 `~/.ssh/config` 实现：

```
# ~/.ssh/config
Host github.com-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519

Host github.com-repoA
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_repoA
```

对应 git remote 设为：
```bash
git remote set-url origin git@github.com-repoA:USER/REPO.git
```
