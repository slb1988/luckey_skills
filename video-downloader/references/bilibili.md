# B站（bilibili）视频下载

## 依赖

```bash
pip install you-get
```

验证安装：`you-get --version`

---

## 支持的页面类型

| 类型 | 典型 URL 示例 |
|------|-------------|
| 单个视频 | `bilibili.com/video/BVxxxxxxxxxx` |
| UP 主空间（投稿） | `space.bilibili.com/<uid>/video` |
| 收藏夹 | `space.bilibili.com/<uid>/favlist?fid=<fid>` |
| 合集（series/season） | `space.bilibili.com/<uid>/lists/<sid>` |

---

## 提取 BV 号

在目标页面打开浏览器开发者工具（F12），切到 Console，执行：

```javascript
const links = Array.from(document.querySelectorAll('a[href*="bilibili.com/video/"]'));
const bvIds = links.map(a => {
  const match = a.href.match(/BV[A-Za-z0-9]{10}/);
  return match ? match[0] : null;
}).filter(Boolean);
const unique = [...new Set(bvIds)];
copy(unique.join('\n'));  // 直接复制到剪贴板
console.log(`提取到 ${unique.length} 个 BV 号`);
```

将剪贴板内容粘贴到文本文件（如 `bv_list.txt`），每行一个 BV 号。

> **注意**：空间/收藏夹页面需要滚动到底部加载全部视频，再执行提取。

---

## 下载

单个视频：

```bash
you-get -c /path/to/config/bilibili_cookies.txt https://www.bilibili.com/video/BV1xxxxxxxxxx
```

批量下载（BV 列表文件，每行一个 BV 号）：

```bash
COOKIES="/path/to/config/bilibili_cookies.txt"
while IFS= read -r bv; do
  [[ -z "$bv" ]] && continue
  you-get -c "$COOKIES" "https://www.bilibili.com/video/$bv"
done < bv_list.txt
```

---

## 踩坑记录

1. **cookies 失效**：下载失败报 401/403 时，重新导出 cookies 覆盖 `config/bilibili_cookies.txt`（参考 `config/bilibili_cookies.txt.template` 内的获取方式）

2. **you-get 报 bad interpreter**：shebang 指向旧版 Python，用 `pip3 install you-get` 重装即可

3. **cookies 格式**：you-get 需要 Netscape cookies.txt 格式，浏览器插件导出的 JSON 需手动转换（参考 SKILL.md 中的转换规则）

4. **高清画质**：默认下载最高可用画质，需要 cookies 有效且账号有权限才能获取 1080P+

5. **弹幕文件**：下载完成后会同时生成 `.cmt.xml` 弹幕文件，这是 you-get 默认行为
