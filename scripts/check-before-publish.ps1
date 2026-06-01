param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"

$blockedPaths = @(
  "captures",
  "node_modules",
  ".venv",
  ".pytest_cache",
  "config\third-party-api.local.toml"
)

$blockedPatterns = @(
  "**\__pycache__",
  "**\*.pyc",
  "**\*.pyo",
  "**\*.log",
  "**\*.pid.json"
)

$issues = New-Object System.Collections.Generic.List[string]

foreach ($relativePath in $blockedPaths) {
  $path = Join-Path $Workspace $relativePath
  if (Test-Path -LiteralPath $path) {
    $issues.Add("Local-only path exists: $relativePath")
  }
}

foreach ($pattern in $blockedPatterns) {
  $matches = @(Get-ChildItem -Path $Workspace -Recurse -Force -ErrorAction SilentlyContinue -Include (Split-Path $pattern -Leaf) |
    Where-Object {
      $full = $_.FullName
      $full -notlike "*\node_modules\*" -and
      $full -notlike "*\captures\*" -and
      $full -notlike "*\.venv\*" -and
      $full -notlike "*\.pytest_cache\*"
    } |
    Select-Object -First 5)
  foreach ($match in $matches) {
    $issues.Add("Generated artifact exists: $($match.FullName.Substring($Workspace.Length).TrimStart('\'))")
  }
}

$secretHits = @(
  rg -n --hidden --pcre2 `
    --glob "!node_modules/**" `
    --glob "!captures/**" `
    --glob "!**/__pycache__/**" `
    --glob "!.pytest_cache/**" `
    --glob "!config/third-party-api.local.toml" `
    --glob "!tests/**" `
    --glob "!docs/**" `
    --glob "!scripts/check-before-publish.ps1" `
    'raw_api_key\s*=\s*["''][^"'']{8,}["'']|api_key\s*=\s*["''](?!<your|your-|example|test|secret|unused)[^"'']{12,}["'']|Bearer\s+[A-Za-z0-9_\-]{32,}|sk-[A-Za-z0-9]{20,}' `
    $Workspace 2>$null
)
foreach ($hit in $secretHits) {
  $issues.Add("Possible secret: $hit")
}

if ($issues.Count -gt 0) {
  Write-Host "Publish check failed:" -ForegroundColor Red
  foreach ($issue in $issues) {
    Write-Host " - $issue"
  }
  Write-Host ""
  Write-Host "These paths are ignored by git, but remove them before uploading a zip or dragging files into GitHub."
  exit 1
}

Write-Host "Publish check passed." -ForegroundColor Green
