param(
  [string]$Workspace = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

function Write-Title {
  Clear-Host
  Write-Host ""
  Write-Host "========================================" -ForegroundColor Cyan
  Write-Host "  Marvis 本地模型外壳启动器" -ForegroundColor Cyan
  Write-Host "========================================" -ForegroundColor Cyan
  Write-Host ""
}

function Wait-Menu {
  Write-Host ""
  Read-Host "按回车返回菜单"
}

function Test-Ready {
  $configPath = Join-Path $Workspace "config\third-party-api.local.toml"
  if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Host "未找到配置文件：" -ForegroundColor Red
    Write-Host $configPath
    Write-Host ""
    Write-Host "请先复制 config\third-party-api.example.toml 为 config\third-party-api.local.toml。"
    return $false
  }

  $apiKey = [Environment]::GetEnvironmentVariable("MARVIS_THIRD_PARTY_API_KEY", "Process")
  if (-not $apiKey) {
    $apiKey = [Environment]::GetEnvironmentVariable("MARVIS_THIRD_PARTY_API_KEY", "User")
  }
  if (-not $apiKey) {
    Write-Host "未检测到环境变量 MARVIS_THIRD_PARTY_API_KEY。" -ForegroundColor Red
    Write-Host ""
    Write-Host "请先在 PowerShell 中运行："
    Write-Host "[Environment]::SetEnvironmentVariable('MARVIS_THIRD_PARTY_API_KEY', '你的真实Key', 'User')"
    return $false
  }

  return $true
}

function Start-Shell {
  Write-Title
  Write-Host "[1/5] 检查配置 ..." -NoNewline
  if (-not (Test-Ready)) {
    Wait-Menu
    return
  }
  Write-Host " OK" -ForegroundColor Green

  Write-Host "[2/5] 检查启动脚本 ..." -NoNewline
  $startScript = Join-Path $Workspace "scripts\start-marvis-wrapper-shell.ps1"
  if (-not (Test-Path -LiteralPath $startScript)) {
    Write-Host " 失败" -ForegroundColor Red
    Write-Host "找不到 $startScript"
    Wait-Menu
    return
  }
  Write-Host " OK" -ForegroundColor Green

  Write-Host "[3/5] 安装 Agent wrapper ..."
  Write-Host "[4/5] 启动第三方 API adapter ..."
  Write-Host "[5/5] 启动官方 Marvis ..."
  Write-Host ""

  try {
    & $startScript -Workspace $Workspace | Out-Host
    Write-Host ""
    Write-Host "启动成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "第三方 API adapter：127.0.0.1:19080"
    Write-Host "Marvis Agent：127.0.0.1:6161"
  }
  catch {
    Write-Host ""
    Write-Host "启动失败：" -ForegroundColor Red
    Write-Host $_.Exception.Message
  }

  Wait-Menu
}

function Show-Status {
  Write-Title
  $statusScript = Join-Path $Workspace "scripts\get-marvis-wrapper-shell-status.ps1"
  try {
    & $statusScript -Workspace $Workspace | Out-Host
  }
  catch {
    Write-Host "读取状态失败：" -ForegroundColor Red
    Write-Host $_.Exception.Message
  }
  Wait-Menu
}

function Stop-Shell {
  Write-Title
  $stopScript = Join-Path $Workspace "scripts\stop-marvis-wrapper-shell.ps1"
  try {
    & $stopScript -Workspace $Workspace -StopAdapter -Force | Out-Host
    Write-Host ""
    Write-Host "已停止本启动器创建的进程。" -ForegroundColor Green
  }
  catch {
    Write-Host "停止时遇到问题：" -ForegroundColor Red
    Write-Host $_.Exception.Message
  }
  Wait-Menu
}

function Restore-Agent {
  Write-Title
  $stopScript = Join-Path $Workspace "scripts\stop-marvis-wrapper-shell.ps1"
  $restoreScript = Join-Path $Workspace "scripts\restore-marvis-agent-wrapper.ps1"

  try {
    Write-Host "这个操作会停止 Marvis 相关进程，并把 MarvisAgent.exe 还原为官方原文件。" -ForegroundColor Yellow
    Write-Host "还原后，如需再次走第三方 API，请重新选择“启动”安装 wrapper。"
    Write-Host ""
    Read-Host "准备好后按回车继续"

    & $stopScript -Workspace $Workspace -StopAdapter -Force | Out-Host
    & $restoreScript | Out-Host

    Write-Host ""
    Write-Host "已还原官方 Agent。" -ForegroundColor Green
  }
  catch {
    Write-Host "还原官方 Agent 失败：" -ForegroundColor Red
    Write-Host $_.Exception.Message
  }

  Wait-Menu
}

while ($true) {
  Write-Title
  Write-Host "  1. 启动"
  Write-Host "  2. 查看状态"
  Write-Host "  3. 停止"
  Write-Host "  4. 还原官方 Agent"
  Write-Host "  5. 退出"
  Write-Host ""
  $choice = Read-Host "请选择 1-5"

  switch ($choice) {
    "1" { Start-Shell }
    "2" { Show-Status }
    "3" { Stop-Shell }
    "4" { Restore-Agent }
    "5" { return }
    default {
      Write-Host ""
      Write-Host "输入无效，请重新选择。" -ForegroundColor Yellow
      Start-Sleep -Seconds 1
    }
  }
}

