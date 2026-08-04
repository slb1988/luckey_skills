param(
    [string]$RepoRoot = "",
    [string]$Query = "",
    [int]$Limit = 40
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
}

if (-not $RepoRoot) {
    throw "Cannot locate the repository root. Pass -RepoRoot explicitly."
}

$repo = (Resolve-Path -LiteralPath $RepoRoot).Path
$vault = Join-Path $repo "luckey"
$routing = Join-Path $vault "00_meta/rules/routing-rules.md"
$metadata = Join-Path $vault "00_meta/rules/metadata-schema.md"

if (-not (Test-Path -LiteralPath $routing) -or -not (Test-Path -LiteralPath $metadata)) {
    throw "This does not look like the Luckey vault: current rule files are missing."
}

function Get-MarkdownCount([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return @(Get-ChildItem -LiteralPath $Path -Recurse -File -Filter "*.md" -ErrorAction SilentlyContinue).Count
}

Write-Output "# Luckey Vault Context"
Write-Output ""
Write-Output "Repository: ``$repo``"
Write-Output ""
Write-Output "## Authoritative rules"
Write-Output ""
Write-Output "- ``luckey/00_meta/rules/routing-rules.md``"
Write-Output "- ``luckey/00_meta/rules/metadata-schema.md``"
Write-Output ""
Write-Output "## Top-level areas"
Write-Output ""
Write-Output "| Area | Markdown files |"
Write-Output "|---|---:|"

Get-ChildItem -LiteralPath $vault -Directory |
    Where-Object { $_.Name -ne ".obsidian" } |
    Sort-Object Name |
    ForEach-Object {
        $count = Get-MarkdownCount $_.FullName
        Write-Output "| ``$($_.Name)`` | $count |"
    }

foreach ($group in @(
    @{ Title = "Reusable note domains"; Path = "02_notes" },
    @{ Title = "Projects"; Path = "03_projects" }
)) {
    $path = Join-Path $vault $group.Path
    Write-Output ""
    Write-Output "## $($group.Title)"
    Write-Output ""
    if (Test-Path -LiteralPath $path) {
        Get-ChildItem -LiteralPath $path -Directory |
            Sort-Object Name |
            ForEach-Object {
                $count = Get-MarkdownCount $_.FullName
                Write-Output "- ``$($_.Name)`` ($count Markdown files)"
            }
    }
}

$capture = Join-Path $vault "01_inbox/capture"
Write-Output ""
Write-Output "## Pending capture"
Write-Output ""
if (Test-Path -LiteralPath $capture) {
    $pending = @(Get-ChildItem -LiteralPath $capture -File | Sort-Object Name)
    Write-Output "Count: $($pending.Count)"
    $pending | Select-Object -First $Limit | ForEach-Object { Write-Output "- ``$($_.Name)``" }
} else {
    Write-Output "No ``01_inbox/capture`` directory found."
}

if ($Query) {
    Write-Output ""
    Write-Output "## Files matching query"
    Write-Output ""
    $rg = Get-Command rg -ErrorAction SilentlyContinue
    if ($rg) {
        $matches = @(& $rg.Source -l -i --glob "*.md" -- $Query $vault 2>$null | Select-Object -First $Limit)
    } else {
        $matches = @(Get-ChildItem -LiteralPath $vault -Recurse -File -Filter "*.md" |
            Select-String -SimpleMatch -Pattern $Query -List |
            Select-Object -First $Limit -ExpandProperty Path)
    }

    if ($matches.Count -eq 0) {
        Write-Output "No matching Markdown files."
    } else {
        foreach ($match in $matches) {
            $resolved = (Resolve-Path -LiteralPath $match).Path
            $relative = $resolved.Substring($vault.Length + 1).Replace("\", "/")
            Write-Output "- ``$relative``"
        }
    }
}
