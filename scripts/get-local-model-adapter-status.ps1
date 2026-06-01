param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$CapturesDir = "",
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

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

function Write-StoppedStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$StatusPath,
    [string]$CapturesDir,
    [string]$Message,
    [string]$LastError = ""
  )

  $status = [ordered]@{
    active = $false
    captures_dir = $CapturesDir
    last_error = $LastError
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

function Get-WorkspacePython {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace,
    [string]$PythonExe = ""
  )

  if ($PythonExe) {
    return $PythonExe
  }

  $workspacePython = Join-Path $Workspace ".venv\Scripts\python.exe"
  if (Test-Path $workspacePython) {
    return $workspacePython
  }
  return "python"
}

if (-not $CapturesDir) {
  $CapturesDir = Join-Path $Workspace "captures\local-model-adapter"
}

$python = Get-WorkspacePython -Workspace $Workspace -PythonExe $PythonExe
$srcPath = Join-Path $Workspace "src"
$statusPath = Join-Path $CapturesDir "runtime-status.json"
$pidPath = Join-Path $CapturesDir "local-model-adapter.pid.json"

if (Test-Path $statusPath) {
  $status = Get-Content -Path $statusPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
  if ($status -and $status.active) {
    $adapterPid = 0
    $listenPort = 0
    if ($status.pid) {
      $adapterPid = [int]$status.pid
    }
    if ($status.listen_port) {
      $listenPort = [int]$status.listen_port
    }

    $isReallyActive = $false
    if ($adapterPid -gt 0 -and $listenPort -gt 0) {
      $process = Get-Process -Id $adapterPid -ErrorAction SilentlyContinue
      $isReallyActive = [bool]($process) -and (Test-ProcessOwnsTcpListenPort -ProcessId $adapterPid -Port $listenPort)
    }

    if (-not $isReallyActive) {
      Remove-Item -Path $pidPath -Force -ErrorAction SilentlyContinue
      Write-StoppedStatus `
        -StatusPath $statusPath `
        -CapturesDir $CapturesDir `
        -Message "Local model adapter is stopped." `
        -LastError "Removed stale local model adapter status; no verified listener is active."
    }
  }
}

$previousPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
try {
  [Environment]::SetEnvironmentVariable("PYTHONPATH", $srcPath, "Process")
  & $python -m marvis_gateway_lab.cli status --status-path $statusPath
  exit $LASTEXITCODE
}
finally {
  [Environment]::SetEnvironmentVariable("PYTHONPATH", $previousPythonPath, "Process")
}
