[CmdletBinding()]
param([string]$OutputPath, [string]$ReleaseManifest, [switch]$Preview)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$env:KNOWLEDGE_TREE_CONFIG = Join-Path $Root '.codex\knowledge-tree.json'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $Root) ("knowledge-tree-portable-{0}.zip" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$Arguments = @((Join-Path $PSScriptRoot 'release_core.py'), 'package', '--root', $Root, '--output', $OutputPath)
if ($ReleaseManifest) { $Arguments += @('--module-manifest', $ReleaseManifest) }
if ($Preview) { $Arguments += '--preview' }
& python -B -X utf8 @Arguments
if ($LASTEXITCODE -ne 0) { throw "Package operation failed (exit $LASTEXITCODE)." }
