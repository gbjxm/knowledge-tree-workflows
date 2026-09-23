[CmdletBinding()]
param(
    [switch]$InstallObsidian,
    [switch]$InstallSkills,
    [string]$TargetSkillsRoot,
    [switch]$OpenVault
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$Vault = Join-Path $Root '个人影视知识树'
$env:KNOWLEDGE_TREE_CONFIG = Join-Path $Root '.codex\knowledge-tree.json'
$env:PYTHONUTF8 = '1'

function Find-Obsidian {
    $Candidates = @(
        (Join-Path (Split-Path -Parent $Root) 'Obsidian.exe'),
        $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Programs\Obsidian\Obsidian.exe' }),
        $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'Obsidian\Obsidian.exe' })
    ) | Where-Object { $_ }
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
    }
    return $null
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3 is required before the bundled validation and maintenance scripts can run.'
}

$Obsidian = Find-Obsidian
if (-not $Obsidian -and $InstallObsidian) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Start-Process 'https://obsidian.md/download'
        throw 'winget is unavailable. The official Obsidian download page was opened; install it, then run this script again.'
    }
    & winget install --id Obsidian.Obsidian -e --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Obsidian installation failed with exit code $LASTEXITCODE."
    }
    $Obsidian = Find-Obsidian
}

if ($InstallSkills) {
    $Arguments = @('-Apply')
    if ($TargetSkillsRoot) {
        $Arguments += @('-TargetSkillsRoot', $TargetSkillsRoot)
    }
    & (Join-Path $PSScriptRoot 'install-skills.ps1') @Arguments
}

& (Join-Path $PSScriptRoot 'verify.ps1')
if ($LASTEXITCODE -ne 0) {
    throw 'Portable knowledge-tree verification failed.'
}

if ($OpenVault) {
    if (-not $Obsidian) {
        throw 'Obsidian is not installed. Re-run with -InstallObsidian after user confirmation.'
    }
    Start-Process -FilePath $Obsidian
    Start-Process -FilePath 'explorer.exe' -ArgumentList "/select,`"$Vault`""
    Write-Host 'In Obsidian, choose “Open folder as vault” and select the highlighted 个人影视知识树 folder.'
}

if (-not $Obsidian) {
    Write-Host 'Obsidian is not installed. Local read-only search and audits are available now.'
    Write-Host 'After user confirmation, run: .\scripts\bootstrap-windows.ps1 -InstallObsidian -InstallSkills -OpenVault'
} else {
    Write-Host "Obsidian detected: $Obsidian"
}
