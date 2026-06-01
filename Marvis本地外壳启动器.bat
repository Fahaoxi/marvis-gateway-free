@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\MarvisShellLauncher-User.ps1" -Workspace "%ROOT:~0,-1%"
endlocal
