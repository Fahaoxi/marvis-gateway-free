from __future__ import annotations

from typing import Any


SAFE_EXAMPLE_FIELDS = (
    "ts",
    "direction",
    "kind",
    "name",
    "request_id",
    "sha256",
)

KNOWN_AG_UI_EVENT_TYPES = {
    "RUN_STARTED",
    "RUN_FINISHED",
    "RUN_ERROR",
    "REASONING_START",
    "REASONING_CONTENT",
    "REASONING_END",
    "TEXT_MESSAGE_START",
    "TEXT_MESSAGE_CONTENT",
    "TEXT_MESSAGE_END",
    "TOOL_CALL_START",
    "TOOL_CALL_ARGS",
    "TOOL_CALL_END",
    "USAGE",
}

MAX_EVENT_TYPE_LENGTH = 80


def _ag_ui_event_type(entry: dict[str, Any]) -> str:
    if entry.get("name") != "ag_ui_event":
        return ""
    preview = entry.get("preview")
    if not isinstance(preview, dict):
        return ""
    data = preview.get("data")
    if not isinstance(data, dict):
        return ""
    event_type = data.get("type")
    if not isinstance(event_type, str):
        return ""
    if len(event_type) > MAX_EVENT_TYPE_LENGTH:
        return ""
    return event_type if event_type in KNOWN_AG_UI_EVENT_TYPES else ""


def _safe_example(entry: dict[str, Any]) -> dict[str, Any]:
    example = {field: entry.get(field) for field in SAFE_EXAMPLE_FIELDS}
    example["ag_ui_event_type"] = _ag_ui_event_type(entry)
    return example


def collect_rule_examples(
    flow: list[dict[str, Any]],
    limit_per_rule: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    if limit_per_rule <= 0:
        return {}

    examples: dict[str, list[dict[str, Any]]] = {}
    for entry in flow:
        matched_rules = entry.get("matched_rules")
        if not isinstance(matched_rules, list):
            continue
        for rule_id in matched_rules:
            if not isinstance(rule_id, str):
                continue
            rule_examples = examples.setdefault(rule_id, [])
            if len(rule_examples) >= limit_per_rule:
                continue
            rule_examples.append(_safe_example(entry))
    return examples
