from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from marvis_gateway_lab.providers.base import ChatMessage, ProviderDelta, ProviderError


def build_chat_request(
    *, model: str, messages: list[ChatMessage], temperature: float
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": message.role, "content": message.content} for message in messages
        ],
        "temperature": temperature,
        "stream": True,
    }


def parse_sse_deltas(lines: Iterable[str]) -> Iterator[ProviderDelta]:
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            continue
        if not stripped.startswith("data:"):
            continue

        data = stripped.removeprefix("data:").strip()
        if data == "[DONE]":
            return

        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProviderError("malformed provider SSE JSON") from exc

        choices = payload.get("choices", []) if isinstance(payload, dict) else []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield ProviderDelta(text=content)


PostJsonStream = Any


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: float
    post_json_stream: PostJsonStream = None

    async def stream_chat(self, messages: list[ChatMessage]):
        post_json_stream = self.post_json_stream or _post_json_stream
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = build_chat_request(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )

        async for delta in _stream_deltas_in_thread(
            post_json_stream,
            url,
            headers,
            payload,
            self.timeout_seconds,
        ):
            yield delta


def _post_json_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Iterator[bytes]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            while True:
                line = response.readline()
                if not line:
                    break
                yield line
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"provider HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError("provider connection failed") from exc


async def _stream_deltas_in_thread(
    post_json_stream: PostJsonStream,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
):
    items: queue.Queue[ProviderDelta | Exception | None] = queue.Queue()

    def worker() -> None:
        try:
            byte_lines = post_json_stream(url, headers, payload, timeout_seconds)
            text_lines = (
                line.decode("utf-8", errors="replace")
                if isinstance(line, bytes)
                else str(line)
                for line in byte_lines
            )
            for delta in parse_sse_deltas(text_lines):
                items.put(delta)
        except ProviderError as exc:
            items.put(exc)
        except Exception as exc:
            items.put(ProviderError("provider request failed"))
        finally:
            items.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        item = await _queue_get(items)
        if item is None:
            return
        if isinstance(item, Exception):
            raise item
        yield item


async def _queue_get(items: queue.Queue[ProviderDelta | Exception | None]):
    import asyncio

    return await asyncio.to_thread(items.get)
