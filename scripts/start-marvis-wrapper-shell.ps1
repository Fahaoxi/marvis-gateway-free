param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$MarvisExe = "",
  [string]$AgentDir = "",
  [string]$InstallRoot = "",
  [int]$AdapterPort = 19080,
  [int]$AgentPort = 6161,
  [switch]$SkipWrapperInstall,
  [switch]$RunCanary
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "MarvisPaths.ps1")

function Wait-HttpOk {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 20
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2
      if ($response) {
        return $true
      }
    }
    catch {
      # Not ready yet.
    }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)

  return $false
}

function Test-ListeningPort {
  param(
    [Parameter(Mandatory = $true)]
    [int]$Port
  )

  try {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1)
  }
  catch {
    foreach ($line in (netstat -ano -p tcp | Select-String "LISTENING")) {
      $parts = ($line.Line -replace "^\s+", "") -split "\s+"
      if ($parts.Count -ge 5 -and $parts[1].EndsWith(":$Port")) {
        return $true
      }
    }
  }
  return $false
}

$scriptsDir = Join-Path $Workspace "scripts"
$installWrapperScript = Join-Path $scriptsDir "install-marvis-agent-wrapper.ps1"
$startAdapterScript = Join-Path $scriptsDir "start-local-model-adapter.ps1"
$adapterStatusScript = Join-Path $scriptsDir "get-local-model-adapter-status.ps1"
$canaryScript = Join-Path $scriptsDir "test-marvis-third-party-canary.js"
$statusRoot = Join-Path $Workspace "captures\marvis-wrapper-shell"
$statusPath = Join-Path $statusRoot "runtime-status.json"
$adapterStatusPath = Join-Path $Workspace "captures\local-model-adapter\runtime-status.json"
$canaryExpectedResponse = [string]::Concat([char]0x6210, [char]0x529F)

New-Item -ItemType Directory -Force -Path $statusRoot | Out-Null

$MarvisExe = Resolve-MarvisApplicationExe -MarvisExe $MarvisExe -InstallRoot $InstallRoot
$AgentDir = Resolve-MarvisAgentDir -AgentDir $AgentDir -InstallRoot $InstallRoot
if (-not (Test-Path -LiteralPath $MarvisExe)) {
  throw "MarvisExe '$MarvisExe' does not exist."
}

if (-not $SkipWrapperInstall) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $installWrapperScript -Workspace $Workspace -AgentDir $AgentDir | Out-Null
}

if (Test-Path -LiteralPath $adapterStatusScript) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $adapterStatusScript -Workspace $Workspace | Out-Null
}

$adapterActive = $false
if (Test-Path -LiteralPath $adapterStatusPath) {
  $adapterStatus = Get-Content -LiteralPath $adapterStatusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
  $adapterActive = [bool]($adapterStatus -and $adapterStatus.active -and $adapterStatus.listen_port -eq $AdapterPort -and (Test-ListeningPort -Port $AdapterPort))
}

if (-not $adapterActive) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $startAdapterScript `
    -Workspace $Workspace `
    -ListenPort $AdapterPort | Out-Null
}

if (-not (Wait-HttpOk -Url "http://127.0.0.1:$AdapterPort/health" -TimeoutSeconds 20)) {
  throw "Local OpenAI adapter did not become healthy on 127.0.0.1:$AdapterPort."
}

$marvisProcess = Get-Process -Name "Marvis" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $marvisProcess) {
  $marvisProcess = Start-Process `
    -FilePath $MarvisExe `
    -WorkingDirectory (Split-Path -Parent $MarvisExe) `
    -PassThru
}

if (-not (Wait-HttpOk -Url "http://127.0.0.1:$AgentPort/health" -TimeoutSeconds 45)) {
  throw "Marvis Agent did not become healthy on 127.0.0.1:$AgentPort."
}

$canaryResult = $null
if ($RunCanary) {
  $canaryOutput = & node $canaryScript --port $AgentPort
  $canaryResult = $canaryOutput -join "`n"
}

$status = [ordered]@{
  active = $true
  mode = "marvis-wrapper-shell"
  workspace = $Workspace
  marvis_pid = $marvisProcess.Id
  marvis_exe = $MarvisExe
  agent_dir = $AgentDir
  adapter_port = $AdapterPort
  agent_port = $AgentPort
  canary_prompt = "MARVIS_THIRD_PARTY_PING"
  canary_expected_response = $canaryExpectedResponse
  canary_result = $canaryResult
  started_at = (Get-Date).ToUniversalTime().ToString("o")
}
$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8

[PSCustomObject]$status
