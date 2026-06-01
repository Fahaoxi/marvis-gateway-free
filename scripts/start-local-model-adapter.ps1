param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$Config = "",
  [string]$LocalConfig = "",
  [string]$CapturesDir = "",
  [string]$PythonExe = "",
  [string]$ListenHost = "127.0.0.1",
  [int]$ListenPort = 19080
)

$ErrorActionPreference = "Stop"

function Get-WorkspacePython {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace,
    [string]$PythonExe = ""
  )

  if ($PythonExe) {
    if (-not (Test-Path -LiteralPath $PythonExe)) {
      throw "PythonExe '$PythonExe' does not exist."
    }
    return $PythonExe
  }

  $workspacePython = Join-Path $Workspace ".venv\Scripts\python.exe"
  if (Test-Path $workspacePython) {
    return $workspacePython
  }
  return "python"
}

function Import-ProviderEnvironmentVariables {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Config
  )

  if (-not (Test-Path -LiteralPath $Config)) {
    return
  }

  $content = Get-Content -LiteralPath $Config -Raw
  $matches = [regex]::Matches($content, '^\s*api_key_env\s*=\s*"([^"]+)"\s*$', [System.Text.RegularExpressions.RegexOptions]::Multiline)
  foreach ($match in $matches) {
    $name = $match.Groups[1].Value
    if (-not $name) {
      continue
    }
    $processValue = [Environment]::GetEnvironmentVariable($name, "Process")
    if ($processValue) {
      continue
    }
    $userValue = [Environment]::GetEnvironmentVariable($name, "User")
    if ($userValue) {
      [Environment]::SetEnvironmentVariable($name, $userValue, "Process")
    }
  }
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
    # Some environments deny Get-NetTCPConnection. Fall back to netstat.
  }

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
  return $false
}

function Get-LocalModelAdapterProcess {
  param(
    [Parameter(Mandatory = $true)]
    [int]$AdapterPid,
    [Parameter(Mandatory = $true)]
    [string]$Workspace,
    [int]$ListenPort = 0
  )

  try {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $AdapterPid" -ErrorAction Stop
    if (-not $process) {
      return $null
    }
    if ($process.CommandLine -notmatch "marvis_gateway_lab\.cli" -or $process.CommandLine -notmatch "\blocal-openai-adapter\b") {
      return $null
    }
    if ($process.CommandLine -notmatch [regex]::Escape($Workspace)) {
      return $null
    }
    return $process
  }
  catch {
    # Command-line inspection can be denied. PID plus listener ownership is the fallback.
  }

  if ($ListenPort -gt 0 -and (Test-ProcessOwnsTcpListenPort -ProcessId $AdapterPid -Port $ListenPort)) {
    return Get-Process -Id $AdapterPid -ErrorAction SilentlyContinue
  }
  return $null
}

function Get-ActiveAdapterPidFromPidFile {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [int]$ListenPort = 0
  )

  if (-not (Test-Path $Path)) {
    return $null
  }

  try {
    $pidRecord = Get-Content -Path $Path -Raw | ConvertFrom-Json -ErrorAction Stop
    $adapterPid = [int]$pidRecord.pid
    if ($adapterPid -gt 0) {
      $process = Get-Process -Id $adapterPid -ErrorAction SilentlyContinue
      if ($process -and $ListenPort -gt 0 -and (Test-ProcessOwnsTcpListenPort -ProcessId $adapterPid -Port $ListenPort)) {
        return $adapterPid
      }
      Remove-Item -Path $Path -Force -ErrorAction SilentlyContinue
    }
  }
  catch {
    Remove-Item -Path $Path -Force -ErrorAction SilentlyContinue
  }

  return $null
}

if (-not $Config) {
  $Config = Join-Path $Workspace "config\third-party-api.local.toml"
}
if (-not $LocalConfig) {
  $LocalConfig = ""
}
if (-not $CapturesDir) {
  $CapturesDir = Join-Path $Workspace "captures\local-model-adapter"
}

New-Item -ItemType Directory -Path $CapturesDir -Force | Out-Null

$srcPath = Join-Path $Workspace "src"
$statusPath = Join-Path $CapturesDir "runtime-status.json"
$pidPath = Join-Path $CapturesDir "local-model-adapter.pid.json"
$stopPath = Join-Path $CapturesDir "local-model-adapter.stop"
$stdoutPath = Join-Path $CapturesDir "local-model-adapter-out.log"
$stderrPath = Join-Path $CapturesDir "local-model-adapter-err.log"
Remove-Item -Path $stopPath -Force -ErrorAction SilentlyContinue

$activeAdapterPid = Get-ActiveAdapterPidFromPidFile -Path $pidPath -ListenPort $ListenPort
if ($null -ne $activeAdapterPid) {
  throw "CapturesDir '$CapturesDir' already has an active local model adapter PID $activeAdapterPid recorded in $pidPath. Stop it first with stop-local-model-adapter.ps1, or use an independent CapturesDir."
}

if (Wait-ListeningPort -HostName $ListenHost -Port $ListenPort -TimeoutSeconds 1) {
  throw "$ListenHost`:$ListenPort is already accepting TCP connections. Stop or move the existing listener before starting this local model adapter."
}

$python = Get-WorkspacePython -Workspace $Workspace -PythonExe $PythonExe
Import-ProviderEnvironmentVariables -Config $Config

$arguments = @(
  "-m", "marvis_gateway_lab.cli", "local-openai-adapter",
  "--config", $Config,
  "--listen-host", $ListenHost,
  "--listen-port", $ListenPort,
  "--status-path", $statusPath,
  "--stop-file", $stopPath
)
if ($LocalConfig -and (Test-Path $LocalConfig)) {
  $arguments += @("--local-config", $LocalConfig)
}

$previousPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
try {
  [Environment]::SetEnvironmentVariable("PYTHONPATH", $srcPath, "Process")
  $process = Start-Process `
    -FilePath $python `
    -ArgumentList $arguments `
    -WorkingDirectory $Workspace `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru
}
finally {
  [Environment]::SetEnvironmentVariable("PYTHONPATH", $previousPythonPath, "Process")
}

$startedAt = (Get-Date).ToUniversalTime().ToString("o")
@{
  pid = $process.Id
  started_at = $startedAt
  workspace = $Workspace
  command = "marvis_gateway_lab.cli local-openai-adapter"
  config = $Config
  local_config = $LocalConfig
  stop_file = $stopPath
  status_path = $statusPath
  captures_dir = $CapturesDir
} | ConvertTo-Json | Set-Content -Path $pidPath -Encoding UTF8

if (-not (Wait-ListeningPort -HostName $ListenHost -Port $ListenPort -TimeoutSeconds 10)) {
  if (-not (Get-LocalModelAdapterProcess -AdapterPid $process.Id -Workspace $Workspace -ListenPort $ListenPort)) {
    Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
    throw "Local model adapter process $($process.Id) exited before $ListenHost`:$ListenPort became ready. Check $stderrPath."
  }
  Write-Warning "Local model adapter process $($process.Id) was started, but $ListenHost`:$ListenPort did not accept connections within 10 seconds. Check $stderrPath."
}

Start-Sleep -Milliseconds 500
if (-not (Get-LocalModelAdapterProcess -AdapterPid $process.Id -Workspace $Workspace -ListenPort $ListenPort)) {
  Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
  throw "Local model adapter process $($process.Id) is not running after startup. Check $stderrPath."
}

[PSCustomObject]@{
  pid = $process.Id
  listen_host = $ListenHost
  listen_port = $ListenPort
  config = $Config
  local_config = $LocalConfig
  pid_file = $pidPath
  status_file = $statusPath
  captures_dir = $CapturesDir
}
