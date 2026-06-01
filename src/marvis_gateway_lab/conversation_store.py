from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from marvis_gateway_lab.providers.base import ChatMessage


@dataclass
class ConversationStore:
    enabled: bool = True
    max_turns: int = 10
    _messages_by_conversation: dict[str, list[ChatMessage]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def append_user(self, conversation_id: str, content: str) -> None:
        self._append(conversation_id, ChatMessage(role="user", content=content))

    def append_assistant(self, conversation_id: str, content: str) -> None:
        self._append(conversation_id, ChatMessage(role="assistant", content=content))

    def build_provider_messages(
        self, conversation_id: str, current_user_content: str
    ) -> list[ChatMessage]:
        current_message = ChatMessage(role="user", content=current_user_content)
        if not self.enabled:
            return [current_message]
        history = self._history_for_provider(conversation_id, reserved_turns=1)
        return [*history, current_message]

    def _append(self, conversation_id: str, message: ChatMessage) -> None:
        if not self.enabled:
            return
        messages = self._messages_by_conversation[conversation_id]
        messages.append(message)
        self._messages_by_conversation[conversation_id] = self._trim_to_turns(messages)

    def _history_for_provider(
        self, conversation_id: str, reserved_turns: int = 0
    ) -> list[ChatMessage]:
        messages = self._messages_by_conversation.get(conversation_id, [])
        return self._trim_to_turns(messages, reserved_turns=reserved_turns)

    def _trim_to_turns(
        self, messages: list[ChatMessage], reserved_turns: int = 0
    ) -> list[ChatMessage]:
        allowed_turns = max(self.max_turns - reserved_turns, 0)
        if allowed_turns <= 0:
            return []

        turns_seen = 0
        start_index = len(messages)
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].role == "user":
                turns_seen += 1
                if turns_seen == allowed_turns:
                    start_index = index
                    break
        else:
            start_index = 0

        return list(messages[start_index:])
