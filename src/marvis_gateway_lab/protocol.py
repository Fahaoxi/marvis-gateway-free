from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit


REDACTED = "<redacted>"

_SENSITIVE_KEY_PARTS = (
    "token",
    "access-token",
    "authorization",
    "cookie",
    "openid",
    "guid",
    "secret",
    "signature",
    "uskey",
)

_CONTENT_KEY_NAMES = {
    "content",
    "delta",
    "reasoning_content",
    "message",
    "messages",
    "conversations",
    "title",
}


@dataclass(frozen=True)
class MessageClassification:
    kind: str
    name: str = ""
    request_id: str | None = None


def parse_json_message(value: str | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _CONTENT_KEY_NAMES or any(
        part in normalized for part in _SENSITIVE_KEY_PARTS
    )


def redact_json(value: Any, parent_key: str = "") -> Any:
    if parent_key and _is_sensitive_key(parent_key):
        return REDACTED
    if isinstance(value, dict):
        return {key: redact_json(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value


def redact_text_preview(text: str) -> str:
    parsed = parse_json_message(text)
    if parsed is None:
        return text
    redacted = redact_json(parsed)
    return json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return REDACTED
    if not parsed.scheme or not parsed.netloc:
        return value

    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username or parsed.password:
        netloc = f"{REDACTED}@{netloc}"

    redacted = SplitResult(
        parsed.scheme,
        netloc,
        parsed.path,
        REDACTED if parsed.query else "",
        REDACTED if parsed.fragment else "",
    )
    return urlunsplit(redacted)


def _action_name(message: dict[str, Any]) -> str:
    payload = message.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("action"), str):
        return payload["action"]
    data = message.get("data")
    if isinstance(data, dict) and isinstance(data.get("action"), str):
        return data["action"]
    return ""


def classify_message(value: str | dict[str, Any]) -> MessageClassification:
    message = parse_json_message(value)
    if message is None:
        return MessageClassification(kind="invalid_json")

    event = message.get("event")
    message_type = message.get("type")
    request_id = message.get("requestId")
    request_id = request_id if isinstance(request_id, str) else None

    if message_type == "ack":
        action_name = _action_name(message)
        name = f"{event}:{action_name}" if event and action_name else str(event or "")
        return MessageClassification(kind="ack", name=name, request_id=request_id)

    if message_type == "event" and isinstance(event, str):
        return MessageClassification(kind="event", name=event, request_id=request_id)

    if event in {"gateway.action", "agent.action"}:
        return MessageClassification(
            kind=event,
            name=_action_name(message),
            request_id=request_id,
        )

    if event == "agent.run":
        return MessageClassification(
            kind="agent.run",
            name="agent.run",
            request_id=request_id,
        )

    if message_type == "error" or event == "error":
        return MessageClassification(kind="error", name=str(event or ""), request_id=request_id)

    return MessageClassification(kind="unknown", request_id=request_id)
