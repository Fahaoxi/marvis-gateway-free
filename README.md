# Marvis Third-Party API Gateway

[简体中文](README.zh-CN.md)

Connect [Tencent Marvis](https://marvis.qq.com/) to third-party OpenAI-compatible APIs while keeping the official desktop UI. Use cloud, private, or self-hosted model providers through a local gateway.

## Overview

This project provides a Windows launcher and local OpenAI-compatible gateway for routing Tencent Marvis model requests to external providers. It is intended for users who want to keep the Marvis desktop experience while choosing their own compatible API provider.

```text
Marvis UI
  -> MarvisAgent wrapper
  -> Marvis Agent request path
  -> local OpenAI-compatible gateway on 127.0.0.1:19080
  -> third-party OpenAI-compatible API
```

The provider can be a public cloud API, a private deployment, or a self-hosted OpenAI-compatible service.

## Disclaimer

This is an unofficial community project and is not affiliated with, endorsed by, or sponsored by Marvis or Tencent. This repository does not include Marvis binaries, proprietary assets, or reverse-engineered source code. Users are responsible for complying with Marvis and third-party provider terms.

## Requirements

- Windows
- PowerShell 5+ or PowerShell 7+
- Python 3.12+
- Node.js 18+
- Tencent Marvis desktop app
- An OpenAI-compatible API endpoint

## Install

```powershell
python -m pip install -e .[dev]
npm install
```

## Configure Provider

Set the environment variable that will hold your provider API key:

```powershell
[Environment]::SetEnvironmentVariable('MARVIS_THIRD_PARTY_API_KEY', '<your api key>', 'User')
```

If you prefer to do it manually, open Windows Environment Variables and create a user variable:

- Name: `MARVIS_THIRD_PARTY_API_KEY`
- Value: your API key

Create your local provider config:

```powershell
Copy-Item .\config\third-party-api.example.toml .\config\third-party-api.local.toml
notepad .\config\third-party-api.local.toml
```

Before use, make sure the example config has been copied or renamed from `config\third-party-api.example.toml` to `config\third-party-api.local.toml`.

Example:

```toml
[provider]
base_url = "https://api.example.com/v1"
model = "your-model-name"
api_key_env = "MARVIS_THIRD_PARTY_API_KEY"
timeout_seconds = 120
```

If Marvis is installed outside the default locations, set:

```powershell
[Environment]::SetEnvironmentVariable('MARVIS_INSTALL_ROOT', 'D:\Path\To\Tencent\Marvis', 'User')
```

## Start From The Launcher

Use: start Marvis and route model requests to a third-party OpenAI-compatible service for testing, debugging, and validation; do not use it for anything illegal, unauthorized, or outside the provider's terms.

Double-click this file from the repository root:

```text
Marvis本地外壳启动器.bat
```

Follow these steps:

1. Make sure Marvis is fully closed and your API key and `config\third-party-api.local.toml` are ready.
2. Double-click `Marvis本地外壳启动器.bat`.
3. Enter `1` to start.
4. Enter `2` to check status.
5. Enter `3` when you are done.
6. When you need to restore the official Agent, enter `3` first, then choose `4`.

Menu options:

- `1. 启动`: start the adapter, install or update the Agent wrapper, and launch Marvis.
- `2. 查看状态`: show adapter, wrapper, and Agent status.
- `3. 停止`: stop the processes started by the launcher.
- `4. 还原官方 Agent`: restore the official `MarvisAgent.exe`.
- `5. 退出`: close the launcher.

Note: do not start or restore while Marvis is still running. Before restoring the official Agent, stop everything started by the launcher first.

## Command Line

Start the full wrapper flow:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-marvis-wrapper-shell.ps1
```

Start and run the local canary:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-marvis-wrapper-shell.ps1 -RunCanary
```

Show status:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\get-marvis-wrapper-shell-status.ps1
```

Stop the wrapper flow and adapter:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-marvis-wrapper-shell.ps1 -StopAdapter -Force
```

Restore the official Agent:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-marvis-agent-wrapper.ps1
```

Run only the adapter:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-model-adapter.ps1
```

## Verify The Route

After starting, open PowerShell in the repository root and run:

```powershell
node .\scripts\test-marvis-third-party-canary.js --port 6161
```

It sends `MARVIS_THIRD_PARTY_PING`. If `SUMMARY` shows `ok: true` and `actualText` is `成功`, the check passed.

For a simple live smoke test:

```powershell
node .\scripts\smoke-marvis-agent.js --port 6161 --mode simple
```

Live smoke tests may call your configured provider.

## Common Errors

### Launcher starts but does not respond

Close the launcher script, open the Tencent Marvis desktop app once, fully exit it, then run the launcher again.

### `Local OpenAI adapter did not become healthy on 127.0.0.1:19080`

This means the launcher could not get a healthy response from `http://127.0.0.1:19080/health`. Check the adapter stderr first:

```powershell
Get-Content .\captures\local-model-adapter\local-model-adapter-err.log -Tail 80
```

If the log contains an error like `unrecognized arguments: - git ...\config\third-party-api.local.toml`, the workspace path likely contains spaces, for example `D:\idea - git test`. PowerShell can split those paths while starting the Python adapter, so the adapter exits before binding `19080` and the wrapper flow reports a health-check failure. Move the repository to a path without spaces, such as `D:\idea-test`, then start it again.

### Restore fails with `Cannot create a file when that file already exists.`

This usually means `MarvisAgent.exe` still exists when the restore script tries to move `MarvisAgent.real.exe` back to `MarvisAgent.exe`. The common cause is that Marvis or one of its Agent processes is still running, so the current wrapper `MarvisAgent.exe` was not removed.

Fully exit Marvis, then check for remaining processes:

```powershell
Get-Process -Name "Marvis*" -ErrorAction SilentlyContinue
```

After the processes are gone, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-marvis-agent-wrapper.ps1
```

`No local model adapter PID file found ... Nothing to stop.` is not the restore failure. It only means there was no adapter PID record to stop.

## Project Layout

```text
config/   Provider config template.
docs/     Architecture and troubleshooting notes.
scripts/  Launch, status, restore, and smoke scripts.
src/      Python adapter, wrapper helpers, capture tools, and CLI.
tests/    Unit tests.
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Development

```powershell
python -m pytest
```
