---
name: oss-upload
description: 上传本地文件到阿里云 OSS，返回公网访问地址。用于截图、图片、附件等需要生成外链的场景。当用户提到"上传图片"、"上传文件"、"OSS"、"上传到云端"、"生成图片链接"、"图床"、"picgo"、"获取外链"时触发。即使用户只说"帮我把这张图传上去"也应该考虑使用此 Skill。【附加能力】当用户给出一个本地 Markdown 文件路径并要求"替换图片链接"时，自动扫描文件中所有外部图片链接（如飞书、语雀等临时鉴权链接），下载后上传 OSS 并原地替换，已是 OSS 链接的跳过不处理。
---

# oss-upload

上传本地文件到阿里云 OSS，输出可直接使用的公网访问地址。

## 快速使用

```bash
python .claude/skills/oss-upload/scripts/oss_upload.py /path/to/file.png
```

成功后输出：
```
OSS_URL: https://your-bucket.oss-cn-shanghai.aliyuncs.com/images/1749174722196.png
```

`OSS_URL:` 开头的行是访问地址，供后续流程提取使用：

```bash
# macOS/Linux
URL=$(python3 .claude/skills/oss-upload/scripts/oss_upload.py /path/to/file.png | grep "^OSS_URL:" | cut -d' ' -f2)
```

```powershell
# Windows PowerShell
$output = python .claude\skills\oss-upload\scripts\oss_upload.py C:\path\to\file.png
$URL = ($output | Select-String "^OSS_URL:").Line -replace "OSS_URL: ", ""
```

## 首次配置

脚本会自动检查 `~/.claude/oss_config.env`：

- **文件不存在**：自动从模版复制并提示填写
- **含占位符 `your_*`**：提示用户手动编辑后重试

配置模版位于 `config/oss_config.env.template`，字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| `OSS_ACCESS_KEY_ID` | 阿里云 AccessKey ID | `LTAI5t...` |
| `OSS_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret | `NEXDx...` |
| `OSS_BUCKET` | Bucket 名称 | `my-bucket` |
| `OSS_ENDPOINT` | 地域 Endpoint | `oss-cn-shanghai.aliyuncs.com` |
| `OSS_PREFIX` | 存储路径前缀 | `images` |

## ossutil 自动安装

脚本启动时检查 ossutil 是否可用，若未安装则自动下载对应平台版本并安装到 `~/bin/`：

| 平台 | 下载包 | 安装路径 |
|------|--------|---------|
| macOS | `ossutil-2.3.0-mac-amd64.zip` | `~/bin/ossutil` |
| Windows | `ossutil-2.3.0-windows-amd64.zip` | `%USERPROFILE%\bin\ossutil.exe` |
| Linux | `ossutil-2.3.0-linux-amd64.zip` | `~/bin/ossutil` |

## 文件命名规则

上传文件名固定为毫秒时间戳 + 原始扩展名，例如 `20260605143022196.png`，确保不冲突。

## 脚本路径

- 主脚本：`scripts/oss_upload.py`（Python 3.6+，无第三方依赖，跨平台）
- 配置模版：`config/oss_config.env.template`
- 运行时配置：`~/.claude/oss_config.env`（用户手动填写，不纳入版本控制）

---

## Markdown 文件图片链接批量迁移到 OSS

当参数为一个本地 Markdown 文件路径时（而非图片文件），执行以下流程将文件内所有外部图片链接替换为 OSS 永久链接。

### 触发条件

用户给出一个 `.md` 文件路径，并说"替换图片链接"、"迁移图片到 OSS"、"把图片上传到自己服务器"等类似意图。

### 执行流程

**第一步：扫描图片链接**

读取目标 Markdown 文件，提取所有 `![...](URL)` 格式的图片 URL：

```bash
grep -oP '!\[.*?\]\(\K[^)]+' /path/to/file.md
```

**第二步：过滤——跳过已是 OSS 链接的图片**

检查每个 URL 是否已经是 OSS 地址（URL 中含 `aliyuncs.com`）。已迁移的直接跳过，不重复上传。

**第三步：并行下载所有需要处理的图片**

创建临时目录，用 curl 批量并行下载（每批 10~13 个）：

```bash
mkdir -p /tmp/md_imgs
curl -sL "URL1" -o /tmp/md_imgs/img_01.png &
curl -sL "URL2" -o /tmp/md_imgs/img_02.png &
# ...
wait
```

下载后检查文件大小，若为 0 字节说明链接已失效，跳过并告知用户。

**第四步：逐一上传到 OSS**

```bash
SCRIPT="/path/to/.claude/skills/oss-upload/scripts/oss_upload.py"
for f in /tmp/md_imgs/img_*.png; do
  OSS_URL=$(python3 "$SCRIPT" "$f" | grep "^OSS_URL:" | cut -d' ' -f2)
  echo "$f -> $OSS_URL"
done
```

**第五步：用 Edit 工具原地替换文件中的链接**

对每个原始 URL 和对应 OSS URL，逐一执行 Edit 替换：
- 旧：`![Image](原始外部URL)`
- 新：`![Image](OSS永久URL)`

**第六步：验证**

```bash
grep -c "原始域名关键字" /path/to/file.md
```

确认文件中的图片链接已全部替换（非图片的普通超链接 `[text](URL)` 保留不动）。

### 注意事项

- **只替换图片链接**：`![...](URL)` 格式。普通超链接 `[text](URL)` 不处理。
- **已是 OSS 链接的跳过**：URL 中含 `aliyuncs.com` 的不重新上传。
- **下载失败的链接跳过**：告知用户哪些图片失效，需手动处理。
- **并行下载提速**：图片数量多时分批并行（每批 10~13 个），wait 后再上传。
