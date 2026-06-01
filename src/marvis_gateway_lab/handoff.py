from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGE_TYPE = "sanitized-marvis-gateway-handoff"
SAFE_ARTIFACT_NAMES = {"summary.json", "frames.safe.ndjson"}
UNSAFE_TEXT = {
    "payload_base64": "<dropped-field>",
    "RELAY-CAPTURE-TEST-001": "<redacted-test-token>",
    "secret-token": "<redacted-token>",
    "gateway-relay.pid.json": "<runtime-pid-file>",
    "gateway-relay.stop": "<runtime-stop-file>",
}


def export_handoff_package(
    sanitized_dir: str | Path,
    output_dir: str | Path,
    runtime_status_path: str | Path | None = None,
    latest_report: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    sanitized_root = Path(sanitized_dir)
    destination = Path(output_dir)
    if not sanitized_root.exists():
        raise FileNotFoundError(f"sanitized_dir does not exist: {sanitized_root}")
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"output_dir already exists: {destination}")
        shutil.rmtree(destination)

    destination.mkdir(parents=True)
    sessions = _copy_safe_sessions(sanitized_root, destination)
    runtime_example = _runtime_status_example(runtime_status_path)
    _write_json(destination / "state" / "runtime-status.example.json", runtime_example)
    _write_text(destination / "README.md", _readme(sessions))
    _write_text(destination / "commands.md", _commands())
    _write_text(destination / "redaction-report.md", _redaction_report())
    _write_text(destination / "docs" / "handoff.md", _handoff_doc(sessions))
    _write_text(
        destination / "docs" / "protocol-summary.md",
        _protocol_summary(sanitized_root, sessions, latest_report),
    )

    manifest = _manifest(destination, sessions)
    _write_json(destination / "manifest.json", manifest)
    manifest["files"] = _file_entries(destination)
    _write_json(destination / "manifest.json", manifest)
    return manifest


def _copy_safe_sessions(sanitized_root: Path, destination: Path) -> list[str]:
    sessions_root = _sessions_root(sanitized_root)
    sessions: list[str] = []
    for session_dir in sorted(path for path in sessions_root.iterdir() if path.is_dir()):
        safe_files = [path for path in session_dir.iterdir() if path.name in SAFE_ARTIFACT_NAMES]
        if not safe_files:
            continue
        sessions.append(session_dir.name)
        target_dir = destination / "captures" / "sanitized" / session_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for safe_file in safe_files:
            shutil.copy2(safe_file, target_dir / safe_file.name)
    return sessions


def _sessions_root(sanitized_root: Path) -> Path:
    nested_root = sanitized_root / "captures" / "sanitized"
    if nested_root.exists():
        return nested_root
    return sanitized_root


def _runtime_status_example(runtime_status_path: str | Path | None) -> dict[str, Any]:
    if runtime_status_path is None:
        return {
            "active": False,
            "listen": "127.0.0.1:<listen-port>",
            "upstream": "ws://<upstream-host>:<upstream-port>",
        }
    data = json.loads(Path(runtime_status_path).read_text(encoding="utf-8"))
    return _sanitize_runtime_value(data)


def _sanitize_runtime_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            key_lower = key.lower()
            if key_lower == "pid" or key_lower.endswith("_pid") or "pid_file" in key_lower:
                continue
            safe[key] = _sanitize_runtime_value(nested)
        return safe
    if isinstance(value, list):
        return [_sanitize_runtime_value(item) for item in value]
    if isinstance(value, str):
        if "\\" in value or "/" in value:
            return _path_placeholder(value)
        return _scrub_text(value)
    return value


def _path_placeholder(value: str) -> str:
    lowered = value.lower()
    if "stop" in lowered:
        return "<runtime-stop-file>"
    if "capture" in lowered:
        return "<captures-dir>"
    if "upstream" in lowered or value.startswith("ws://") or value.startswith("wss://"):
        return "ws://<upstream-host>:<upstream-port>"
    return "<path>"


def _manifest(destination: Path, sessions: list[str]) -> dict[str, Any]:
    return {
        "package_type": PACKAGE_TYPE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"sanitized_captures": "<sanitized-dir>"},
        "sessions": sessions,
        "safety": {
            "raw_payload_included": False,
            "raw_captures_included": False,
            "runtime_pid_included": False,
        },
        "files": _file_entries(destination),
    }


def _file_entries(destination: Path) -> list[dict[str, str]]:
    entries = []
    for path in sorted(file for file in destination.rglob("*") if file.is_file()):
        if path.name == "manifest.json":
            continue
        entries.append(
            {
                "path": path.relative_to(destination).as_posix(),
                "sha256": _sha256(path),
            }
        )
    return entries


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readme(sessions: list[str]) -> str:
    session_text = ", ".join(sessions) if sessions else "none"
    return _scrub_text(
        "\n".join(
            [
                "# Sanitized Marvis Gateway Handoff",
                "",
                "This package contains only sanitized gateway artifacts.",
                f"Included sessions: {session_text}",
                "",
                "Use the files under captures/sanitized for offline protocol review.",
            ]
        )
    )


def _commands() -> str:
    return "\n".join(
        [
            "# Command Templates",
            "",
            "Inspect manifest:",
            "python -m json.tool manifest.json",
            "",
            "Inspect sanitized frames:",
            "Get-Content captures/sanitized/<session-id>/frames.safe.ndjson",
        ]
    )


def _redaction_report() -> str:
    return "\n".join(
        [
            "# Redaction Report",
            "",
            "Dropped field classes:",
            "- Runtime process identifiers and control-file paths",
            "- Encoded binary payload bodies",
            "- Authentication, cookie, and token-like values",
            "- Raw message, title, delta, and private content fields",
            "",
            "Only sanitized summaries and safe frame records are exported.",
        ]
    )


def _handoff_doc(sessions: list[str]) -> str:
    return "\n".join(
        [
            "# Handoff Notes",
            "",
            f"Session count: {len(sessions)}",
            "",
            "The package is safe for offline handoff because it excludes raw captures",
            "and runtime control files.",
        ]
    )


def _protocol_summary(sanitized_root: Path, sessions: list[str], latest_report: str) -> str:
    summaries = []
    sessions_root = _sessions_root(sanitized_root)
    for session in sessions:
        summary_path = sessions_root / session / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        counts = summary.get("counts", {}) if isinstance(summary, dict) else {}
        summaries.append(f"- {session}: {counts.get('frames_total', 0)} safe frames")

    report = _scrub_text(latest_report.strip())
    lines = ["# Protocol Summary", "", "Sessions:", *summaries]
    if report:
        lines.extend(["", "Latest run report:", report])
    return "\n".join(lines)


def _write_json(path: Path, data: Any) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_scrub_text(text), encoding="utf-8")


def _scrub_text(text: str) -> str:
    for unsafe, replacement in UNSAFE_TEXT.items():
        text = text.replace(unsafe, replacement)
    return text
