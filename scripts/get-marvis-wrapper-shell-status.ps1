param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$AgentDir = "",
  [string]$InstallRoot = "",
  [int]$AdapterPort = 19080,
  [int]$AgentPort = 6161
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "MarvisPaths.ps1")

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

function Get-PortOwner {
  param([int]$Port)
  try {
    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    if ($connection) {
      return [int]$connection.OwningProcess
    }
  }
  catch {
    return $null
  }
  return $null
}

$agentDir = Resolve-MarvisAgentDir -AgentDir $AgentDir -InstallRoot $InstallRoot
$wrapperExe = Join-Path $agentDir "MarvisAgent.exe"
$realExe = Join-Path $agentDir "MarvisAgent.real.exe"
$wrapperLog = Join-Path $agentDir "MarvisAgent.wrapper.log"
$statusPath = Join-Path $Workspace "captures\marvis-wrapper-shell\runtime-status.json"
$adapterStatusPath = Join-Path $Workspace "captures\local-model-adapter\runtime-status.json"
$canaryExpectedResponse = [string]::Concat([char]0x6210, [char]0x529F)

$statusRecord = $null
if (Test-Path -LiteralPath $statusPath) {
  $statusRecord = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
}

$adapterRecord = $null
if (Test-Path -LiteralPath $adapterStatusPath) {
  $adapterRecord = Get-Content -LiteralPath $adapterStatusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
}

$wrapperLogTail = @()
if (Test-Path -LiteralPath $wrapperLog) {
  $wrapperLogTail = @(Get-Content -LiteralPath $wrapperLog -Tail 5 | ForEach-Object { [string]$_ })
}

$status = [ordered]@{
  active = (Test-HttpHealth -Url "http://127.0.0.1:$AgentPort/health") -and (Test-HttpHealth -Url "http://127.0.0.1:$AdapterPort/health")
  mode = "marvis-wrapper-shell"
  workspace = $Workspace
  wrapper_installed = (Test-Path -LiteralPath $wrapperExe) -and (Test-Path -LiteralPath $realExe)
  wrapper_exe = $wrapperExe
  real_exe = $realExe
  wrapper_log_tail = $wrapperLogTail
  adapter = $adapterRecord
  status = $statusRecord
  adapter_port = $AdapterPort
  adapter_owner_pid = Get-PortOwner -Port $AdapterPort
  agent_port = $AgentPort
  agent_owner_pid = Get-PortOwner -Port $AgentPort
  canary_prompt = "MARVIS_THIRD_PARTY_PING"
  canary_expected_response = $canaryExpectedResponse
  updated_at = (Get-Date).ToUniversalTime().ToString("o")
}

$status | ConvertTo-Json -Depth 8
