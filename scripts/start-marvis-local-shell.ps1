param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [int]$AdapterPort = 19080,
  [int]$AgentPort = 6161,
  [string]$ListenHost = "127.0.0.1",
  [string]$Config = "",
  [string]$CapturesRoot = "",
  [string]$PythonExe = "",
  [string]$MarvisAgentPath = "D:\Program Files\Tencent\Marvis\MarvisAgent\1.0.1100.151\MarvisAgent.exe",
  [string]$UserId = "probe_user_19080"
)

$ErrorActionPreference = "Stop"

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

function Wait-ListeningPort {
  param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,
    [Parameter(Mandatory = $true)]
    [int]$Port,
    [int]$TimeoutSeconds = 10
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
      $connect = $client.BeginConnect($HostName, $Port, $null, $null)
      if ($connect.AsyncWaitHandle.WaitOne(250, $false)) {
        $client.EndConnect($connect)
        return $true
      }
    }
    catch {
      # Not listening yet.
    }
    finally {
      $client.Close()
    }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)

  return $false
}

function Test-ProcessOwnsTcpListenPort {
  param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
    [int]$Port
  )

  try {
    $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
    return [bool]($connections | Where-Object { $_.OwningProcess -eq $ProcessId } | Select-Object -First 1)
  }
  catch {
    foreach ($line in (netstat -ano -p tcp | Select-String "LISTENING")) {
      $parts = ($line.Line -replace "^\s+", "") -split "\s+"
      if ($parts.Count -lt 5) {
        continue
      }
      $lastColon = $parts[1].LastIndexOf(":")
      if ($lastColon -lt 0) {
        continue
      }
      $localPort = [int]$parts[1].Substring($lastColon + 1)
      $ownerProcessId = [int]$parts[4]
      if ($localPort -eq $Port -and $ownerProcessId -eq $ProcessId) {
        return $true
      }
    }
  }
  return $false
}

function Get-ActiveAdapterStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$StatusPath,
    [Parameter(Mandatory = $true)]
    [int]$ExpectedPort
  )

  if (-not (Test-Path -LiteralPath $StatusPath)) {
    return $null
  }

  $status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
  if (-not $status -or -not $status.active -or -not $status.pid) {
    return $null
  }

  $adapterPid = [int]$status.pid
  $adapterPort = [int]$status.listen_port
  if ($adapterPort -ne $ExpectedPort) {
    return $null
  }

  $process = Get-Process -Id $adapterPid -ErrorAction SilentlyContinue
  if ($process -and (Test-ProcessOwnsTcpListenPort -ProcessId $adapterPid -Port $ExpectedPort)) {
    return $status
  }

  return $null
}

if (-not $Config) {
  $Config = Join-Path $Workspace "config\third-party-api.local.toml"
}
if (-not $CapturesRoot) {
  $CapturesRoot = Join-Path $Workspace "captures\marvis-local-shell"
}

if (-not (Test-Path -LiteralPath $MarvisAgentPath)) {
  throw "MarvisAgentPath '$MarvisAgentPath' does not exist."
}
if (-not (Test-Path -LiteralPath $Config)) {
  throw "Config '$Config' does not exist. Create it from config\third-party-api.example.toml."
}

$scriptsDir = Join-Path $Workspace "scripts"
$adapterStartScript = Join-Path $scriptsDir "start-local-model-adapter.ps1"
$adapterStatusScript = Join-Path $scriptsDir "get-local-model-adapter-status.ps1"
$adapterStatusPath = Join-Path $Workspace "captures\local-model-adapter\runtime-status.json"

New-Item -ItemType Directory -Force -Path $CapturesRoot | Out-Null
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $CapturesRoot "run-$runStamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$currentStatusPath = Join-Path $CapturesRoot "marvis-local-shell-current.json"
$agentPortFile = Join-Path $runDir "agent_port.ini"
$kbPortFile = Join-Path $runDir "knowledgebase_port.ini"
$agentLogDir = Join-Path $runDir "logs"
$agentHomeDir = Join-Path $runDir "home"
$agentLockFile = Join-Path $runDir "agent.lock"
$agentStdout = Join-Path $runDir "agent-local-out.log"
$agentStderr = Join-Path $runDir "agent-local-err.log"

New-Item -ItemType Directory -Force -Path $agentLogDir, $agentHomeDir | Out-Null
New-Item -ItemType File -Force -Path $agentLockFile | Out-Null

if (Test-Path -LiteralPath $adapterStatusScript) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $adapterStatusScript `
    -Workspace $Workspace `
    -PythonExe $PythonExe | Out-Null
}

$adapterStatus = Get-ActiveAdapterStatus -StatusPath $adapterStatusPath -ExpectedPort $AdapterPort
if (-not $adapterStatus) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $adapterStartScript `
    -Workspace $Workspace `
    -Config $Config `
    -PythonExe $PythonExe `
    -ListenHost $ListenHost `
    -ListenPort $AdapterPort | Out-Null
  $adapterStatus = Get-ActiveAdapterStatus -StatusPath $adapterStatusPath -ExpectedPort $AdapterPort
  if (-not $adapterStatus) {
    throw "Local model adapter did not become active on $ListenHost`:$AdapterPort."
  }
}

if (Wait-ListeningPort -HostName $ListenHost -Port $AgentPort -TimeoutSeconds 1) {
  throw "$ListenHost`:$AgentPort is already accepting TCP connections. Stop or move the existing Agent listener before starting this launcher."
}

$arguments = @(
  "--port_file", $agentPortFile,
  "--log_dir", $agentLogDir,
  "--home_dir", $agentHomeDir,
  "--port", $AgentPort,
  "--user_id", $UserId,
  "--work_mode", "local",
  "--kb_port_file", $kbPortFile,
  "--local_llm_port", $AdapterPort,
  "--lock_file", $agentLockFile
)

$agentProcess = Start-Process `
  -FilePath $MarvisAgentPath `
  -ArgumentList $arguments `
  -WorkingDirectory (Split-Path -Parent $MarvisAgentPath) `
  -WindowStyle Hidden `
  -RedirectStandardOutput $agentStdout `
  -RedirectStandardError $agentStderr `
  -PassThru

if (-not (Wait-HttpOk -Url "http://$ListenHost`:$AgentPort/health" -TimeoutSeconds 25)) {
  $agentProcess.Refresh()
  if ($agentProcess.HasExited) {
    throw "MarvisAgent process $($agentProcess.Id) exited before health check passed. Check $agentStderr."
  }
  throw "MarvisAgent process $($agentProcess.Id) started, but /health did not pass on $ListenHost`:$AgentPort. Check $agentStderr."
}

$status = [ordered]@{
  active = $true
  mode = "marvis-local-shell"
  workspace = $Workspace
  run_dir = $runDir
  adapter_port = $AdapterPort
  adapter_status_path = $adapterStatusPath
  agent_pid = $agentProcess.Id
  agent_port = $AgentPort
  agent_health_url = "http://$ListenHost`:$AgentPort/health"
  marvis_agent_path = $MarvisAgentPath
  user_id = $UserId
  started_at = (Get-Date).ToUniversalTime().ToString("o")
  pid_file = $currentStatusPath
}
$status | ConvertTo-Json | Set-Content -LiteralPath $currentStatusPath -Encoding UTF8

[PSCustomObject]$status
