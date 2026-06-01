from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterable, Callable, Iterable
from dataclasses import dataclass
import hashlib
import inspect
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from marvis_gateway_lab.capture import GatewaySessionRecorder, redact_headers
from marvis_gateway_lab.live import (
    LiveIntervention,
    apply_live_interventions,
    collect_live_session_arms,
)
from marvis_gateway_lab.protocol import classify_message, parse_json_message
from marvis_gateway_lab.rules import DEFAULT_RULES, ObserveRule


HANDSHAKE_SEPARATOR = b"\r\n\r\n"
MAX_HANDSHAKE_BYTES = 128 * 1024


@dataclass(frozen=True)
class AgentRunContext:
    request_id: str | None
    conversation_id: str
    message: str
    raw_frame_text: str
    recorder: GatewaySessionRecorder


AgentRunHandler = Callable[[AgentRunContext], Any]


@dataclass
class GatewayRelayConfig:
    listen_host: str = "127.0.0.1"
    listen_port: int = 10123
    upstream_url: str = ""
    captures_dir: Path = Path("captures")
    include_payload: bool = False
    live_interventions: tuple[LiveIntervention, ...] | None = None
    live_rules: tuple[ObserveRule, ...] = DEFAULT_RULES
    agent_run_handler: AgentRunHandler | None = None


@dataclass
class WebSocketFrame:
    raw: bytes
    opcode: str
    payload: str | bytes
    fin: bool
    rsv1: bool
    masked: bool
    close_code: int | None = None
    close_reason: str = ""


def _parse_upstream_url(upstream_url: str) -> tuple[str, int]:
    parsed = urlparse(upstream_url)
    if parsed.scheme != "ws":
        raise ValueError("only ws:// upstream URLs are supported in this phase")
    if not parsed.hostname:
        raise ValueError("upstream URL must include a host")
    port = parsed.port or 80
    return parsed.hostname, port


def _headers_from_handshake(handshake: bytes) -> dict[str, str]:
    text = handshake.decode("iso-8859-1", errors="replace")
    headers: dict[str, str] = {}
    for line in text.split("\r\n")[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()
    return headers


async def _read_handshake(reader: asyncio.StreamReader) -> bytes:
    data = await reader.readuntil(HANDSHAKE_SEPARATOR)
    if len(data) > MAX_HANDSHAKE_BYTES:
        raise ValueError("websocket handshake exceeded maximum size")
    return data


async def _write_http_error(
    writer: asyncio.StreamWriter,
    status_code: int,
    reason: str,
) -> None:
    body = f"{status_code} {reason}\n".encode("utf-8")
    response = (
        f"HTTP/1.1 {status_code} {reason}\r\n"
        "Connection: close\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "\r\n"
    ).encode("ascii") + body
    writer.write(response)
    await writer.drain()


def _opcode_name(opcode: int) -> str:
    return {
        0x0: "continuation",
        0x1: "text",
        0x2: "binary",
        0x8: "close",
        0x9: "ping",
        0xA: "pong",
    }.get(opcode, f"opcode_{opcode}")


def _build_text_frame(payload: str, masked: bool) -> WebSocketFrame:
    payload_bytes = payload.encode("utf-8")
    first = 0x80 | 0x1
    length = len(payload_bytes)
    if length < 126:
        header = bytes([first, (0x80 if masked else 0) | length])
    elif length <= 0xFFFF:
        header = bytes([first, (0x80 if masked else 0) | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, (0x80 if masked else 0) | 127]) + length.to_bytes(8, "big")

    if masked:
        mask_key = os.urandom(4)
        encoded_payload = bytes(
            byte ^ mask_key[index % 4] for index, byte in enumerate(payload_bytes)
        )
        raw = header + mask_key + encoded_payload
    else:
        raw = header + payload_bytes

    return WebSocketFrame(
        raw=raw,
        opcode="text",
        payload=payload,
        fin=True,
        rsv1=False,
        masked=masked,
    )


async def _read_exact(reader: asyncio.StreamReader, size: int) -> bytes:
    if size == 0:
        return b""
    return await reader.readexactly(size)


async def _read_frame(reader: asyncio.StreamReader) -> WebSocketFrame:
    header = await _read_exact(reader, 2)
    first, second = header
    fin = bool(first & 0x80)
    rsv1 = bool(first & 0x40)
    opcode_value = first & 0x0F
    masked = bool(second & 0x80)
    payload_len = second & 0x7F
    extended = b""

    if payload_len == 126:
        extended = await _read_exact(reader, 2)
        payload_len = int.from_bytes(extended, "big")
    elif payload_len == 127:
        extended = await _read_exact(reader, 8)
        payload_len = int.from_bytes(extended, "big")

    mask_key = await _read_exact(reader, 4) if masked else b""
    encoded_payload = await _read_exact(reader, payload_len)
    raw = header + extended + mask_key + encoded_payload

    if masked:
        payload_bytes = bytes(
            byte ^ mask_key[index % 4] for index, byte in enumerate(encoded_payload)
        )
    else:
        payload_bytes = encoded_payload

    opcode = _opcode_name(opcode_value)
    close_code = None
    close_reason = ""
    payload: str | bytes = payload_bytes

    if opcode == "text" and not rsv1:
        payload = payload_bytes.decode("utf-8", errors="replace")
    elif opcode == "close":
        if len(payload_bytes) >= 2:
            close_code = int.from_bytes(payload_bytes[:2], "big")
            close_reason = payload_bytes[2:].decode("utf-8", errors="replace")

    return WebSocketFrame(
        raw=raw,
        opcode=opcode,
        payload=payload,
        fin=fin,
        rsv1=rsv1,
        masked=masked,
        close_code=close_code,
        close_reason=close_reason,
    )


def _record_frame(
    recorder: GatewaySessionRecorder,
    direction: str,
    frame: WebSocketFrame,
    include_payload: bool,
) -> None:
    extra = {
        "fin": frame.fin,
        "rsv1": frame.rsv1,
        "masked": frame.masked,
    }
    if frame.opcode == "close":
        extra["close_code"] = frame.close_code
        extra["close_reason"] = frame.close_reason
    if frame.opcode in {"ping", "pong", "close", "continuation"}:
        payload = frame.payload if isinstance(frame.payload, bytes) else frame.payload.encode("utf-8")
    else:
        payload = frame.payload
    recorder.record_frame(
        direction,
        payload,
        include_payload=include_payload,
        opcode=frame.opcode,
        extra=extra,
    )


def _agent_run_context(
    payload: str,
    recorder: GatewaySessionRecorder,
) -> AgentRunContext | None:
    parsed = parse_json_message(payload)
    if parsed is None:
        return None
    classification = classify_message(parsed)
    if classification.kind != "agent.run":
        return None

    request_id = classification.request_id
    frame_payload = parsed.get("payload")
    if not isinstance(frame_payload, dict):
        frame_payload = {}
    conversation_id = frame_payload.get("conversation_id")
    message = frame_payload.get("message")
    return AgentRunContext(
        request_id=request_id,
        conversation_id=conversation_id if isinstance(conversation_id, str) else "",
        message=message if isinstance(message, str) else "",
        raw_frame_text=payload,
        recorder=recorder,
    )


async def _send_agent_run_handler_events(
    handler: AgentRunHandler,
    context: AgentRunContext,
    writer: asyncio.StreamWriter,
    include_payload: bool,
) -> None:
    result = handler(context)
    if inspect.isawaitable(result):
        result = await result

    if isinstance(result, AsyncIterable):
        async for event in result:
            await _send_synthetic_agent_run_event(event, writer, context.recorder, include_payload)
        return

    if isinstance(result, (str, dict)):
        await _send_synthetic_agent_run_event(result, writer, context.recorder, include_payload)
        return

    if isinstance(result, Iterable):
        for event in result:
            await _send_synthetic_agent_run_event(event, writer, context.recorder, include_payload)


async def _send_synthetic_agent_run_event(
    event: str | dict[str, Any],
    writer: asyncio.StreamWriter,
    recorder: GatewaySessionRecorder,
    include_payload: bool,
) -> None:
    if isinstance(event, dict):
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    else:
        payload = event

    frame = _build_text_frame(payload, masked=False)
    _record_frame(recorder, "upstream_to_client", frame, include_payload)
    writer.write(frame.raw)
    await writer.drain()


def _run_finished_conversation_id(payload: str, direction: str) -> str:
    if direction != "upstream_to_client":
        return ""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict) or parsed.get("event") != "ag_ui_event":
        return ""
    data = parsed.get("data")
    if not isinstance(data, dict) or data.get("type") != "RUN_FINISHED":
        return ""
    conversation_id = data.get("conversation_id")
    return conversation_id if isinstance(conversation_id, str) else ""


def _disarm_finished_conversation(
    armed_scopes: dict[str, set[str]] | None,
    conversation_id: str,
) -> None:
    if not armed_scopes or not conversation_id:
        return
    for scopes in armed_scopes.values():
        scopes.discard(conversation_id)


async def _pipe_frames(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    recorder: GatewaySessionRecorder,
    direction: str,
    include_payload: bool,
    live_interventions: tuple[LiveIntervention, ...] | None = None,
    live_rules: tuple[ObserveRule, ...] = DEFAULT_RULES,
    armed_scopes: dict[str, set[str]] | None = None,
    agent_run_handler: AgentRunHandler | None = None,
    agent_run_client_writer: asyncio.StreamWriter | None = None,
) -> tuple[int | None, str]:
    close_code = None
    close_reason = ""
    while True:
        frame = await _read_frame(reader)
        _record_frame(recorder, direction, frame, include_payload)
        if (
            direction == "client_to_upstream"
            and agent_run_handler is not None
            and agent_run_client_writer is not None
            and frame.opcode == "text"
            and not frame.rsv1
        ):
            payload = frame.payload
            if not isinstance(payload, str):
                raise TypeError("text WebSocket frame payload must be a string")
            context = _agent_run_context(payload, recorder)
            if context is not None:
                try:
                    await _send_agent_run_handler_events(
                        agent_run_handler,
                        context,
                        agent_run_client_writer,
                        include_payload,
                    )
                except Exception as exc:
                    recorder.record_event(
                        "agent_run_handler_error",
                        {"message": "agent_run_handler failed"},
                    )
                    recorder.record_error("agent_run_handler failed")
                    raise RuntimeError("agent_run_handler failed") from exc
                continue
        if live_interventions is not None and frame.opcode == "text" and not frame.rsv1:
            payload = frame.payload
            if not isinstance(payload, str):
                raise TypeError("text WebSocket frame payload must be a string")
            finished_conversation_id = _run_finished_conversation_id(payload, direction)
            if armed_scopes is not None:
                for intervention_id, scope in collect_live_session_arms(
                    payload,
                    direction,
                    live_interventions,
                    rules=live_rules,
                ):
                    armed_scopes.setdefault(intervention_id, set()).add(scope)
            decision = apply_live_interventions(
                payload,
                direction,
                live_interventions,
                rules=live_rules,
                armed_scopes=armed_scopes,
            )
            if decision.audit is not None:
                recorder.record_event("live_intervention", decision.audit)
            _disarm_finished_conversation(armed_scopes, finished_conversation_id)
            if decision.blocked:
                continue
            if decision.forward_payload != payload:
                frame = _build_text_frame(
                    decision.forward_payload or "",
                    masked=direction == "client_to_upstream",
                )
        writer.write(frame.raw)
        await writer.drain()
        if frame.opcode == "close":
            close_code = frame.close_code
            close_reason = frame.close_reason
            return close_code, close_reason


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass


async def _handle_stream_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    config: GatewayRelayConfig,
) -> None:
    client_remote = client_writer.get_extra_info("peername")
    client_remote_text = ":".join(str(part) for part in client_remote) if client_remote else ""
    upstream_reader: asyncio.StreamReader | None = None
    upstream_writer: asyncio.StreamWriter | None = None
    recorder: GatewaySessionRecorder | None = None
    close_code: int | None = None
    close_reason = ""

    try:
        try:
            client_handshake = await _read_handshake(client_reader)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return
        client_headers = _headers_from_handshake(client_handshake)
        recorder = GatewaySessionRecorder(
            captures_dir=config.captures_dir,
            listen_host=config.listen_host,
            listen_port=config.listen_port,
            upstream_url=config.upstream_url,
            client_remote=client_remote_text,
            client_headers=client_headers,
        )

        upstream_host, upstream_port = _parse_upstream_url(config.upstream_url)
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                upstream_host,
                upstream_port,
            )
        except OSError as exc:
            recorder.record_error(f"upstream connection failed: {exc}")
            await _write_http_error(client_writer, 502, "Bad Gateway")
            return
        upstream_writer.write(client_handshake)
        await upstream_writer.drain()

        upstream_handshake = await _read_handshake(upstream_reader)
        recorder.record_upstream_handshake(_headers_from_handshake(upstream_handshake))
        recorder.record_event(
            "upstream_handshake_raw",
            {
                "sha256": hashlib.sha256(upstream_handshake).hexdigest(),
                "payload_base64": base64.b64encode(upstream_handshake).decode("ascii")
                if config.include_payload
                else "",
                "headers": redact_headers(_headers_from_handshake(upstream_handshake)),
            },
        )
        client_writer.write(upstream_handshake)
        await client_writer.drain()

        armed_scopes: dict[str, set[str]] = {}
        client_to_upstream = asyncio.create_task(
            _pipe_frames(
                client_reader,
                upstream_writer,
                recorder,
                "client_to_upstream",
                config.include_payload,
                config.live_interventions,
                config.live_rules,
                armed_scopes,
                config.agent_run_handler,
                client_writer,
            )
        )
        upstream_to_client = asyncio.create_task(
            _pipe_frames(
                upstream_reader,
                client_writer,
                recorder,
                "upstream_to_client",
                config.include_payload,
                config.live_interventions,
                config.live_rules,
                armed_scopes,
            )
        )
        done, pending = await asyncio.wait(
            {client_to_upstream, upstream_to_client},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if pending:
            more_done, pending = await asyncio.wait(pending, timeout=1.0)
            done.update(more_done)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task_close_code, task_close_reason = task.result()
            close_code = close_code or task_close_code
            close_reason = close_reason or task_close_reason
    except Exception as exc:
        if recorder is not None:
            recorder.record_error(str(exc))
        else:
            recorder = GatewaySessionRecorder(
                captures_dir=config.captures_dir,
                listen_host=config.listen_host,
                listen_port=config.listen_port,
                upstream_url=config.upstream_url,
                client_remote=client_remote_text,
                client_headers={},
            )
            recorder.record_error(str(exc))
    finally:
        if upstream_writer is not None:
            await _close_writer(upstream_writer)
        await _close_writer(client_writer)
        if recorder is not None:
            recorder.close(close_code=close_code, close_reason=close_reason)


async def run_gateway_relay(
    config: GatewayRelayConfig,
    stop_event: asyncio.Event | None = None,
) -> None:
    if not config.upstream_url:
        raise ValueError("upstream_url is required")

    _parse_upstream_url(config.upstream_url)
    if stop_event is None:
        stop_event = asyncio.Event()

    server = await asyncio.start_server(
        lambda reader, writer: _handle_stream_client(reader, writer, config),
        config.listen_host,
        config.listen_port,
    )
    try:
        await stop_event.wait()
    finally:
        server.close()
        await server.wait_closed()
