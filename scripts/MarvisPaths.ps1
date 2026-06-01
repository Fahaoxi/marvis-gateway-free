function Get-MarvisInstallRoot {
  param([string]$InstallRoot = "")

  if ($InstallRoot) {
    return $InstallRoot
  }

  $envRoot = [Environment]::GetEnvironmentVariable("MARVIS_INSTALL_ROOT", "Process")
  if (-not $envRoot) {
    $envRoot = [Environment]::GetEnvironmentVariable("MARVIS_INSTALL_ROOT", "User")
  }
  if ($envRoot) {
    return $envRoot
  }

  foreach ($candidate in @(
    "D:\Program Files\Tencent\Marvis",
    "C:\Program Files\Tencent\Marvis",
    "C:\Program Files (x86)\Tencent\Marvis"
  )) {
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }

  return "D:\Program Files\Tencent\Marvis"
}

function Convert-ToVersionOrNull {
  param([string]$Text)
  try {
    return [version]$Text
  }
  catch {
    return $null
  }
}

function Find-LatestMarvisVersionDirectory {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Parent,
    [Parameter(Mandatory = $true)]
    [string]$RequiredRelativePath
  )

  if (-not (Test-Path -LiteralPath $Parent)) {
    return $null
  }

  $candidates = @(
    Get-ChildItem -LiteralPath $Parent -Directory -ErrorAction SilentlyContinue |
      Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName $RequiredRelativePath) } |
      ForEach-Object {
        [PSCustomObject]@{
          Path = $_.FullName
          Version = Convert-ToVersionOrNull $_.Name
          Name = $_.Name
          LastWriteTime = $_.LastWriteTimeUtc
        }
      }
  )

  if (-not $candidates) {
    return $null
  }

  $versioned = @($candidates | Where-Object { $null -ne $_.Version })
  if ($versioned) {
    return ($versioned | Sort-Object Version -Descending | Select-Object -First 1).Path
  }

  return ($candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Path
}

function Resolve-MarvisApplicationExe {
  param(
    [string]$MarvisExe = "",
    [string]$InstallRoot = ""
  )

  if ($MarvisExe) {
    return $MarvisExe
  }

  $root = Get-MarvisInstallRoot -InstallRoot $InstallRoot
  $applicationRoot = Join-Path $root "Application"
  $applicationDir = Find-LatestMarvisVersionDirectory -Parent $applicationRoot -RequiredRelativePath "Marvis.exe"
  if (-not $applicationDir) {
    throw "Could not find Marvis.exe under '$applicationRoot'. Pass -MarvisExe or set MARVIS_INSTALL_ROOT."
  }
  return (Join-Path $applicationDir "Marvis.exe")
}

function Resolve-MarvisAgentDir {
  param(
    [string]$AgentDir = "",
    [string]$InstallRoot = ""
  )

  if ($AgentDir) {
    return $AgentDir
  }

  $root = Get-MarvisInstallRoot -InstallRoot $InstallRoot
  $agentRoot = Join-Path $root "MarvisAgent"
  $agentDir = Find-LatestMarvisVersionDirectory -Parent $agentRoot -RequiredRelativePath "MarvisAgent.exe"
  if (-not $agentDir) {
    throw "Could not find MarvisAgent.exe under '$agentRoot'. Pass -AgentDir or set MARVIS_INSTALL_ROOT."
  }
  return $agentDir
}

function Resolve-MarvisOfflineAssetPaths {
  param(
    [string]$BundlePath = "",
    [string]$LazyChunkPath = "",
    [string]$InstallRoot = ""
  )

  if ($BundlePath -and $LazyChunkPath) {
    return [PSCustomObject]@{
      BundlePath = $BundlePath
      LazyChunkPath = $LazyChunkPath
    }
  }

  $marvisExe = Resolve-MarvisApplicationExe -InstallRoot $InstallRoot
  $assetsDir = Join-Path (Split-Path -Parent $marvisExe) "marvis-offline-page\assets"
  if (-not (Test-Path -LiteralPath $assetsDir)) {
    throw "Could not find Marvis offline assets under '$assetsDir'. Pass -BundlePath and -LazyChunkPath."
  }

  if (-not $BundlePath) {
    $bundle = Get-ChildItem -LiteralPath $assetsDir -Filter "index-*.js" -File -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -ne "index-B3r57gBB.js" } |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1
    if (-not $bundle) {
      throw "Could not find main Marvis UI bundle under '$assetsDir'. Pass -BundlePath."
    }
    $BundlePath = $bundle.FullName
  }

  if (-not $LazyChunkPath) {
    $lazy = Get-ChildItem -LiteralPath $assetsDir -Filter "index-*.js" -File -ErrorAction SilentlyContinue |
      Where-Object {
        try {
          $text = [System.IO.File]::ReadAllText($_.FullName, [System.Text.UTF8Encoding]::new($false))
          $text.Contains("S0()") -or $text.Contains("isLoading")
        }
        catch {
          $false
        }
      } |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1
    if (-not $lazy) {
      throw "Could not find Marvis UI lazy chunk under '$assetsDir'. Pass -LazyChunkPath."
    }
    $LazyChunkPath = $lazy.FullName
  }

  return [PSCustomObject]@{
    BundlePath = $BundlePath
    LazyChunkPath = $LazyChunkPath
  }
}
