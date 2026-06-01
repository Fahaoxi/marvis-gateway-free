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

function Convert-FromBase64Utf8([string]$Value) {
  return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Value))
}

$OriginalSnippetBase64 = "cmV0dXJuIGYudXNlTWVtbygoKT0+dCE9PUJvLkxvY2FsP0RBbjplIT09UjIuSW5zdGFsbENvbXBsZXRlZD97cGxhY2Vob2xkZXI6IuacrOWcsOaooeWei+mFjee9ruS4re+8jOW9k+WJjeS7jeaYr+aViOeOh+aooeW8j++8jOivt+i+k+WFpeS7u+WKoe+8jOS6pOe7meaIkeadpeWujOaIkCIsaXNSZXRyeUZhaWxlZDohMSxpc0xvYWRpbmc6ITF9Om4/LnN0YXR1cz09PUF4LkVycm9yJiZuLmlzUmV0cnlGYWlsZWQ/e3BsYWNlaG9sZGVyOiLmnKzlnLDmqKHlnovov5DooYzlvILluLjvvIzml6Dms5Xkvb/nlKjpmpDnp4HmqKHlvI/vvIzor7fliIfmjaLoh7PmlYjnjofmqKHlvI8iLGlzUmV0cnlGYWlsZWQ6ITAsaXNMb2FkaW5nOiExfTpuPy5zdGF0dXM9PT1BeC5SdW5uaW5nJiZyPT09ITA/e3BsYWNlaG9sZGVyOiLmnKzlnLDmqKHlnovlt7LlsLHnu6rvvIzlvZPliY3mmK/pmpDnp4HmqKHlvI/vvIzor7fovpPlhaXku7vliqHvvIzkuqTnu5nmiJHmnaXlrozmiJAiLGlzUmV0cnlGYWlsZWQ6ITEsaXNMb2FkaW5nOiExfTpuPy5zdGF0dXM9PT1BeC5SdW5uaW5nJiZyIT09ITA/e3BsYWNlaG9sZGVyOiLmnKzlnLDmqKHlnovljbPlsIblsLHnu6rvvIzor7fnqI3nrYkiLGlzUmV0cnlGYWlsZWQ6ITEsaXNMb2FkaW5nOiEwfTp7cGxhY2Vob2xkZXI6IuacrOWcsOaooeWei+ato+WcqOWKoOi9ve+8jOivt+eojeetiSIsaXNSZXRyeUZhaWxlZDohMSxpc0xvYWRpbmc6ITB9LFt0LGUsbixyXSk="
$PatchedSnippetBase64 = "cmV0dXJuIGYudXNlTWVtbygoKT0+dCE9PUJvLkxvY2FsP0RBbjp7cGxhY2Vob2xkZXI6IuacrOWcsOaooeWei+S7o+eQhuW3suaOpeeuoe+8jOW9k+WJjeaYr+makOengeaooeW8j++8jOivt+i+k+WFpeS7u+WKoe+8jOS6pOe7meaIkeadpeWujOaIkCIsaXNSZXRyeUZhaWxlZDohMSxpc0xvYWRpbmc6ITF9LFt0LGUsbixyXSk="
$OriginalSendFlowGateBase64 = "aWYoZy5jdXJyZW50KXtjdC5pbmZvKCJbU2VuZEZsb3ddIGFib3J0OiBsb2NhbCBtb2RlbCBpc1JldHJ5RmFpbGVkLCBzaG93aW5nIHN3aXRjaCBtb2RlIGNvbmZpcm0iKSxOdC5yZXBvcnRFdmVudCh7cGdpZDoiaG9tZSIsZXZlbnROYW1lOmljLkxPQ0FMX01PREVMX1JFVFJZX0ZBSUxFRCxidXNpbmVzc1BhcmFtczp7fX0pLGF3YWl0IHkuY3VycmVudCgpO3JldHVybn1pZihiLmN1cnJlbnQpe2N0LmluZm8oIltTZW5kRmxvd10gYWJvcnQ6IGxvY2FsIG1vZGVsIGlzIGxvYWRpbmcsIHNob3cgdG9hc3QiKSxNbigi5pys5Zyw5qih5Z6L5q2j5Zyo5Yqg6L2977yM6K+356iN562JIik7cmV0dXJufQ=="
$PatchedSendFlowGateBase64 = "aWYoZy5jdXJyZW50KXtjdC5pbmZvKCJbU2VuZEZsb3ddIGJ5cGFzczogbG9jYWwgbW9kZWwgaXNSZXRyeUZhaWxlZCwgY29udGludWUgdmlhIGV4dGVybmFsIGxvY2FsIGFkYXB0ZXIiKX1pZihiLmN1cnJlbnQpe2N0LmluZm8oIltTZW5kRmxvd10gYnlwYXNzOiBsb2NhbCBtb2RlbCBpcyBsb2FkaW5nLCBjb250aW51ZSB2aWEgZXh0ZXJuYWwgbG9jYWwgYWRhcHRlciIpfQ=="
$OriginalLazyLoadingStateBase64 = "e2lzTG9hZGluZzpJfT1TMCgpLFA9SCgkPT4kLnRhYi5hY3RpdmVUYWJJZCk="
$PatchedLazyLoadingStateBase64 = "e2lzTG9hZGluZzpJfT17aXNMb2FkaW5nOiExfSxQPUgoJD0+JC50YWIuYWN0aXZlVGFiSWQp"
$OriginalLazyLoadingToastBase64 = "SSYmUnMoIuacrOWcsOaooeWei+ato+WcqOWKoOi9ve+8jOivt+eojeetiSIp"
$PatchedLazyLoadingToastBase64 = "ITEmJlJzKCLmnKzlnLDmqKHlnovmraPlnKjliqDovb3vvIzor7fnqI3nrYkiKQ=="

$OriginalSnippet = Convert-FromBase64Utf8 $OriginalSnippetBase64
$PatchedSnippet = Convert-FromBase64Utf8 $PatchedSnippetBase64
$OriginalSendFlowGate = Convert-FromBase64Utf8 $OriginalSendFlowGateBase64
$PatchedSendFlowGate = Convert-FromBase64Utf8 $PatchedSendFlowGateBase64
$OriginalLazyLoadingState = Convert-FromBase64Utf8 $OriginalLazyLoadingStateBase64
$PatchedLazyLoadingState = Convert-FromBase64Utf8 $PatchedLazyLoadingStateBase64
$OriginalLazyLoadingToast = Convert-FromBase64Utf8 $OriginalLazyLoadingToastBase64
$PatchedLazyLoadingToast = Convert-FromBase64Utf8 $PatchedLazyLoadingToastBase64

if (-not (Test-Path -LiteralPath $BundlePath)) {
  throw "Marvis UI bundle not found: $BundlePath"
}
if (-not (Test-Path -LiteralPath $LazyChunkPath)) {
  throw "Marvis UI lazy chunk not found: $LazyChunkPath"
}

$backupDir = Join-Path $Workspace "captures\marvis-ui-patches"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$manifestPath = Join-Path $backupDir "latest-patch.json"
$previousManifest = $null
if (Test-Path -LiteralPath $manifestPath) {
  $previousManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$mainRaw = [System.IO.File]::ReadAllText($BundlePath, $utf8NoBom)
$lazyRaw = [System.IO.File]::ReadAllText($LazyChunkPath, $utf8NoBom)

$needsZotPatch = -not $mainRaw.Contains($PatchedSnippet)
$needsSendFlowPatch = -not $mainRaw.Contains($PatchedSendFlowGate)
$needsLazyStatePatch = -not $lazyRaw.Contains($PatchedLazyLoadingState)
$needsLazyToastPatch = -not $lazyRaw.Contains($PatchedLazyLoadingToast)

if (-not $needsZotPatch -and -not $needsSendFlowPatch -and -not $needsLazyStatePatch -and -not $needsLazyToastPatch) {
  [PSCustomObject]@{
    patched = $true
    changed = $false
    message = "Marvis UI loading gate patch is already fully applied."
    bundle_path = $BundlePath
    lazy_chunk_path = $LazyChunkPath
  }
  exit 0
}

if ($needsZotPatch -and -not $mainRaw.Contains($OriginalSnippet)) {
  throw "Target local LLM state snippet not found. Marvis may have updated its frontend bundle."
}
if ($needsSendFlowPatch -and -not $mainRaw.Contains($OriginalSendFlowGate)) {
  throw "Target SendFlow loading gate snippet not found. Marvis may have updated its frontend bundle."
}
if ($needsLazyStatePatch -and -not $lazyRaw.Contains($OriginalLazyLoadingState)) {
  throw "Target lazy chunk loading state snippet not found. Marvis may have updated its frontend bundle."
}
if ($needsLazyToastPatch -and -not $lazyRaw.Contains($OriginalLazyLoadingToast)) {
  throw "Target lazy chunk loading toast snippet not found. Marvis may have updated its frontend bundle."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $backupDir "index-B0ab8dhL.js.$stamp.bak"
$lazyBackupPath = Join-Path $backupDir "index-B3r57gBB.js.$stamp.bak"
Copy-Item -LiteralPath $BundlePath -Destination $backupPath -Force
Copy-Item -LiteralPath $LazyChunkPath -Destination $lazyBackupPath -Force

if (-not ($needsZotPatch -or $needsSendFlowPatch) -and $previousManifest.backup_path) {
  $backupPath = $previousManifest.backup_path
}
if (-not ($needsLazyStatePatch -or $needsLazyToastPatch) -and $previousManifest.lazy_backup_path) {
  $lazyBackupPath = $previousManifest.lazy_backup_path
}

$patchedMain = $mainRaw
if ($needsZotPatch) {
  $patchedMain = $patchedMain.Replace($OriginalSnippet, $PatchedSnippet)
}
if ($needsSendFlowPatch) {
  $patchedMain = $patchedMain.Replace($OriginalSendFlowGate, $PatchedSendFlowGate)
}

$patchedLazy = $lazyRaw
if ($needsLazyStatePatch) {
  $patchedLazy = $patchedLazy.Replace($OriginalLazyLoadingState, $PatchedLazyLoadingState)
}
if ($needsLazyToastPatch) {
  $patchedLazy = $patchedLazy.Replace($OriginalLazyLoadingToast, $PatchedLazyLoadingToast)
}

[System.IO.File]::WriteAllText($BundlePath, $patchedMain, $utf8NoBom)
[System.IO.File]::WriteAllText($LazyChunkPath, $patchedLazy, $utf8NoBom)

$manifest = [ordered]@{
  patched = $true
  bundle_path = $BundlePath
  backup_path = $backupPath
  lazy_chunk_path = $LazyChunkPath
  lazy_backup_path = $lazyBackupPath
  workspace = $Workspace
  patched_at = (Get-Date).ToUniversalTime().ToString("o")
  patch = "local-llm-loading-gate-bypass-v3"
  zot_patch_applied = $needsZotPatch
  sendflow_patch_applied = $needsSendFlowPatch
  lazy_loading_state_patch_applied = $needsLazyStatePatch
  lazy_loading_toast_patch_applied = $needsLazyToastPatch
  files = @(
    [ordered]@{
      "role" = "main_bundle"
      "path" = $BundlePath
      "backup_path" = $backupPath
      "changed" = ($needsZotPatch -or $needsSendFlowPatch)
    },
    [ordered]@{
      "role" = "lazy_chunk"
      "path" = $LazyChunkPath
      "backup_path" = $lazyBackupPath
      "changed" = ($needsLazyStatePatch -or $needsLazyToastPatch)
    }
  )
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

[PSCustomObject]@{
  patched = $true
  changed = $true
  bundle_path = $BundlePath
  backup_path = $backupPath
  lazy_chunk_path = $LazyChunkPath
  lazy_backup_path = $lazyBackupPath
  manifest_path = $manifestPath
}
