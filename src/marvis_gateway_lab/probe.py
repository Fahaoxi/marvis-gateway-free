from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from typing import Any

import websockets


@dataclass(frozen=True)
class GatewayAction:
    action: str
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProbeResult:
    uri: str
    connected_event: dict[str, Any] | None
    acks: list[dict[str, Any]] = field(default_factory=list)


def build_gateway_action_request(
    request_id: str,
    action: GatewayAction,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action.action}
    if action.data is not None:
        payload["data"] = action.data
    return {
        "event": "gateway.action",
        "requestId": request_id,
        "payload": payload,
    }


async def probe_gateway_actions(
    uri: str,
    actions: list[GatewayAction],
    request_prefix: str = "probe",
    timeout_seconds: float = 5,
) -> ProbeResult:
    connected_event: dict[str, Any] | None = None
    acks: list[dict[str, Any]] = []

    async with websockets.connect(
        uri,
        ping_interval=None,
        open_timeout=timeout_seconds,
        close_timeout=2,
    ) as websocket:
        first_message = await asyncio.wait_for(websocket.recv(), timeout_seconds)
        connected_event = _decode_json_message(first_message)

        for index, action in enumerate(actions, start=1):
            request_id = f"{request_prefix}-{index}"
            request = build_gateway_action_request(request_id, action)
            await websocket.send(
                json.dumps(request, ensure_ascii=False, separators=(",", ":"))
            )
            acks.append(
                await _wait_for_ack(websocket, request_id, timeout_seconds)
            )

    return ProbeResult(uri=uri, connected_event=connected_event, acks=acks)


async def _wait_for_ack(websocket, request_id: str, timeout_seconds: float) -> dict[str, Any]:
    while True:
        message = await asyncio.wait_for(websocket.recv(), timeout_seconds)
        parsed = _decode_json_message(message)
        if parsed.get("requestId") == request_id:
            return parsed


def _decode_json_message(message: str | bytes) -> dict[str, Any]:
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    parsed = json.loads(message)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object websocket message")
    return parsed
