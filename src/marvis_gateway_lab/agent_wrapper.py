from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_BACKUP_NAME = "MarvisAgent.real.exe"
DEFAULT_LOCAL_LLM_PORT = 19080
DEFAULT_WORK_MODE = "local"
DEFAULT_LOG_NAME = "MarvisAgent.wrapper.log"


@dataclass(frozen=True)
class WrapperConfig:
    real_exe_path: Path
    local_llm_port: int = DEFAULT_LOCAL_LLM_PORT
    work_mode: str = DEFAULT_WORK_MODE
    log_path: Path | None = None


def resolve_real_exe_path(
    wrapper_exe_path: str | Path,
    explicit_real_exe: str | Path | None = None,
    backup_name: str = DEFAULT_BACKUP_NAME,
) -> Path:
    wrapper_path = Path(wrapper_exe_path).resolve()
    if explicit_real_exe:
        real_path = Path(explicit_real_exe).resolve()
    else:
        real_path = wrapper_path.with_name(backup_name)

    if real_path == wrapper_path:
        raise ValueError("real exe path must be different from wrapper exe path")
    return real_path


def rewrite_agent_arguments(
    arguments: Iterable[str],
    *,
    local_llm_port: int,
    work_mode: str,
) -> list[str]:
    rewritten: list[str] = []
    args = list(arguments)
    i = 0
    work_mode_seen = False
    local_llm_port_seen = False

    while i < len(args):
        argument = args[i]

        if argument == "--work_mode":
            rewritten.extend([argument, work_mode])
            work_mode_seen = True
            i += 2
            continue

        if argument.startswith("--work_mode="):
            rewritten.append(f"--work_mode={work_mode}")
            work_mode_seen = True
            i += 1
            continue

        if argument == "--local_llm_port":
            rewritten.extend([argument, str(local_llm_port)])
            local_llm_port_seen = True
            i += 2
            continue

        if argument.startswith("--local_llm_port="):
            rewritten.append(f"--local_llm_port={local_llm_port}")
            local_llm_port_seen = True
            i += 1
            continue

        rewritten.append(argument)
        i += 1

    if not work_mode_seen:
        rewritten.extend(["--work_mode", work_mode])
    if not local_llm_port_seen:
        rewritten.extend(["--local_llm_port", str(local_llm_port)])

    return rewritten


def load_wrapper_config(
    argv0: str,
    environ: dict[str, str] | None = None,
) -> WrapperConfig:
    env = environ or os.environ
    wrapper_path = Path(argv0).resolve()
    real_exe_path = resolve_real_exe_path(
        wrapper_path,
        explicit_real_exe=env.get("MARVIS_AGENT_WRAPPER_REAL_EXE"),
    )
    local_llm_port = int(
        env.get("MARVIS_AGENT_WRAPPER_LOCAL_LLM_PORT", str(DEFAULT_LOCAL_LLM_PORT))
    )
    work_mode = env.get("MARVIS_AGENT_WRAPPER_WORK_MODE", DEFAULT_WORK_MODE)
    log_path_text = env.get("MARVIS_AGENT_WRAPPER_LOG")
    log_path = Path(log_path_text).resolve() if log_path_text else wrapper_path.with_name(DEFAULT_LOG_NAME)
    return WrapperConfig(
        real_exe_path=real_exe_path,
        local_llm_port=local_llm_port,
        work_mode=work_mode,
        log_path=log_path,
    )


def append_wrapper_log(log_path: Path | None, message: str) -> None:
    if log_path is None:
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def launch_real_agent(
    config: WrapperConfig,
    arguments: Iterable[str],
) -> int:
    if not config.real_exe_path.exists():
        raise FileNotFoundError(f"real agent executable not found: {config.real_exe_path}")

    rewritten_args = rewrite_agent_arguments(
        arguments,
        local_llm_port=config.local_llm_port,
        work_mode=config.work_mode,
    )
    command = [str(config.real_exe_path), *rewritten_args]
    append_wrapper_log(
        config.log_path,
        "launch " + subprocess.list2cmdline(command),
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=str(config.real_exe_path.parent),
        creationflags=creationflags,
    )
    return_code = process.wait()
    append_wrapper_log(config.log_path, f"exit code={return_code}")
    return return_code


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    config = load_wrapper_config(sys.argv[0])
    try:
        return launch_real_agent(config, args)
    except Exception as exc:  # pragma: no cover - defensive logging path
        append_wrapper_log(config.log_path, f"error {exc!r}")
        print(f"MarvisAgent wrapper failed: {exc}", file=sys.stderr)
        return 1

