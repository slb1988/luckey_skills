<#
.SYNOPSIS
  Extract the UE commandlet command line from a TeamCity build log.

.DESCRIPTION
  Given a TeamCity build URL (or buildId), downloads the build log via REST API
  (Bearer token in $env:TC_AGENT_MONITOR_TOKEN) and extracts the
  "UnrealEditor.exe ... -run=...Commandlet ... -builder=..." invocation.

  Emits:
    - RawCommand:  the exact line from the log
    - VsArgs:      VS Debugging "Command Arguments" form (everything after .uproject),
                   with the uproject path rewritten to -LocalRoot when supplied.

.PARAMETER Url
  TeamCity build URL, e.g.
  http://192.168.2.13:8111/buildConfiguration/PL_WpBuildMinimap/7945?buildTab=log

.PARAMETER BuildId
  Numeric build id (alternative to -Url).

.PARAMETER LocalRoot
  Optional workspace root to rewrite the uproject path onto,
  e.g. C:\WinBuilder3_MainDev_Sandbox  ->  uproject becomes
  C:\WinBuilder3_MainDev_Sandbox/Main/ProjectLungfish.uproject

.PARAMETER TcBase
  TeamCity base URL. Default http://192.168.2.13:8111
#>
param(
  [string]$Url,
  [int]$BuildId,
  [string]$LocalRoot,
  [string]$TcBase = "http://192.168.2.13:8111"
)

$ErrorActionPreference = "Stop"

if (-not $env:TC_AGENT_MONITOR_TOKEN) {
  throw "TC_AGENT_MONITOR_TOKEN not set. Store it via secrets, it is auto-injected in exec_command."
}

# --- Resolve buildId from URL if needed ---
if (-not $BuildId -and $Url) {
  # URLs look like /buildConfiguration/<CFG>/<BUILDID>?...  or  ?buildId=<ID>
  if ($Url -match "[?&]buildId=(\d+)") { $BuildId = [int]$Matches[1] }
  elseif ($Url -match "/(?:viewLog\.html.*?buildId=)?(\d{3,})(?:[?&/]|$)") { $BuildId = [int]$Matches[1] }
  elseif ($Url -match "/(\d{3,})(?:\?|$)") { $BuildId = [int]$Matches[1] }
}
if (-not $BuildId) { throw "Could not determine BuildId from input. Pass -BuildId or a URL containing it." }

$headers = @{ Authorization = "Bearer $env:TC_AGENT_MONITOR_TOKEN" }

# --- Build metadata (for context + sanity) ---
$meta = Invoke-RestMethod -Uri "$TcBase/app/rest/builds/id:$BuildId" -Headers (@{Authorization=$headers.Authorization; Accept="application/json"})
$cfg    = $meta.buildTypeId
$number = $meta.number
$agent  = $meta.agent.name

# --- Download log ---
$tmp = Join-Path $env:TEMP "tc_$BuildId.log"
Invoke-WebRequest -Uri "$TcBase/downloadBuildLog.html?buildId=$BuildId" -Headers $headers -OutFile $tmp | Out-Null

# --- Extract the commandlet invocation ---
# Match the echoed full command line containing UnrealEditor.exe + -run=...Commandlet
$pattern = 'UnrealEditor(?:-Cmd)?\.exe\s+.*?-run=\w+Commandlet.*?(?=$)'
$line = (Select-String -Path $tmp -Pattern $pattern -AllMatches |
         Select-Object -First 1).Matches.Value

if (-not $line) {
  # Fallback: any line mentioning a *Builder commandlet
  $hit = Select-String -Path $tmp -Pattern 'UnrealEditor.*-run=.*Commandlet' | Select-Object -First 1
  if ($hit) { $line = $hit.Line }
}
if (-not $line) { throw "No UE commandlet invocation found in log for build $BuildId." }

$raw = $line.Trim()

# Split exe vs args: everything from the first .uproject onward are the args
$argsPart = $null
if ($raw -match '(?<exe>.*?UnrealEditor(?:-Cmd)?\.exe)\s+(?<rest>.*)$') {
  $rest = $Matches['rest']
} else { $rest = $raw }

# rest = "<uproject> <map> -run=... -builder=..."
# VS Command Arguments = everything after the exe (i.e. $rest), with uproject path localized
$vsArgs = $rest
if ($LocalRoot) {
  $root = $LocalRoot.TrimEnd('\','/')
  # Replace the leading uproject token (up to first whitespace) with localized path.
  if ($rest -match '^(?<uproj>\S+\.uproject)(?<tail>\s.*)$') {
    $projLeaf = Split-Path -Leaf $Matches['uproj']           # ProjectLungfish.uproject
    $vsArgs = "$root/Main/$projLeaf" + $Matches['tail']
  }
}

[pscustomobject]@{
  BuildId    = $BuildId
  Config     = $cfg
  Number     = $number
  Agent      = $agent
  RawCommand = $raw
  VsArgs     = $vsArgs
} | Format-List

Write-Output ""
Write-Output "=== COPY: VS Command Arguments ==="
Write-Output $vsArgs
