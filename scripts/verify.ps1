[CmdletBinding()]
param(
    [ValidateSet('Daily','Migration','Release')][string]$Mode = 'Daily',
    [string]$Root,
    [string]$Manifest,
    [switch]$SkipAudits
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
$Root = (Resolve-Path -LiteralPath $Root).Path
$env:KNOWLEDGE_TREE_CONFIG = Join-Path $Root '.codex\knowledge-tree.json'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
if ($SkipAudits -and $Mode -ne 'Daily') { throw '-SkipAudits is valid only in Daily mode.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3 is required.' }
if ($Mode -eq 'Daily') {
    if ($Manifest) { throw '-Manifest is not used in Daily mode.' }
    $Arguments = @((Join-Path $PSScriptRoot 'release_core.py'), 'daily', '--root', $Root)
    if ($SkipAudits) { $Arguments += '--skip-audits' }
} elseif ($Mode -eq 'Migration') {
    if (-not $Manifest) { $Manifest = Join-Path $Root 'manifest\vault-before-migration.json' }
    $Arguments = @((Join-Path $PSScriptRoot 'release_core.py'), 'migration', '--root', $Root, '--manifest', $Manifest)
} else {
    if (-not $Manifest) { throw 'Release mode requires -Manifest for this exact release.' }
    $Arguments = @((Join-Path $PSScriptRoot 'release_core.py'), 'verify-release', '--root', $Root, '--manifest', $Manifest)
}
& python -B -X utf8 @Arguments
if ($LASTEXITCODE -ne 0) { throw "$Mode verification failed (exit $LASTEXITCODE)." }
