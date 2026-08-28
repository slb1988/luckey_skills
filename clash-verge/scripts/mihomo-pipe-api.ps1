# mihomo 命名管道 API 封装（Windows 专用）
# 用法：
#   powershell -ExecutionPolicy Bypass -File mihomo-pipe-api.ps1 -ApiPath "/version"
#   powershell -ExecutionPolicy Bypass -File mihomo-pipe-api.ps1 -ApiPath "/proxies/OpenAI"
#   powershell -ExecutionPolicy Bypass -File mihomo-pipe-api.ps1 -ApiPath "/proxies/OpenAI" -Method PUT -Body '{"name":"JP01"}'
#   powershell -ExecutionPolicy Bypass -File mihomo-pipe-api.ps1 -ApiPath "/proxies/JP01/delay?timeout=5000&url=https%3A%2F%2Fwww.gstatic.com%2Fgenerate_204"
# 注意：中文分组/节点名需先 URL 编码，如 代理 -> %E4%BB%A3%E7%90%86
param(
    [Parameter(Mandatory=$true)][string]$ApiPath,
    [string]$Method = 'GET',
    [string]$Body = $null,
    [string]$PipeName = 'verge-mihomo',
    [string]$Secret = 'set-your-secret'
)

$pipe = New-Object System.IO.Pipes.NamedPipeClientStream('.', $PipeName, [System.IO.Pipes.PipeDirection]::InOut)
$pipe.Connect(3000)

$req = "$Method $ApiPath HTTP/1.1`r`nHost: localhost`r`nAuthorization: Bearer $Secret`r`nContent-Type: application/json`r`nConnection: close`r`n"
if ($Body) {
    $b = [Text.Encoding]::UTF8.GetBytes($Body)
    $req += "Content-Length: $($b.Length)`r`n`r`n$Body"
} else {
    $req += "`r`n"
}
$bytes = [Text.Encoding]::UTF8.GetBytes($req)
$pipe.Write($bytes, 0, $bytes.Length)
$pipe.Flush()

# 注意：该流不支持 ReadTimeout，不要设置。读到 0 或连接关闭即结束。
$ms = New-Object System.IO.MemoryStream
$buf = New-Object byte[] 65536
try {
    while ($true) {
        $n = $pipe.Read($buf, 0, $buf.Length)
        if ($n -le 0) { break }
        $ms.Write($buf, 0, $n)
    }
} catch { }
$pipe.Close()

$text = [Text.Encoding]::UTF8.GetString($ms.ToArray())
# 剥掉 HTTP 头
if ($text -match "`r`n`r`n") { $text = ($text -split "`r`n`r`n", 2)[1] }
# 剥掉 chunked 编码的尺寸行
$text = $text -replace "(?m)^[0-9a-fA-F]{1,6}`r?`n", ""
Write-Output $text.Trim()
