[CmdletBinding()]
param(
    [switch]$SkipDesktop,
    [switch]$SkipCli,
    [switch]$ConfigureMcp,
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
$mcpName = 'mermaid-code-mcp'
$mcpUrl = 'http://127.0.0.1:37079/mcp'
$installedExecutable = $null

function Find-MermaidCodeExecutable {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Mermaid Code\mermaid-code.exe'),
        (Join-Path $env:LOCALAPPDATA 'Mermaid Code\Mermaid Code.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Mermaid Code\mermaid-code.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Mermaid Code\Mermaid Code.exe'),
        (Join-Path $env:ProgramFiles 'Mermaid Code\mermaid-code.exe'),
        (Join-Path $env:ProgramFiles 'Mermaid Code\Mermaid Code.exe')
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    $uninstallRoots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $entry = Get-ItemProperty $uninstallRoots -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq 'Mermaid Code' } |
        Select-Object -First 1
    if ($entry -and $entry.InstallLocation) {
        $installLocation = ([string]$entry.InstallLocation).Trim().Trim('"')
        foreach ($executableName in @('mermaid-code.exe', 'Mermaid Code.exe')) {
            $candidate = Join-Path $installLocation $executableName
            if (Test-Path -LiteralPath $candidate) {
                return (Get-Item -LiteralPath $candidate).FullName
            }
        }
    }

    return $null
}

if (-not $SkipDesktop) {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Automatic Mermaid Code installation currently supports Windows only.'
    }

    $installedExecutable = Find-MermaidCodeExecutable
    if (-not $installedExecutable) {
        $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/m8524769/mermaid-code/releases/latest' -Headers @{ 'User-Agent' = 'mermaid-diagrams-skill' }
        $asset = $release.assets |
            Where-Object { $_.name -match '_x64_en-US\.msi$' } |
            Select-Object -First 1
        if (-not $asset) {
            throw 'The latest Mermaid Code release does not include a Windows x64 MSI.'
        }

        $downloadDirectory = Join-Path ([IO.Path]::GetTempPath()) "mermaid-code-install-$([guid]::NewGuid().ToString('N'))"
        New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
        $installerPath = Join-Path $downloadDirectory $asset.name

        try {
            Write-Output "Downloading Mermaid Code $($release.tag_name)..."
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installerPath
            $hash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash
            Write-Output "Installer SHA256: $hash"

            $process = Start-Process msiexec.exe -ArgumentList @('/i', "`"$installerPath`"", '/qn', '/norestart') -Wait -PassThru
            if ($process.ExitCode -notin @(0, 3010)) {
                throw "Mermaid Code installer exited with code $($process.ExitCode)."
            }
        }
        finally {
            $resolvedDownloadDirectory = [IO.Path]::GetFullPath($downloadDirectory)
            $resolvedTempDirectory = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
            if ($resolvedDownloadDirectory.StartsWith($resolvedTempDirectory, [StringComparison]::OrdinalIgnoreCase) -and
                (Test-Path -LiteralPath $resolvedDownloadDirectory)) {
                Remove-Item -LiteralPath $resolvedDownloadDirectory -Recurse -Force
            }
        }

        $installedExecutable = Find-MermaidCodeExecutable
        if (-not $installedExecutable) {
            throw 'Mermaid Code installation completed, but the executable could not be located.'
        }
    }

    $desktopVersion = (Get-Item -LiteralPath $installedExecutable).VersionInfo.ProductVersion
    Write-Output "Mermaid Code: $desktopVersion ($installedExecutable)"
}

if (-not $SkipCli) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw 'npm is required to install the official Mermaid CLI.'
    }

    & $npm.Source install --global '@mermaid-js/mermaid-cli'
    if ($LASTEXITCODE -ne 0) {
        throw 'Mermaid CLI installation failed.'
    }

    $mmdc = Get-Command mmdc -ErrorAction Stop
    $cliVersion = & $mmdc.Source --version
    Write-Output "Mermaid CLI: $cliVersion"
}

if ($ConfigureMcp) {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if ($codex) {
        & $codex.Source mcp get $mcpName *> $null
        if ($LASTEXITCODE -ne 0) {
            & $codex.Source mcp add $mcpName --url $mcpUrl
            if ($LASTEXITCODE -ne 0) {
                throw 'Could not configure Mermaid Code MCP for Codex.'
            }
        }
        Write-Output "Codex MCP configured: $mcpName"
    }

    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if ($claude) {
        & $claude.Source mcp get $mcpName *> $null
        if ($LASTEXITCODE -ne 0) {
            & $claude.Source mcp add --scope user --transport http $mcpName $mcpUrl
            if ($LASTEXITCODE -ne 0) {
                throw 'Could not configure Mermaid Code MCP for Claude Code.'
            }
        }
        Write-Output "Claude Code MCP configured: $mcpName"
    }
}

if ($Launch) {
    if (-not $installedExecutable) {
        $installedExecutable = Find-MermaidCodeExecutable
    }
    if (-not $installedExecutable) {
        throw 'Mermaid Code is not installed or could not be located.'
    }

    Start-Process -FilePath $installedExecutable
    Write-Output 'Mermaid Code launched. Enable MCP Server once from the top-left menu.'
}
