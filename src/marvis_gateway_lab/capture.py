from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from marvis_gateway_lab.protocol import redact_text_preview, redact_url
from marvis_gateway_lab.summary import write_session_summary

MAX_TEXT_PREVIEW_CHARS = 4000

_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-device-guid",
}
_SENSITIVE_HEADER_PARTS = (
    "token",
    "signature",
    "openid",
    "access-token",
    "uskey",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _session_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for name, value in headers.items():
        normalized = name.lower()
        if normalized in _SENSITIVE_HEADER_NAMES or any(
            part in normalized for part in _SENSITIVE_HEADER_PARTS
        ):
            redacted[name] = "<redacted>"
        else:
            redacted[name] = value
    return redacted


def summarize_payload(
    payload: str | bytes,
    include_payload: bool = False,
    opcode: str | None = None,
) -> dict:
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
        preview = redact_text_preview(payload[:MAX_TEXT_PREVIEW_CHARS])
        summary = {
            "opcode": opcode or "text",
            "size": len(payload_bytes),
            "sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "text_preview": preview,
            "text_truncated": len(payload) > MAX_TEXT_PREVIEW_CHARS,
        }
        if include_payload:
            summary["payload_base64"] = base64.b64encode(payload_bytes).decode("ascii")
        return summary

    summary = {
        "opcode": opcode or "binary",
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "payload_base64": base64.b64encode(payload).decode("ascii"),
    }
    return summary


class GatewaySessionRecorder:
    connection_id: str
    session_dir: Path

    def __init__(
        self,
        captures_dir: Path,
        listen_host: str,
        listen_port: int,
        upstream_url: str,
        client_remote: str,
        client_headers: dict[str, str] | None = None,
    ) -> None:
        self.connection_id = uuid4().hex[:12]
        self.session_dir = (
            Path(captures_dir)
            / "gateway-sessions"
            / f"{_session_timestamp()}-{self.connection_id}"
        )
        self._frames_path = self.session_dir / "frames.ndjson"
        self._session_path = self.session_dir / "session.json"
        self._index_path = self.session_dir.parent / "index.ndjson"
        self.session_dir.mkdir(parents=True, exist_ok=False)

        self._session = {
            "connection_id": self.connection_id,
            "started_at": utc_now(),
            "ended_at": None,
            "listen_host": listen_host,
            "listen_port": listen_port,
            "upstream_url": redact_url(upstream_url),
            "client_remote": client_remote,
            "client_headers": redact_headers(client_headers or {}),
            "upstream_headers": None,
            "close_code": None,
            "close_reason": "",
            "error": None,
        }
        self._closed = False

        self._write_session()
        self._append_index()
        self.record_event("open", {})
        self.record_event(
            "client_handshake",
            {"client_headers": self._session["client_headers"]},
        )

    def record_event(self, event_type: str, fields: dict) -> None:
        event = {"ts": utc_now(), "type": event_type}
        event.update(fields)
        with self._frames_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def record_upstream_handshake(
        self, headers: dict[str, str] | None = None
    ) -> None:
        self._session["upstream_headers"] = redact_headers(headers or {})
        self._write_session()
        self.record_event(
            "upstream_handshake",
            {"upstream_headers": self._session["upstream_headers"]},
        )

    def record_frame(
        self,
        direction: str,
        payload: str | bytes,
        include_payload: bool = False,
        opcode: str | None = None,
        extra: dict | None = None,
    ) -> None:
        fields = {
            "direction": direction,
            **summarize_payload(payload, include_payload, opcode=opcode),
        }
        if extra:
            fields.update(extra)
        self.record_event(
            "frame",
            fields,
        )
        self._write_summary()

    def record_error(self, message: str) -> None:
        self._session["error"] = message
        self._write_session()
        self.record_event("error", {"message": message})

    def close(
        self,
        close_code: int | None = None,
        close_reason: str = "",
    ) -> None:
        if self._closed:
            return

        self._closed = True
        self._session["ended_at"] = utc_now()
        self._session["close_code"] = close_code
        self._session["close_reason"] = close_reason
        self._write_session()
        self._write_summary()
        self.record_event(
            "close",
            {"close_code": close_code, "close_reason": close_reason},
        )

    def _write_session(self) -> None:
        self._session_path.write_text(
            json.dumps(self._session, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _append_index(self) -> None:
        entry = {
            "ts": self._session["started_at"],
            "connection_id": self.connection_id,
            "session_dir": str(self.session_dir),
            "listen_host": self._session["listen_host"],
            "listen_port": self._session["listen_port"],
            "upstream_url": self._session["upstream_url"],
            "client_remote": self._session["client_remote"],
        }
        with self._index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _write_summary(self) -> None:
        try:
            write_session_summary(self.session_dir)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            self.record_event("summary_error", {"message": str(exc)})
