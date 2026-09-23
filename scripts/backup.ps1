[CmdletBinding(DefaultParameterSetName = 'Preview')]
param(
    [Parameter(ParameterSetName = 'Preview')][switch]$Preview,
    [Parameter(Mandatory = $true, ParameterSetName = 'Apply')][switch]$Apply,
    [Parameter(Mandatory = $true, ParameterSetName = 'Restore')][switch]$RestoreTest,
    [Parameter(Mandatory = $true, ParameterSetName = 'Restore')][string]$Commit
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$Arguments = @('-B', '-X', 'utf8', (Join-Path $PSScriptRoot 'github_backup.py'), '--root', $Root)
if ($Apply) { $Arguments += '--apply' }
elseif ($RestoreTest) { $Arguments += @('--restore-test', '--commit', $Commit) }
else { $Arguments += '--preview' }
& python @Arguments
if ($LASTEXITCODE -ne 0) { throw "Backup did not complete (exit $LASTEXITCODE). See the reported phase and receipt." }
