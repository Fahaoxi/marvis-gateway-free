from __future__ import annotations

from typing import Any


def build_agent_run_ack(
    request_id: str,
    conversation_id: str,
    response_id: str,
) -> dict[str, Any]:
    return {
        "event": "agent.run",
        "requestId": request_id,
        "type": "ack",
        "data": {
            "conversation_id": conversation_id,
            "ok": True,
            "response_id": response_id,
        },
    }


def _ag_ui_event(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "ag_ui_event",
        "type": "event",
        "data": data,
    }


def build_run_started(
    conversation_id: str,
    response_id: str,
    *,
    seq: int,
    timestamp_ms: int,
) -> dict[str, Any]:
    return _ag_ui_event(
        {
            "conversation_id": conversation_id,
            "response_id": response_id,
            "seq": seq,
            "threadId": conversation_id,
            "timestamp": timestamp_ms,
            "type": "RUN_STARTED",
        }
    )


def build_text_message_start(
    conversation_id: str,
    response_id: str,
    message_id: str,
    *,
    seq: int,
    timestamp_ms: int,
) -> dict[str, Any]:
    return _ag_ui_event(
        {
            "conversation_id": conversation_id,
            "messageId": message_id,
            "response_id": response_id,
            "role": "assistant",
            "seq": seq,
            "timestamp": timestamp_ms,
            "type": "TEXT_MESSAGE_START",
        }
    )


def build_text_message_content(
    conversation_id: str,
    response_id: str,
    message_id: str,
    delta: str,
    *,
    seq: int,
    timestamp_ms: int,
) -> dict[str, Any]:
    return _ag_ui_event(
        {
            "conversation_id": conversation_id,
            "delta": delta,
            "messageId": message_id,
            "response_id": response_id,
            "seq": seq,
            "timestamp": timestamp_ms,
            "type": "TEXT_MESSAGE_CONTENT",
        }
    )


def build_text_message_end(
    conversation_id: str,
    response_id: str,
    message_id: str,
    *,
    seq: int,
    timestamp_ms: int,
) -> dict[str, Any]:
    return _ag_ui_event(
        {
            "conversation_id": conversation_id,
            "messageId": message_id,
            "response_id": response_id,
            "seq": seq,
            "timestamp": timestamp_ms,
            "type": "TEXT_MESSAGE_END",
        }
    )


def build_run_finished(
    conversation_id: str,
    response_id: str,
    *,
    seq: int,
    timestamp_ms: int,
) -> dict[str, Any]:
    return _ag_ui_event(
        {
            "conversation_id": conversation_id,
            "response_id": response_id,
            "seq": seq,
            "threadId": conversation_id,
            "timestamp": timestamp_ms,
            "type": "RUN_FINISHED",
        }
    )
