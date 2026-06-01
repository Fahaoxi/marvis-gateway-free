param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$CapturesRoot = "",
  [int]$TimeoutSeconds = 10,
  [switch]$StopAdapter,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Stop-OwnedProcess {
  param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [int]$TimeoutSeconds = 10,
    [switch]$Force
  )

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process) {
    return $false
  }

  if ($Force) {
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    return $true
  }

  Stop-Process -Id $ProcessId -ErrorAction Stop
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    Start-Sleep -Milliseconds 250
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
      return $true
    }
  } while ((Get-Date) -lt $deadline)

  throw "Process $ProcessId did not stop within $TimeoutSeconds seconds. Re-run with -Force."
}

if (-not $CapturesRoot) {
  $CapturesRoot = Join-Path $Workspace "captures\marvis-local-shell"
}

$shellStatusPath = Join-Path $CapturesRoot "marvis-local-shell-current.json"
if (-not (Test-Path -LiteralPath $shellStatusPath)) {
  Write-Host "No marvis local shell status file found at $shellStatusPath. Nothing to stop."
  if ($StopAdapter) {
    $adapterStopArgs = @(
      "-NoProfile",
      "-ExecutionPolicy", "Bypass",
      "-File", (Join-Path $Workspace "scripts\stop-local-model-adapter.ps1"),
      "-Workspace", $Workspace
    )
    if ($Force) {
      $adapterStopArgs += "-Force"
    }
    & powershell @adapterStopArgs
  }
  return
}

$shellStatus = Get-Content -LiteralPath $shellStatusPath -Raw | ConvertFrom-Json -ErrorAction Stop
$agentPid = [int]$shellStatus.agent_pid

try {
  $mcpChildren = @(
    Get-CimInstance Win32_Process -Filter "Name = 'MarvisMCP.exe'" -ErrorAction Stop |
      Where-Object { $_.ParentProcessId -eq $agentPid }
  )
  foreach ($child in $mcpChildren) {
    Stop-OwnedProcess -ProcessId ([int]$child.ProcessId) -TimeoutSeconds $TimeoutSeconds -Force:$Force | Out-Null
  }
}
catch {
  # If child enumeration is denied, still stop the launcher-owned Agent PID.
}

Stop-OwnedProcess -ProcessId $agentPid -TimeoutSeconds $TimeoutSeconds -Force:$Force | Out-Null

$shellStatus | Add-Member -NotePropertyName "active" -NotePropertyValue $false -Force
$shellStatus | Add-Member -NotePropertyName "stopped_at" -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
$shellStatus | ConvertTo-Json | Set-Content -LiteralPath $shellStatusPath -Encoding UTF8

if ($StopAdapter) {
  $adapterStopArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $Workspace "scripts\stop-local-model-adapter.ps1"),
    "-Workspace", $Workspace
  )
  if ($Force) {
    $adapterStopArgs += "-Force"
  }
  & powershell @adapterStopArgs
}

Write-Host "Stopped marvis local shell Agent process $agentPid."
