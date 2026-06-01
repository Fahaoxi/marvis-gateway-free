from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ProviderDelta:
    text: str


class ProviderError(Exception):
    """Raised when provider-compatible data cannot be parsed."""
