from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from marvis_gateway_lab.protocol import redact_url
from marvis_gateway_lab.status import RuntimeStatus, write_status


CANARY_PROMPT = "MARVIS_THIRD_PARTY_PING"
CANARY_RESPONSE = "成功"


@dataclass(frozen=True)
class LocalOpenAIAdapterConfig:
    listen_host: str
    listen_port: int
    upstream_base_url: str
    upstream_api_key: str
    model: str
    timeout_seconds: float
    status_path: Path


class LocalOpenAIAdapterServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        config: LocalOpenAIAdapterConfig,
    ) -> None:
        super().__init__(server_address, LocalOpenAIAdapterHandler)
        self.config = config
        self.server_thread: threading.Thread | None = None


class LocalOpenAIAdapterHandler(BaseHTTPRequestHandler):
    server: LocalOpenAIAdapterServer

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(200, {"ok": True})
            return

        if self.path in {"/v1/models", "/models"}:
            self._write_json(200, self._model_list_payload())
            return

        if self.path == "/":
            self._write_json(
                200,
                {
                    "ok": True,
                    "mode": "local-openai-adapter",
                    "model": self.server.config.model,
                },
            )
            return

        self.send_error(404, "not found")

    def do_POST(self) -> None:
        if self.path not in {"/v1/chat/completions", "/chat/completions"}:
            self.send_error(404, "not found")
            return

        try:
            payload = self._read_json_payload()
            payload["model"] = self.server.config.model
            if is_canary_payload(payload):
                self._write_streaming_text(CANARY_RESPONSE)
                return
            self._proxy_stream(payload)
        except Exception as exc:
            self._write_json_error(502, type(exc).__name__)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_payload(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _proxy_stream(self, payload: dict[str, Any]) -> None:
        config = self.server.config
        url = config.upstream_base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.upstream_api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            self.send_response(response.status)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

    def _write_streaming_text(self, text: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        event = {
            "choices": [
                {
                    "delta": {
                        "content": text,
                    }
                }
            ]
        }
        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=True)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _write_json_error(self, status_code: int, error_type: str) -> None:
        self._write_json(status_code, {"error": error_type})

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def _model_list_payload(self) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": self.server.config.model,
                    "object": "model",
                    "owned_by": "marvis-gateway-lab",
                }
            ],
        }


def run_local_openai_adapter(
    config: LocalOpenAIAdapterConfig,
    *,
    stop_event: threading.Event | None = None,
) -> LocalOpenAIAdapterServer:
    server = LocalOpenAIAdapterServer((config.listen_host, config.listen_port), config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.server_thread = thread
    thread.start()

    actual_port = server.server_port
    write_status(
        config.status_path,
        RuntimeStatus(
            mode="local-openai-adapter",
            active=True,
            listen_host=config.listen_host,
            listen_port=actual_port,
            upstream_url=redact_url(config.upstream_base_url),
            captures_dir=str(config.status_path.parent),
            pid=os.getpid(),
            message="Local OpenAI adapter started.",
        ),
    )

    if stop_event is not None:
        watcher = threading.Thread(
            target=_shutdown_when_stopped,
            args=(server, stop_event),
            daemon=True,
        )
        watcher.start()

    return server


def is_canary_payload(payload: dict[str, Any]) -> bool:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False

    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        return extract_message_text(message.get("content")).strip() == CANARY_PROMPT

    return False


def extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _shutdown_when_stopped(
    server: LocalOpenAIAdapterServer,
    stop_event: threading.Event,
) -> None:
    stop_event.wait()
    server.shutdown()
