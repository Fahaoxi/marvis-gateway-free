param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$CapturesDir = "",
  [int]$TimeoutSeconds = 10,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-LocalModelAdapterProcess {
  param(
    [Parameter(Mandatory = $true)]
    [int]$AdapterPid,
    [string]$ExpectedStopFile = "",
    [string]$ExpectedStatusPath = "",
    [string]$ExpectedCapturesDir = ""
  )

  try {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $AdapterPid" -ErrorAction Stop
    if (-not $process) {
      return $null
    }
    if ($process.CommandLine -notmatch "marvis_gateway_lab\.cli" -or $process.CommandLine -notmatch "\blocal-openai-adapter\b") {
      return $null
    }
    foreach ($expected in @($ExpectedStopFile, $ExpectedStatusPath, $ExpectedCapturesDir)) {
      if ($expected -and $process.CommandLine -notmatch [regex]::Escape($expected)) {
        return $null
      }
    }
    return $process
  }
  catch {
    return $null
  }
}

function Write-StoppedStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$StatusPath,
    [string]$CapturesDir,
    [string]$Message
  )

  $status = [ordered]@{
    active = $false
    captures_dir = $CapturesDir
    last_error = ""
    listen_host = "127.0.0.1"
    listen_port = 19080
    message = $Message
    mode = "stopped"
    pid = $null
    updated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    upstream_url = ""
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StatusPath) | Out-Null
  $status | ConvertTo-Json | Set-Content -Path $StatusPath -Encoding UTF8
}

if (-not $CapturesDir) {
  $CapturesDir = Join-Path $Workspace "captures\local-model-adapter"
}

$pidPath = Join-Path $CapturesDir "local-model-adapter.pid.json"
$statusPath = Join-Path $CapturesDir "runtime-status.json"

if (-not (Test-Path $pidPath)) {
  Write-Host "No local model adapter PID file found at $pidPath. Nothing to stop."
  return
}

try {
  $pidRecord = Get-Content -Path $pidPath -Raw | ConvertFrom-Json -ErrorAction Stop
}
catch {
  Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
  throw "Local model adapter PID file was invalid and has been removed: $pidPath"
}

$adapterPid = [int]$pidRecord.pid
$stopPath = [string]$pidRecord.stop_file
if (-not $stopPath) {
  $stopPath = Join-Path $CapturesDir "local-model-adapter.stop"
}
$recordedStatusPath = [string]$pidRecord.status_path
if ($recordedStatusPath) {
  $statusPath = $recordedStatusPath
}
$expectedCapturesDir = [string]$pidRecord.captures_dir
if (-not $expectedCapturesDir) {
  $expectedCapturesDir = $CapturesDir
}

$adapterProcess = Get-LocalModelAdapterProcess -AdapterPid $adapterPid -ExpectedStopFile $stopPath -ExpectedStatusPath $statusPath -ExpectedCapturesDir $expectedCapturesDir
if (-not $adapterProcess) {
  Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
  throw "PID $adapterPid is not a marvis_gateway_lab local-openai-adapter process. Removed stale PID file without stopping anything."
}

Set-Content -Path $stopPath -Value "stop" -Encoding ASCII

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
  Start-Sleep -Milliseconds 250
  if (-not (Get-Process -Id $adapterPid -ErrorAction SilentlyContinue)) {
    Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $stopPath -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped local model adapter process $adapterPid."
    return
  }
} while ((Get-Date) -lt $deadline)

if ($Force) {
  Stop-Process -Id $adapterPid -Force -ErrorAction Stop
  Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
  Remove-Item -Path $stopPath -Force -ErrorAction SilentlyContinue
  Write-StoppedStatus -StatusPath $statusPath -CapturesDir $CapturesDir -Message "Local model adapter force-stopped."
  Write-Host "Force-stopped local model adapter process $adapterPid after graceful stop timed out."
  return
}

throw "Local model adapter process $adapterPid did not stop within $TimeoutSeconds seconds. Re-run with -Force if you want to terminate it."
