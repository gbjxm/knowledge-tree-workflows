[CmdletBinding()]
param(
    [ValidateSet('Daily','Migration','Release','Installed')][string]$Mode = 'Daily',
    [string]$Root,
    [string]$Manifest,
    [switch]$SkipAudits,
    [string]$TargetSkillsRoot,
    [AllowEmptyCollection()][string[]]$SkillNames
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
if ($Mode -eq 'Installed') {
    try {
        if ($Manifest -or $SkipAudits) { throw 'Installed mode does not accept -Manifest or -SkipAudits.' }
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3 is required.' }
        $env:PYTHONUTF8 = '1'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        $Arguments = @((Join-Path $PSScriptRoot 'release_core.py'), 'verify-installed', '--root', $Root)
        if ($PSBoundParameters.ContainsKey('TargetSkillsRoot')) {
            if ([string]::IsNullOrWhiteSpace($TargetSkillsRoot)) { throw 'TargetSkillsRoot was supplied but is empty.' }
            $Arguments += @('--target', $TargetSkillsRoot)
        }
        if ($PSBoundParameters.ContainsKey('SkillNames')) {
            if ($null -eq $SkillNames -or $SkillNames.Count -eq 0) { throw 'SkillNames was supplied but is empty.' }
            foreach ($SkillName in $SkillNames) {
                if ([string]::IsNullOrWhiteSpace($SkillName)) { throw 'SkillNames contains an empty name.' }
            }
            $Arguments += @('--skill-names') + $SkillNames
        }
        & python -B -X utf8 @Arguments
        exit $LASTEXITCODE
    } catch {
        @{ ok = $false; mode = 'Installed'; status = 'check_failed'; writes = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress
        exit 2
    }
}
if ($PSBoundParameters.ContainsKey('TargetSkillsRoot') -or $PSBoundParameters.ContainsKey('SkillNames')) {
    throw '-TargetSkillsRoot and -SkillNames are valid only in Installed mode.'
}
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
