from __future__ import annotations

import time
from uuid import uuid4
from typing import Any, AsyncIterator, Protocol

from marvis_gateway_lab.conversation_store import ConversationStore
from marvis_gateway_lab.marvis_events import (
    build_agent_run_ack,
    build_run_finished,
    build_run_started,
    build_text_message_content,
    build_text_message_end,
    build_text_message_start,
)
from marvis_gateway_lab.providers.base import ChatMessage


class StreamingProvider(Protocol):
    def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[Any]:
        ...


class AgentRunContextProtocol(Protocol):
    request_id: str
    conversation_id: str
    message: str
    recorder: Any


class ApiLauncherAgentRunHandler:
    def __init__(
        self,
        *,
        provider: StreamingProvider,
        conversation_store: ConversationStore,
        provider_type: str,
        model: str,
    ) -> None:
        self.provider = provider
        self.conversation_store = conversation_store
        self.provider_type = provider_type
        self.model = model

    async def handle(
        self,
        context: AgentRunContextProtocol,
    ) -> AsyncIterator[dict[str, Any]]:
        response_id = f"resp_{uuid4().hex}"
        message_id = f"msg_{uuid4().hex}"
        seq = 1
        assistant_parts: list[str] = []
        status = "finished"

        self._record_agent_run(context, status="started")
        yield build_agent_run_ack(
            context.request_id,
            context.conversation_id,
            response_id,
        )
        yield build_run_started(
            context.conversation_id,
            response_id,
            seq=seq,
            timestamp_ms=_timestamp_ms(),
        )
        seq += 1
        yield build_text_message_start(
            context.conversation_id,
            response_id,
            message_id,
            seq=seq,
            timestamp_ms=_timestamp_ms(),
        )
        seq += 1

        messages = self.conversation_store.build_provider_messages(
            context.conversation_id,
            context.message,
        )
        try:
            async for delta in self.provider.stream_chat(messages):
                text = getattr(delta, "text", "")
                if not isinstance(text, str) or not text:
                    continue
                assistant_parts.append(text)
                yield build_text_message_content(
                    context.conversation_id,
                    response_id,
                    message_id,
                    text,
                    seq=seq,
                    timestamp_ms=_timestamp_ms(),
                )
                seq += 1
        except Exception as exc:
            status = "error"
            self._record_provider_error(context, exc)

        yield build_text_message_end(
            context.conversation_id,
            response_id,
            message_id,
            seq=seq,
            timestamp_ms=_timestamp_ms(),
        )
        seq += 1
        yield build_run_finished(
            context.conversation_id,
            response_id,
            seq=seq,
            timestamp_ms=_timestamp_ms(),
        )

        assistant_text = "".join(assistant_parts)
        if status == "finished":
            self.conversation_store.append_user(context.conversation_id, context.message)
            self.conversation_store.append_assistant(context.conversation_id, assistant_text)
        self._record_agent_run(context, status=status)

    def _record_agent_run(
        self,
        context: AgentRunContextProtocol,
        *,
        status: str,
    ) -> None:
        context.recorder.record_event(
            "launcher_agent_run",
            {
                "conversation_id": context.conversation_id,
                "model": self.model,
                "provider_type": self.provider_type,
                "request_id": context.request_id,
                "status": status,
            },
        )

    def _record_provider_error(
        self,
        context: AgentRunContextProtocol,
        exc: Exception,
    ) -> None:
        context.recorder.record_event(
            "launcher_provider_error",
            {
                "conversation_id": context.conversation_id,
                "error_type": type(exc).__name__,
                "model": self.model,
                "provider_type": self.provider_type,
                "request_id": context.request_id,
                "status": "error",
            },
        )


def _timestamp_ms() -> int:
    return int(time.time() * 1000)
