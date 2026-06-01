from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path


def wait_for_listening_port(
    host: str,
    port: int,
    timeout_seconds: float = 10.0,
) -> bool:
    """Return True once a TCP listener accepts connections on host:port."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def resolve_pythonw(python_exe: str) -> str:
    """Prefer sibling pythonw.exe on Windows when it exists."""
    if os.name != "nt":
        return python_exe

    python_path = Path(python_exe)
    if python_path.name.lower() != "python.exe":
        return python_exe

    pythonw_path = python_path.with_name("pythonw.exe")
    if pythonw_path.exists():
        return str(pythonw_path)
    return python_exe


def write_pid_file(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid}), encoding="utf-8")
