[CmdletBinding()]
param([string]$TargetSkillsRoot, [AllowEmptyCollection()][string[]]$SkillNames, [switch]$Apply)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$env:KNOWLEDGE_TREE_CONFIG = Join-Path $Root '.codex\knowledge-tree.json'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
if ($PSBoundParameters.ContainsKey('SkillNames')) {
    if ($null -eq $SkillNames -or $SkillNames.Count -eq 0) { throw 'SkillNames was supplied but is empty.' }
    foreach ($SkillName in $SkillNames) {
        if ([string]::IsNullOrWhiteSpace($SkillName)) { throw 'SkillNames contains an empty name.' }
    }
}
if (-not $TargetSkillsRoot) {
    if ($env:CODEX_HOME) {
        $TargetSkillsRoot = Join-Path $env:CODEX_HOME 'skills'
    } elseif ($env:USERPROFILE -and (Test-Path -LiteralPath (Join-Path $env:USERPROFILE '.codex'))) {
        $TargetSkillsRoot = Join-Path $env:USERPROFILE '.codex\skills'
    } else { throw 'Pass -TargetSkillsRoot explicitly; no Codex Skills root was found.' }
}
$Arguments = @((Join-Path $PSScriptRoot 'release_core.py'), 'install', '--root', $Root, '--target', $TargetSkillsRoot)
if ($PSBoundParameters.ContainsKey('SkillNames')) { $Arguments += @('--skill-names') + $SkillNames }
if ($Apply) { $Arguments += '--apply' }
& python -B -X utf8 @Arguments
if ($LASTEXITCODE -ne 0) { throw "Skill selection or installation failed (exit $LASTEXITCODE)." }
