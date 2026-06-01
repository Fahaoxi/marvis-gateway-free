param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$AgentDir = "",
  [string]$InstallRoot = "",
  [string]$PythonExe = "python",
  [string]$PyInstallerExe = "D:\Program Files\Python\Python312\Scripts\pyinstaller.exe",
  [string]$CscExe = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
  [string]$BackupExeName = "MarvisAgent.real.exe",
  [string]$DistRoot = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "MarvisPaths.ps1")

if (-not $DistRoot) {
  $DistRoot = Join-Path $Workspace "captures\marvis-agent-wrapper-build"
}

$AgentDir = Resolve-MarvisAgentDir -AgentDir $AgentDir -InstallRoot $InstallRoot
$wrapperEntry = Join-Path $Workspace "src\marvis_gateway_lab\agent_wrapper_main.py"
$csharpWrapperSource = Join-Path $Workspace "scripts\MarvisAgentWrapper.cs"
$targetExe = Join-Path $AgentDir "MarvisAgent.exe"
$backupExe = Join-Path $AgentDir $BackupExeName

if (-not (Test-Path -LiteralPath $wrapperEntry)) {
  throw "Wrapper entry '$wrapperEntry' does not exist."
}
if (-not (Test-Path -LiteralPath $targetExe)) {
  throw "Official MarvisAgent '$targetExe' does not exist."
}
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
$buildRoot = Join-Path $DistRoot "pyinstaller-work"
$distDir = Join-Path $DistRoot "dist"
$specDir = Join-Path $DistRoot "spec"
$outputExe = Join-Path $distDir "MarvisAgent.exe"

Remove-Item -LiteralPath $buildRoot,$distDir,$specDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $buildRoot,$distDir,$specDir | Out-Null

if ((Test-Path -LiteralPath $CscExe) -and (Test-Path -LiteralPath $csharpWrapperSource)) {
  & $CscExe /nologo /target:winexe /optimize+ /out:$outputExe $csharpWrapperSource
}
elseif (Test-Path -LiteralPath $PyInstallerExe) {
  & $PyInstallerExe `
    --noconfirm `
    --clean `
    --onefile `
    --name MarvisAgent `
    --distpath $distDir `
    --workpath $buildRoot `
    --specpath $specDir `
    --paths (Join-Path $Workspace "src") `
    $wrapperEntry | Out-Null
}
else {
  throw "Neither C# compiler '$CscExe' nor PyInstaller '$PyInstallerExe' is available."
}

if (-not (Test-Path -LiteralPath $outputExe)) {
  throw "Built wrapper exe '$outputExe' was not created."
}

if (-not (Test-Path -LiteralPath $backupExe)) {
  Move-Item -LiteralPath $targetExe -Destination $backupExe
}
else {
  Remove-Item -LiteralPath $targetExe -Force -ErrorAction SilentlyContinue
}

Copy-Item -LiteralPath $outputExe -Destination $targetExe -Force

[PSCustomObject]@{
  active = $true
  workspace = $Workspace
  agent_dir = $AgentDir
  target_exe = $targetExe
  backup_exe = $backupExe
  built_wrapper_exe = $outputExe
}
