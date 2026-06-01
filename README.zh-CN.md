# Marvis 第三方 API 网关

[English](README.md)

让 [腾讯 Marvis](https://marvis.qq.com/) 接入第三方 OpenAI 兼容 API，同时保留官方桌面端体验。支持云端、私有化或自建模型服务，通过本地网关灵活转发请求。

## 项目简介

本项目提供 Windows 启动脚本和本地 OpenAI 兼容网关，用于把腾讯 Marvis 的模型请求转发到外部兼容服务。适合想继续使用 Marvis 桌面 UI，同时自由选择第三方 API、私有部署或自建模型服务的用户。

```text
Marvis UI
  -> MarvisAgent wrapper
  -> Marvis Agent request path
  -> local OpenAI-compatible gateway on 127.0.0.1:19080
  -> third-party OpenAI-compatible API
```

provider 可以是公共云 API、私有化部署，也可以是自建的 OpenAI 兼容服务。

## 免责声明

本项目是非官方社区项目，与 Marvis 或腾讯无隶属、背书或赞助关系。本仓库不包含 Marvis 官方二进制文件、专有资源或逆向源码。使用者需自行遵守 Marvis 及第三方模型服务商的相关条款。

## 环境要求

- Windows
- PowerShell 5+ 或 PowerShell 7+
- Python 3.12+
- Node.js 18+
- 腾讯 Marvis 桌面版
- 一个 OpenAI 兼容 API 端点

## 安装

```powershell
python -m pip install -e .[dev]
npm install
```

## 配置模型服务

设置用于保存 provider API key 的环境变量：

```powershell
[Environment]::SetEnvironmentVariable('MARVIS_THIRD_PARTY_API_KEY', '<your api key>', 'User')
```

如果你想手动设置，可以在 Windows 里打开“环境变量”设置，新建一个用户变量：

- 变量名：`MARVIS_THIRD_PARTY_API_KEY`
- 变量值：你的 API Key

创建本地 provider 配置：

```powershell
Copy-Item .\config\third-party-api.example.toml .\config\third-party-api.local.toml
notepad .\config\third-party-api.local.toml
```

使用前请确认已经将 `config\third-party-api.example.toml` 复制或重命名为 `config\third-party-api.local.toml`。

示例：

```toml
[provider]
base_url = "https://api.example.com/v1"
model = "your-model-name"
api_key_env = "MARVIS_THIRD_PARTY_API_KEY"
timeout_seconds = 120
```

如果 Marvis 不在默认安装位置，可以设置：

```powershell
[Environment]::SetEnvironmentVariable('MARVIS_INSTALL_ROOT', 'D:\Path\To\Tencent\Marvis', 'User')
```

## 使用启动器

用途：启动 Marvis，并把模型请求转发到第三方 OpenAI 兼容服务，方便联调、测试和排障；请勿用于非法、未授权或超出服务条款的用途。

在仓库根目录双击：

```text
Marvis本地外壳启动器.bat
```

按这个顺序用就行：

1. 先确认 Marvis 已完全退出，并且已经配好 API Key 和 `config\third-party-api.local.toml`。
2. 双击 `Marvis本地外壳启动器.bat`。
3. 输入 `1` 启动。
4. 启动后可以输入 `2` 查看状态。
5. 用完输入 `3` 停止。
6. 需要还原官方 Agent 时，先输入 `3` 停止，再执行 `4. 还原官方 Agent`。

菜单选项：

- `1. 启动`：启动 adapter，安装或更新 Agent wrapper，并启动 Marvis。
- `2. 查看状态`：查看 adapter、wrapper 和 Agent 状态。
- `3. 停止`：停止由启动器创建的进程。
- `4. 还原官方 Agent`：恢复官方 `MarvisAgent.exe`。
- `5. 退出`：关闭启动器。

注意：启动和还原前都不要让 Marvis 处于运行状态；还原前务必先停止启动器创建的进程。

## 命令行用法

启动完整 wrapper 链路：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-marvis-wrapper-shell.ps1
```

启动并运行本地暗号验证：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-marvis-wrapper-shell.ps1 -RunCanary
```

查看状态：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\get-marvis-wrapper-shell-status.ps1
```

停止 wrapper 链路和 adapter：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-marvis-wrapper-shell.ps1 -StopAdapter -Force
```

还原官方 Agent：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-marvis-agent-wrapper.ps1
```

只启动 adapter：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-model-adapter.ps1
```

## 验证链路

启动后，在仓库根目录打开 PowerShell，运行：

```powershell
node .\scripts\test-marvis-third-party-canary.js --port 6161
```

它会发送 `MARVIS_THIRD_PARTY_PING`。看到 `SUMMARY` 里 `ok: true`，并且 `actualText` 是 `成功`，就说明成功了。

简单 live smoke：

```powershell
node .\scripts\smoke-marvis-agent.js --port 6161 --mode simple
```

live smoke 可能会调用你配置的 provider。

## 常见报错

### 启动器启动后无响应

请尝试打开腾讯 Marvis 桌面端，然后完全退出，再重新运行启动器。

### `Local OpenAI adapter did not become healthy on 127.0.0.1:19080`

这表示启动脚本等不到 `http://127.0.0.1:19080/health` 返回健康状态。先看 adapter stderr：

```powershell
Get-Content .\captures\local-model-adapter\local-model-adapter-err.log -Tail 80
```

如果日志里出现类似 `unrecognized arguments: - git ...\config\third-party-api.local.toml`，通常是工作目录路径包含空格，例如 `D:\idea - git 测试`，导致 PowerShell 启动 Python adapter 时把路径拆成了多段。此时 adapter 进程会在绑定 `19080` 前退出，外层脚本就会报健康检查失败。优先把仓库放到不含空格的路径，例如 `D:\idea-test`，再重新启动。

### 还原官方 Agent 失败：`Cannot create a file when that file already exists.`

这个报错通常表示 `MarvisAgent.exe` 仍然存在，脚本无法把 `MarvisAgent.real.exe` 移回 `MarvisAgent.exe`。常见原因是 Marvis 或 Agent 进程还在运行，导致当前 wrapper 版 `MarvisAgent.exe` 没有被删除。

先完全退出 Marvis，再确认没有残留进程：

```powershell
Get-Process -Name "Marvis*" -ErrorAction SilentlyContinue
```

确认进程退出后再执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-marvis-agent-wrapper.ps1
```

`No local model adapter PID file found ... Nothing to stop.` 不是还原失败原因，只表示没有 adapter PID 记录可停止。

## 项目结构

```text
config/   Provider 配置模板。
docs/     架构与排障文档。
scripts/  启动、状态、恢复和 smoke 脚本。
src/      Python adapter、wrapper helper、capture 工具和 CLI。
tests/    单元测试。
```

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [排障指南](docs/TROUBLESHOOTING.md)
- [贡献指南](CONTRIBUTING.md)
- [安全说明](SECURITY.md)

## 开发

```powershell
python -m pytest
```
