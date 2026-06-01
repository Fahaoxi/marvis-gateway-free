param(
  [string]$AgentDir = "",
  [string]$InstallRoot = "",
  [string]$BackupExeName = "MarvisAgent.real.exe"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "MarvisPaths.ps1")

$AgentDir = Resolve-MarvisAgentDir -AgentDir $AgentDir -InstallRoot $InstallRoot
$targetExe = Join-Path $AgentDir "MarvisAgent.exe"
$backupExe = Join-Path $AgentDir $BackupExeName

if (-not (Test-Path -LiteralPath $backupExe)) {
  throw "Backup exe '$backupExe' does not exist."
}

Remove-Item -LiteralPath $targetExe -Force -ErrorAction SilentlyContinue
Move-Item -LiteralPath $backupExe -Destination $targetExe

[PSCustomObject]@{
  active = $false
  agent_dir = $AgentDir
  restored_exe = $targetExe
}
