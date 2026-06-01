from __future__ import annotations

from pathlib import Path

import pytest

from marvis_gateway_lab.agent_wrapper import (
    DEFAULT_BACKUP_NAME,
    DEFAULT_LOCAL_LLM_PORT,
    DEFAULT_WORK_MODE,
    load_wrapper_config,
    resolve_real_exe_path,
    rewrite_agent_arguments,
)


def test_rewrite_agent_arguments_replaces_equals_style_work_mode_and_adds_local_port():
    rewritten = rewrite_agent_arguments(
        ["--port_file=a.ini", "--work_mode=cloud", "--user_id=tester"],
        local_llm_port=19080,
        work_mode="local",
    )

    assert rewritten == [
        "--port_file=a.ini",
        "--work_mode=local",
        "--user_id=tester",
        "--local_llm_port",
        "19080",
    ]


def test_rewrite_agent_arguments_replaces_split_style_flags():
    rewritten = rewrite_agent_arguments(
        ["--work_mode", "cloud", "--local_llm_port", "18888", "--port", "6161"],
        local_llm_port=19080,
        work_mode="local",
    )

    assert rewritten == [
        "--work_mode",
        "local",
        "--local_llm_port",
        "19080",
        "--port",
        "6161",
    ]


def test_rewrite_agent_arguments_appends_missing_flags():
    rewritten = rewrite_agent_arguments(
        ["--port", "6161"],
        local_llm_port=19080,
        work_mode="local",
    )

    assert rewritten == [
        "--port",
        "6161",
        "--work_mode",
        "local",
        "--local_llm_port",
        "19080",
    ]


def test_resolve_real_exe_path_defaults_to_backup_name():
    wrapper_path = Path(r"D:\Program Files\Tencent\Marvis\MarvisAgent\1.0.1100.151\MarvisAgent.exe")

    resolved = resolve_real_exe_path(wrapper_path)

    assert resolved == wrapper_path.with_name(DEFAULT_BACKUP_NAME)


def test_resolve_real_exe_path_rejects_same_path():
    wrapper_path = Path(r"D:\Program Files\Tencent\Marvis\MarvisAgent\1.0.1100.151\MarvisAgent.exe")

    with pytest.raises(ValueError):
        resolve_real_exe_path(wrapper_path, explicit_real_exe=wrapper_path)


def test_load_wrapper_config_uses_defaults_and_wrapper_relative_paths():
    wrapper_path = r"D:\Program Files\Tencent\Marvis\MarvisAgent\1.0.1100.151\MarvisAgent.exe"

    config = load_wrapper_config(wrapper_path, environ={})

    assert config.real_exe_path == Path(wrapper_path).resolve().with_name(DEFAULT_BACKUP_NAME)
    assert config.local_llm_port == DEFAULT_LOCAL_LLM_PORT
    assert config.work_mode == DEFAULT_WORK_MODE
    assert config.log_path == Path(wrapper_path).resolve().with_name("MarvisAgent.wrapper.log")


def test_load_wrapper_config_honors_environment_overrides():
    wrapper_path = r"D:\Program Files\Tencent\Marvis\MarvisAgent\1.0.1100.151\MarvisAgent.exe"
    env = {
        "MARVIS_AGENT_WRAPPER_REAL_EXE": r"D:\backup\MarvisAgent.real.exe",
        "MARVIS_AGENT_WRAPPER_LOCAL_LLM_PORT": "29080",
        "MARVIS_AGENT_WRAPPER_WORK_MODE": "local",
        "MARVIS_AGENT_WRAPPER_LOG": r"D:\logs\wrapper.log",
    }

    config = load_wrapper_config(wrapper_path, environ=env)

    assert config.real_exe_path == Path(env["MARVIS_AGENT_WRAPPER_REAL_EXE"]).resolve()
    assert config.local_llm_port == 29080
    assert config.work_mode == "local"
    assert config.log_path == Path(env["MARVIS_AGENT_WRAPPER_LOG"]).resolve()

