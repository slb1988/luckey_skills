[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string]$InputPath,

    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

$inputItem = Get-Item -LiteralPath $InputPath
if ($inputItem.Extension -notin @('.mmd', '.mermaid')) {
    throw "Expected a .mmd or .mermaid input file: $($inputItem.FullName)"
}

$source = Get-Content -Raw -LiteralPath $inputItem.FullName
if ($source -match '^\s*```') {
    throw 'Standalone Mermaid files must contain raw syntax without Markdown code fences.'
}

$temporaryOutput = $false
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path ([IO.Path]::GetTempPath()) "mermaid-validate-$([guid]::NewGuid().ToString('N')).svg"
    $temporaryOutput = $true
}

$outputFullPath = [IO.Path]::GetFullPath($OutputPath)
$outputExtension = [IO.Path]::GetExtension($outputFullPath)
if ($outputExtension -notin @('.svg', '.png', '.pdf')) {
    throw "Output must use .svg, .png, or .pdf: $outputFullPath"
}

$outputDirectory = Split-Path -Parent $outputFullPath
if ($outputDirectory -and -not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$mmdc = Get-Command mmdc -ErrorAction SilentlyContinue
$npx = Get-Command npx -ErrorAction SilentlyContinue

try {
    if ($mmdc) {
        & $mmdc.Source -i $inputItem.FullName -o $outputFullPath -q
    }
    elseif ($npx) {
        & $npx.Source -y -p '@mermaid-js/mermaid-cli' mmdc -i $inputItem.FullName -o $outputFullPath -q
    }
    else {
        throw 'Neither mmdc nor npx is available. Run Install-MermaidTooling.ps1 first.'
    }

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputFullPath)) {
        throw "Mermaid validation failed for $($inputItem.FullName)"
    }

    if ($temporaryOutput) {
        Write-Output "Valid Mermaid: $($inputItem.FullName)"
    }
    else {
        Write-Output "Rendered Mermaid: $outputFullPath"
    }
}
finally {
    if ($temporaryOutput -and (Test-Path -LiteralPath $outputFullPath)) {
        Remove-Item -LiteralPath $outputFullPath -Force
    }
}
