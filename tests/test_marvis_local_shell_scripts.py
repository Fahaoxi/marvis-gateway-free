import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BAT_LAUNCHER = REPO_ROOT / "Marvis本地外壳启动器.bat"


def parse_powershell_script(path: Path) -> None:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"[scriptblock]::Create((Get-Content -Raw {str(path)!r})) | Out-Null",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def test_local_shell_scripts_parse_as_powershell():
    for script_name in (
        "start-local-model-adapter.ps1",
        "stop-local-model-adapter.ps1",
        "get-local-model-adapter-status.ps1",
        "start-marvis-local-shell.ps1",
        "stop-marvis-local-shell.ps1",
        "get-marvis-local-shell-status.ps1",
        "start-marvis-wrapper-shell.ps1",
        "stop-marvis-wrapper-shell.ps1",
        "get-marvis-wrapper-shell-status.ps1",
        "install-marvis-agent-wrapper.ps1",
        "restore-marvis-agent-wrapper.ps1",
        "MarvisShellLauncher-User.ps1",
        "patch-marvis-ui-loading-gate.ps1",
        "restore-marvis-ui-loading-gate.ps1",
        "get-marvis-ui-patch-status.ps1",
        "MarvisPaths.ps1",
        "check-before-publish.ps1",
    ):
        parse_powershell_script(SCRIPTS_DIR / script_name)


def test_adapter_script_defaults_to_idea_workspace_and_provider_config():
    script = read_script("start-local-model-adapter.ps1")

    assert "Split-Path -Parent $PSScriptRoot" in script
    assert "config\\third-party-api.local.toml" in script
    assert "Import-ProviderEnvironmentVariables -Config $Config" in script
    assert 'api_key_env' in script
    assert 'GetEnvironmentVariable($name, "User")' in script
    assert "captures\\local-model-adapter" in script
    assert "ListenPort = 19080" in script
    assert "D:\\Practice\\idea2" not in script
    assert "config\\launcher.toml" not in script
    assert "raw_api_key" not in script


def test_marvis_local_shell_launcher_uses_local_mode_and_file_lock():
    script = read_script("start-marvis-local-shell.ps1")

    assert "--work_mode" in script
    assert '"local"' in script
    assert "--local_llm_port" in script
    assert "get-local-model-adapter-status.ps1" in script
    assert "& powershell -NoProfile -ExecutionPolicy Bypass -File $adapterStatusScript" in script
    assert "agent.lock" in script
    assert "New-Item -ItemType File -Force -Path $agentLockFile" in script
    assert "captures\\marvis-local-shell" in script
    assert "third-party-api.local.toml" in script
    assert "D:\\Practice\\idea2" not in script


def test_stop_local_shell_only_uses_recorded_pids():
    script = read_script("stop-marvis-local-shell.ps1")

    assert "marvis-local-shell-current.json" in script
    assert "agent_pid" in script
    assert 'Add-Member -NotePropertyName "stopped_at"' in script
    assert "$adapterStopArgs += \"-Force\"" in script
    assert "stop-local-model-adapter.ps1\") -Workspace $Workspace -Force:$Force" not in script
    assert "MarvisAssistant" not in script
    assert "MarvisSvr" not in script


def test_user_bat_launcher_is_simple_menu_and_calls_project_scripts():
    raw = BAT_LAUNCHER.read_bytes()
    text = raw.decode("ascii")

    assert "@echo off" in text
    assert "MarvisShellLauncher-User.ps1" in text
    assert "powershell" in text
    assert all(byte < 128 for byte in raw)
    assert "D:\\Practice\\idea2" not in text


def test_ui_loading_gate_patch_scripts_are_reversible_and_self_elevating():
    patch_script = read_script("patch-marvis-ui-loading-gate.ps1")
    restore_script = read_script("restore-marvis-ui-loading-gate.ps1")
    status_script = read_script("get-marvis-ui-patch-status.ps1")

    assert "Start-Process" in patch_script
    assert "-Verb RunAs" in patch_script
    assert "Copy-Item -LiteralPath $BundlePath -Destination $backupPath" in patch_script
    assert "PatchedSnippetBase64" in patch_script
    assert "PatchedSendFlowGateBase64" in patch_script
    assert "LazyChunkPath" in patch_script
    assert "index-B3r57gBB.js" in patch_script
    assert "PatchedLazyLoadingStateBase64" in patch_script
    assert "PatchedLazyLoadingToastBase64" in patch_script
    assert '"role" = "main_bundle"' in patch_script
    assert '"role" = "lazy_chunk"' in patch_script
    assert "files = @(" in patch_script
    assert "Convert-FromBase64Utf8 $PatchedSnippetBase64" in patch_script
    assert "Convert-FromBase64Utf8 $PatchedSendFlowGateBase64" in patch_script
    assert "latest-patch.json" in patch_script

    assert "Start-Process" in restore_script
    assert "-Verb RunAs" in restore_script
    assert "foreach ($file in $filesToRestore)" in restore_script
    assert "Copy-Item -LiteralPath $file.backup_path -Destination $file.path" in restore_script
    assert "$manifest.files" in restore_script
    assert "Remove-Item -LiteralPath $manifestPath" in restore_script

    assert "original_snippet_present" in status_script
    assert "patched_snippet_present" in status_script
    assert "patched_sendflow_gate_present" in status_script
    assert "lazy_chunk_path" in status_script
    assert "patched_lazy_loading_state_present" in status_script
    assert "patched_lazy_loading_toast_present" in status_script
    assert "latest-patch.json" in status_script


def test_user_launcher_exposes_only_core_menu_items():
    launcher = read_script("MarvisShellLauncher-User.ps1")

    assert "start-marvis-wrapper-shell.ps1" in launcher
    assert "get-marvis-wrapper-shell-status.ps1" in launcher
    assert "stop-marvis-wrapper-shell.ps1" in launcher
    assert "restore-marvis-agent-wrapper.ps1" in launcher
    assert "test-marvis-third-party-canary.js" not in launcher
    assert "MARVIS_THIRD_PARTY_PING" not in launcher
    assert "暗号验证第三方 API" not in launcher
    assert "修复隐私模式加载提示" not in launcher
    assert "查看修复状态" not in launcher
    assert "恢复隐私模式修复" not in launcher
    assert "patch-marvis-ui-loading-gate.ps1" not in launcher
    assert "restore-marvis-ui-loading-gate.ps1" not in launcher
    assert "get-marvis-ui-patch-status.ps1" not in launcher
    assert "  1. 启动" in launcher
    assert "  2. 查看状态" in launcher
    assert "  3. 停止" in launcher
    assert "  4. 还原官方 Agent" in launcher
    assert "  5. 退出" in launcher
    assert 'Read-Host "请选择 1-5"' in launcher


def test_wrapper_scripts_build_and_restore_official_agent_binary():
    install_script = read_script("install-marvis-agent-wrapper.ps1")
    restore_script = read_script("restore-marvis-agent-wrapper.ps1")

    assert "MarvisPaths.ps1" in install_script
    assert "Resolve-MarvisAgentDir" in install_script
    assert "CscExe" in install_script
    assert "MarvisAgentWrapper.cs" in install_script
    assert "/target:winexe" in install_script
    assert "PyInstallerExe" in install_script
    assert "agent_wrapper_main.py" in install_script
    assert "--onefile" in install_script
    assert "MarvisAgent.real.exe" in install_script
    assert "Move-Item -LiteralPath $targetExe -Destination $backupExe" in install_script
    assert "Copy-Item -LiteralPath $outputExe -Destination $targetExe -Force" in install_script

    assert "MarvisAgent.real.exe" in restore_script
    assert "Resolve-MarvisAgentDir" in restore_script
    assert "Remove-Item -LiteralPath $targetExe -Force -ErrorAction SilentlyContinue" in restore_script
    assert "Move-Item -LiteralPath $backupExe -Destination $targetExe" in restore_script


def test_wrapper_shell_scripts_use_official_marvis_and_canary():
    start_script = read_script("start-marvis-wrapper-shell.ps1")
    status_script = read_script("get-marvis-wrapper-shell-status.ps1")
    stop_script = read_script("stop-marvis-wrapper-shell.ps1")
    canary_script = (SCRIPTS_DIR / "test-marvis-third-party-canary.js").read_text(encoding="utf-8")

    assert "install-marvis-agent-wrapper.ps1" in start_script
    assert "start-local-model-adapter.ps1" in start_script
    assert "Resolve-MarvisApplicationExe" in start_script
    assert "Resolve-MarvisAgentDir" in start_script
    assert "D:\\Program Files\\Tencent\\Marvis\\Application\\1.60.1000.21\\Marvis.exe" not in start_script
    assert "MARVIS_THIRD_PARTY_PING" in start_script
    assert "RunCanary" in start_script

    assert "Resolve-MarvisAgentDir" in status_script
    assert "MarvisAgent.wrapper.log" in status_script
    assert "canary_expected_response" in status_script

    assert "MarvisAgent.real" in stop_script
    assert "stop-local-model-adapter.ps1" in stop_script
    assert '$adapterStopArgs += "-Force"' in stop_script
    assert "stop-local-model-adapter.ps1\") -Workspace $Workspace -Force:$Force" not in stop_script
    assert "does not restore the wrapper" in stop_script

    assert "MARVIS_THIRD_PARTY_PING" in canary_script
    assert "成功" in canary_script


def test_marvis_paths_auto_discovers_install_dirs():
    paths_script = read_script("MarvisPaths.ps1")
    patch_script = read_script("patch-marvis-ui-loading-gate.ps1")
    status_script = read_script("get-marvis-ui-patch-status.ps1")

    assert "MARVIS_INSTALL_ROOT" in paths_script
    assert "Resolve-MarvisApplicationExe" in paths_script
    assert "Resolve-MarvisAgentDir" in paths_script
    assert "Resolve-MarvisOfflineAssetPaths" in paths_script
    assert "Sort-Object Version -Descending" in paths_script

    assert "Resolve-MarvisOfflineAssetPaths" in patch_script
    assert "Resolve-MarvisOfflineAssetPaths" in status_script
