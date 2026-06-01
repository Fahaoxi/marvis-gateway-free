from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from marvis_gateway_lab.capture import utc_now


@dataclass
class RuntimeStatus:
    mode: str = "stopped"
    active: bool = False
    listen_host: str = "127.0.0.1"
    listen_port: int = 10123
    upstream_url: str = ""
    captures_dir: str = "captures"
    pid: int | None = None
    message: str = ""
    last_error: str = ""
    updated_at: str = ""


def write_status(path: Path, status: RuntimeStatus) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    status.updated_at = utc_now()
    path.write_text(
        json.dumps(asdict(status), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_status(path: Path) -> RuntimeStatus:
    path = Path(path)
    if not path.exists():
        return RuntimeStatus()

    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    known_fields = {field.name for field in fields(RuntimeStatus)}
    return RuntimeStatus(
        **{name: value for name, value in raw.items() if name in known_fields}
    )
