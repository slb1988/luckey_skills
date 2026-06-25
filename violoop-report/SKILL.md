---
name: violoop-report
description: 图文记录工具。当用户传来一张图片（截图/文件路径）并附上文字说明时，自动上传图片到 OSS 图床，然后以 Markdown 格式追加写入 workspace 下的记录文件。触发词：记录、record、log、笔记、note、写进去、存下来、记一下、配字记录、图文记录、用户反馈、反馈记录、feedback。即使用户只说"帮我记录一下"、"把这个存下来"、"加个截图到记录里"也应该触发此 Skill。也适用于纯文字反馈（无图片）。所有记录追加到同一个单文件中。
---

# violoop-report

记录工具：可带图片也可纯文字 → 上传 OSS → 追加到统一单文件。

**记录文件（唯一固定）：**
```
C:\Users\admin\.violoop\workspace\user-feedback.md
```

## 触发场景

- 用户在聊天中内嵌图片（`[Screenshot name=xxx.jpg ...]`）+ 配字
- 用户提供本地图片路径 + 配字
- 纯文字描述（无图片），也照常记录

## 执行流程

### Step 1：判断是否有图片

**有图片**时，来源分两种：

**A. 聊天内嵌图片**（最常见）
消息格式类似 `[Screenshot name=125485960e23233ec0ebddcecccbde00.jpg ...]`，图片没有本地路径，但 Violoop 会把它缓存到微信临时目录。用文件名 hash 去找：

```powershell
$hash = "125485960e23233ec0ebddcecccbde00"  # 从 name= 提取
$cacheBase = "$env:USERPROFILE\Documents\xwechat_files"
$imgPath = Get-ChildItem $cacheBase -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.BaseName -eq $hash } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
```

**B. 用户给出本地路径**
直接用该路径。

**无图片**：直接跳到 Step 3，只写文字。

### Step 2：上传图片到 OSS

```powershell
$ossScript = "C:\Users\admin\.violoop\skills\oss-upload\scripts\oss_upload.py"
$output = python $ossScript "$imgPath"
$ossUrl = ($output | Select-String "^OSS_URL:").Line -replace "OSS_URL: ", ""
```

- 脚本自动读取 `~/.claude/oss_config.env`，自动安装 ossutil
- 输出 URL 形如 `https://<bucket>.<endpoint>/images/<timestamp>.jpg`
- 若 `$ossUrl` 为空，报错停止，**不写入记录**

### Step 3：追加写入记录文件

```powershell
$reportFile = "C:\Users\admin\.violoop\workspace\user-feedback.md"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

if (-not (Test-Path $reportFile)) {
    "# 用户反馈记录`n" | Set-Content $reportFile -Encoding UTF8
}
```

**有图片时** — embed + 配字 + 原始 URL：
```powershell
$entry = @"

---

**$timestamp**

![$caption]($ossUrl)

$caption

$ossUrl
"@
Add-Content $reportFile $entry -Encoding UTF8
```

**纯文字时**：
```powershell
$entry = @"

---

**$timestamp**

$caption
"@
Add-Content $reportFile $entry -Encoding UTF8
```

### Step 4：回复用户

**有图片时：**
```
✅ 已记录

![配字](ossUrl)
📝 配字
🔗 ossUrl
📁 user-feedback.md
```

**纯文字时：**
```
✅ 已记录

📝 用户说的话
📁 user-feedback.md
```

## 注意事项

- 聊天内嵌图片的缓存路径：`%USERPROFILE%\Documents\xwechat_files\...\temp\RWTemp\<年月>\<hash>.jpg`
- 图片记录同时写 embed + URL，embed 渲染图片，URL 方便复制引用
- 配字作为图片 alt text 和正文都写，保证可搜索
- 每条记录前加 `---` 分隔线，时间戳加粗
- 所有记录追加到同一文件，不覆盖
- OSS 上传失败时不写入记录，避免 broken image
