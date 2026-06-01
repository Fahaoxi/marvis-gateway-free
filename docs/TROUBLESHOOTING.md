# Troubleshooting

## UI Replies With "任务终止"

First check whether MarvisAgent is running on `6161` but the local adapter on `19080` is stopped:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\get-marvis-wrapper-shell-status.ps1
Invoke-RestMethod http://127.0.0.1:6161/health
Invoke-RestMethod http://127.0.0.1:19080/v1/models
```

If `6161` is healthy but `19080` fails, restart the full wrapper path:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-marvis-wrapper-shell.ps1
```

Then run the canary:

```powershell
node .\scripts\test-marvis-third-party-canary.js --port 6161
```

## Local Model Stays Loading

If Marvis keeps showing the local model loading state, first verify this project path:

```powershell
Invoke-RestMethod http://127.0.0.1:19080/v1/models
Invoke-RestMethod http://127.0.0.1:6161/health
```

If both endpoints are healthy, inspect Marvis logs for local engine startup errors. One known Windows failure mode is a stray `D:\Program` file intercepting an unquoted `D:\Program Files\...` launch path. Check it with:

```powershell
Get-Item D:\Program -ErrorAction SilentlyContinue
```

If that file exists, rename it, fully exit Marvis, and start the wrapper path again.

## Marvis Takes Back Port 6161

The official Marvis app may restart its own Agent and reclaim `127.0.0.1:6161`. A reliable startup sequence is:

1. Fully exit Marvis.
2. Stop Marvis-related processes if needed.
3. Start this project's wrapper path.
4. Confirm `http://127.0.0.1:6161/health`.
5. Start Marvis UI.

## Restoring The Official Agent

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-marvis-agent-wrapper.ps1
```

This removes the wrapper executable and moves `MarvisAgent.real.exe` back to `MarvisAgent.exe`.
