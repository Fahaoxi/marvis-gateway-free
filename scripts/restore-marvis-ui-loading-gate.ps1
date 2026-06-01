param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$BundlePath = "",
  [string]$LazyChunkPath = "",
  [string]$InstallRoot = "",
  [switch]$NoElevate
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "MarvisPaths.ps1")

function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not $NoElevate -and -not (Test-IsAdministrator)) {
  $argsList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSCommandPath`"",
    "-Workspace", "`"$Workspace`"",
    "-BundlePath", "`"$BundlePath`"",
    "-LazyChunkPath", "`"$LazyChunkPath`"",
    "-InstallRoot", "`"$InstallRoot`"",
    "-NoElevate"
  )
  Start-Process -FilePath "powershell.exe" -ArgumentList $argsList -Verb RunAs -Wait | Out-Null
  exit $LASTEXITCODE
}

$assetPaths = Resolve-MarvisOfflineAssetPaths -BundlePath $BundlePath -LazyChunkPath $LazyChunkPath -InstallRoot $InstallRoot
$BundlePath = $assetPaths.BundlePath
$LazyChunkPath = $assetPaths.LazyChunkPath

$backupDir = Join-Path $Workspace "captures\marvis-ui-patches"
$manifestPath = Join-Path $backupDir "latest-patch.json"

if (-not (Test-Path -LiteralPath $manifestPath)) {
  throw "Patch manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$filesToRestore = @()
if ($manifest.files) {
  $filesToRestore = @($manifest.files)
} else {
  $filesToRestore = @(
    [PSCustomObject]@{
      role = "main_bundle"
      path = $BundlePath
      backup_path = $manifest.backup_path
      changed = $true
    }
  )
  if ($manifest.lazy_backup_path) {
    $filesToRestore += [PSCustomObject]@{
      role = "lazy_chunk"
      path = $LazyChunkPath
      backup_path = $manifest.lazy_backup_path
      changed = $true
    }
  }
}

foreach ($file in $filesToRestore) {
  if (-not $file.backup_path -or -not (Test-Path -LiteralPath $file.backup_path)) {
    throw "Backup file not found for $($file.role). Manifest path: $manifestPath"
  }
}

foreach ($file in $filesToRestore) {
  Copy-Item -LiteralPath $file.backup_path -Destination $file.path -Force
}

$restoreStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$restoredManifestPath = Join-Path $backupDir "restored-$restoreStamp.json"
$restoreRecord = [ordered]@{
  restored = $true
  bundle_path = $BundlePath
  lazy_chunk_path = $LazyChunkPath
  restored_files = $filesToRestore
  restored_at = (Get-Date).ToUniversalTime().ToString("o")
  previous_manifest = $manifestPath
}
$restoreRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $restoredManifestPath -Encoding UTF8
Remove-Item -LiteralPath $manifestPath -Force

[PSCustomObject]@{
  restored = $true
  bundle_path = $BundlePath
  lazy_chunk_path = $LazyChunkPath
  restored_files = $filesToRestore.Count
  restore_record = $restoredManifestPath
}
