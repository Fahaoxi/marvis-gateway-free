param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
  [string]$BundlePath = "",
  [string]$LazyChunkPath = "",
  [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "MarvisPaths.ps1")

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

$backupDir = Join-Path $Workspace "captures\marvis-ui-patches"
$manifestPath = Join-Path $backupDir "latest-patch.json"
$manifest = $null
if (Test-Path -LiteralPath $manifestPath) {
  $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$bundleExists = Test-Path -LiteralPath $BundlePath
$lazyExists = Test-Path -LiteralPath $LazyChunkPath
$mainRaw = ""
$lazyRaw = ""
if ($bundleExists) {
  $mainRaw = [System.IO.File]::ReadAllText($BundlePath, $utf8NoBom)
}
if ($lazyExists) {
  $lazyRaw = [System.IO.File]::ReadAllText($LazyChunkPath, $utf8NoBom)
}

$mainPatched = $bundleExists -and $mainRaw.Contains($PatchedSnippet) -and $mainRaw.Contains($PatchedSendFlowGate)
$lazyPatched = $lazyExists -and $lazyRaw.Contains($PatchedLazyLoadingState) -and $lazyRaw.Contains($PatchedLazyLoadingToast)

[PSCustomObject]@{
  bundle_path = $BundlePath
  lazy_chunk_path = $LazyChunkPath
  exists = $bundleExists
  lazy_chunk_exists = $lazyExists
  patched = $mainPatched -and $lazyPatched
  main_bundle_patched = $mainPatched
  lazy_chunk_patched = $lazyPatched
  original_snippet_present = $bundleExists -and $mainRaw.Contains($OriginalSnippet)
  patched_snippet_present = $bundleExists -and $mainRaw.Contains($PatchedSnippet)
  original_sendflow_gate_present = $bundleExists -and $mainRaw.Contains($OriginalSendFlowGate)
  patched_sendflow_gate_present = $bundleExists -and $mainRaw.Contains($PatchedSendFlowGate)
  original_lazy_loading_state_present = $lazyExists -and $lazyRaw.Contains($OriginalLazyLoadingState)
  patched_lazy_loading_state_present = $lazyExists -and $lazyRaw.Contains($PatchedLazyLoadingState)
  original_lazy_loading_toast_present = $lazyExists -and $lazyRaw.Contains($OriginalLazyLoadingToast)
  patched_lazy_loading_toast_present = $lazyExists -and $lazyRaw.Contains($PatchedLazyLoadingToast)
  manifest_path = $manifestPath
  manifest_exists = Test-Path -LiteralPath $manifestPath
  backup_path = $manifest.backup_path
  lazy_backup_path = $manifest.lazy_backup_path
  patched_at = $manifest.patched_at
}
