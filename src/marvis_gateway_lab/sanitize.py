from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from marvis_gateway_lab.protocol import (
    classify_message,
    parse_json_message,
    redact_json,
)
from marvis_gateway_lab.summary import write_session_summary


FRAME_METADATA_FIELDS = ("type", "direction", "opcode", "size", "sha256", "ts")
HEADER_REDACT_KEYS = {
    "authorization",
    "cookie",
    "host",
    "origin",
    "referer",
    "sec-websocket-key",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sanitize_headers(headers: Any) -> Any:
    if not isinstance(headers, dict):
        return headers
    sanitized = {}
    for key, value in headers.items():
        if key.lower() in HEADER_REDACT_KEYS:
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = redact_json(value, key)
    return sanitized


def _sanitize_session_metadata(
    session: dict[str, Any],
    anonymized_id: str,
) -> dict[str, Any]:
    safe = dict(session)
    safe["connection_id"] = anonymized_id
    safe["client_remote"] = "<client>"
    safe["upstream_url"] = "ws://<upstream>"
    for key in ("client_headers", "upstream_headers", "headers"):
        if key in safe:
            safe[key] = _sanitize_headers(safe[key])
    return redact_json(safe)


def _safe_text_preview(redacted_preview: Any) -> str | None:
    if redacted_preview is None:
        return None
    if isinstance(redacted_preview, (dict, list)):
        return json.dumps(redacted_preview, ensure_ascii=False, separators=(",", ":"))
    if isinstance(redacted_preview, str):
        return redacted_preview
    return json.dumps(redacted_preview, ensure_ascii=False, separators=(",", ":"))


def _sanitize_frame(frame: dict[str, Any], dropped_fields: set[str]) -> dict[str, Any]:
    if "payload_base64" in frame:
        dropped_fields.add("payload_base64")

    safe = {
        key: frame[key]
        for key in FRAME_METADATA_FIELDS
        if key in frame
    }

    text_preview = frame.get("text_preview")
    parsed = parse_json_message(text_preview) if isinstance(text_preview, str) else None
    classification = classify_message(parsed if parsed is not None else text_preview)
    safe["kind"] = classification.kind
    safe["name"] = classification.name
    safe["request_id"] = classification.request_id

    if parsed is not None:
        preview = redact_json(parsed)
    elif isinstance(text_preview, str):
        preview = "<redacted>"
    else:
        preview = None

    if preview is not None:
        safe["preview"] = preview
        safe_text = _safe_text_preview(preview)
        if safe_text is not None:
            safe["text_preview"] = safe_text

    return safe


def sanitize_session(
    source_session_dir: str | Path,
    output_session_dir: str | Path,
    anonymized_id: str = "session-001",
) -> dict[str, Any]:
    source_session_dir = Path(source_session_dir)
    output_session_dir = Path(output_session_dir)
    output_session_dir.mkdir(parents=True, exist_ok=True)

    session = _read_json(source_session_dir / "session.json")
    frames = _read_ndjson(source_session_dir / "frames.ndjson")
    dropped_fields: set[str] = set()

    safe_session = _sanitize_session_metadata(session, anonymized_id)
    safe_frames = [_sanitize_frame(frame, dropped_fields) for frame in frames]

    _write_json(output_session_dir / "session.json", safe_session)
    _write_ndjson(output_session_dir / "frames.safe.ndjson", safe_frames)
    _write_ndjson(output_session_dir / "frames.ndjson", safe_frames)
    write_session_summary(output_session_dir)

    return {
        "source_session": str(source_session_dir),
        "anonymized_id": anonymized_id,
        "frames_total": len(frames),
        "dropped_fields": sorted(dropped_fields),
        "output_session_dir": str(output_session_dir),
    }
