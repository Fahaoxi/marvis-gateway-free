param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [switch]$StopAdapter,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Stop-ByName {
  param([string[]]$Names)
  foreach ($name in $Names) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
      Stop-Process -Id $_.Id -Force:$Force -ErrorAction SilentlyContinue
    }
  }
}

Stop-ByName -Names @("Marvis", "MarvisHost", "MarvisAgent", "MarvisAgent.real", "MarvisMCP")

if ($StopAdapter) {
  $adapterStopScript = Join-Path $Workspace "scripts\stop-local-model-adapter.ps1"
  $adapterStopArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $adapterStopScript,
    "-Workspace", $Workspace
  )
  if ($Force) {
    $adapterStopArgs += "-Force"
  }
  & powershell @adapterStopArgs
}

$statusPath = Join-Path $Workspace "captures\marvis-wrapper-shell\runtime-status.json"
if (Test-Path -LiteralPath $statusPath) {
  $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
  if ($status) {
    $status | Add-Member -NotePropertyName "active" -NotePropertyValue $false -Force
    $status | Add-Member -NotePropertyName "stopped_at" -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8
  }
}

Write-Host "Stopped Marvis wrapper shell processes."
Write-Host "This stop command does not restore the wrapper. Run scripts\restore-marvis-agent-wrapper.ps1 if you want the official MarvisAgent.exe restored."
