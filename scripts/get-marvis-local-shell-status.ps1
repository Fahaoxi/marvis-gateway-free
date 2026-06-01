param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$CapturesRoot = ""
)

$ErrorActionPreference = "Stop"

function Test-HttpHealth {
  param([string]$Url)
  try {
    $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2
    return [bool]$response
  }
  catch {
    return $false
  }
}

if (-not $CapturesRoot) {
  $CapturesRoot = Join-Path $Workspace "captures\marvis-local-shell"
}

$shellStatusPath = Join-Path $CapturesRoot "marvis-local-shell-current.json"
$adapterStatusPath = Join-Path $Workspace "captures\local-model-adapter\runtime-status.json"

$shellStatus = $null
if (Test-Path -LiteralPath $shellStatusPath) {
  $shellStatus = Get-Content -LiteralPath $shellStatusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
}

$adapterStatus = $null
if (Test-Path -LiteralPath $adapterStatusPath) {
  $adapterStatus = Get-Content -LiteralPath $adapterStatusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
}

$agentPid = $null
$agentActive = $false
$agentHealth = $false
$mcpProcesses = @()

if ($shellStatus -and $shellStatus.agent_pid) {
  $agentPid = [int]$shellStatus.agent_pid
  $agentProcess = Get-Process -Id $agentPid -ErrorAction SilentlyContinue
  $agentActive = [bool]$agentProcess
  if ($shellStatus.agent_health_url) {
    $agentHealth = Test-HttpHealth -Url ([string]$shellStatus.agent_health_url)
  }

  try {
    $mcpProcesses = @(
      Get-CimInstance Win32_Process -Filter "Name = 'MarvisMCP.exe'" -ErrorAction Stop |
        Where-Object { $_.ParentProcessId -eq $agentPid } |
        Select-Object ProcessId, ParentProcessId, ExecutablePath
    )
  }
  catch {
    $mcpProcesses = @()
  }
}

$status = [ordered]@{
  active = [bool]($shellStatus -and $shellStatus.active -and $agentActive -and $agentHealth)
  mode = "marvis-local-shell"
  workspace = $Workspace
  captures_root = $CapturesRoot
  shell_status_path = $shellStatusPath
  shell = $shellStatus
  adapter = $adapterStatus
  agent_pid = $agentPid
  agent_active = $agentActive
  agent_health = $agentHealth
  marvis_mcp = $mcpProcesses
  updated_at = (Get-Date).ToUniversalTime().ToString("o")
}

$status | ConvertTo-Json -Depth 8
