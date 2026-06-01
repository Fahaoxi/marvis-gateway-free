from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class ObserveRule:
    id: str
    label: str
    description: str
    enabled: bool = True
    kind: str = ""
    name: str = ""
    direction: str = ""
    ag_ui_event_type: str = ""


class RulesConfigError(ValueError):
    pass


DEFAULT_RULES: tuple[ObserveRule, ...] = (
    ObserveRule(
        id="user-message",
        label="User message",
        description="Client-to-upstream agent run request.",
        kind="agent.run",
        direction="client_to_upstream",
    ),
    ObserveRule(
        id="run-start",
        label="Run start",
        description="AG-UI run started event.",
        kind="ag_ui_event",
        ag_ui_event_type="RUN_STARTED",
    ),
    ObserveRule(
        id="reasoning-stream",
        label="Reasoning stream",
        description="AG-UI reasoning content event.",
        kind="ag_ui_event",
        ag_ui_event_type="REASONING_CONTENT",
    ),
    ObserveRule(
        id="assistant-stream",
        label="Assistant stream",
        description="AG-UI assistant text content event.",
        kind="ag_ui_event",
        ag_ui_event_type="TEXT_MESSAGE_CONTENT",
    ),
    ObserveRule(
        id="run-finished",
        label="Run finished",
        description="AG-UI run finished event.",
        kind="ag_ui_event",
        ag_ui_event_type="RUN_FINISHED",
    ),
    ObserveRule(
        id="token-usage",
        label="Token usage",
        description="AG-UI usage event.",
        kind="ag_ui_event",
        ag_ui_event_type="USAGE",
    ),
    ObserveRule(
        id="run-start",
        label="Run start",
        description="AG-UI run started event.",
        name="ag_ui_event",
        ag_ui_event_type="RUN_STARTED",
    ),
    ObserveRule(
        id="reasoning-stream",
        label="Reasoning stream",
        description="AG-UI reasoning content event.",
        name="ag_ui_event",
        ag_ui_event_type="REASONING_CONTENT",
    ),
    ObserveRule(
        id="assistant-stream",
        label="Assistant stream",
        description="AG-UI assistant text content event.",
        name="ag_ui_event",
        ag_ui_event_type="TEXT_MESSAGE_CONTENT",
    ),
    ObserveRule(
        id="run-finished",
        label="Run finished",
        description="AG-UI run finished event.",
        name="ag_ui_event",
        ag_ui_event_type="RUN_FINISHED",
    ),
    ObserveRule(
        id="token-usage",
        label="Token usage",
        description="AG-UI usage event.",
        name="ag_ui_event",
        ag_ui_event_type="USAGE",
    ),
    ObserveRule(
        id="status-poll",
        label="Status poll",
        description="Gateway Weixin status polling action.",
        name="weixin.getStatus",
    ),
    ObserveRule(
        id="conversation-list",
        label="Conversation list",
        description="Agent conversations list action.",
        name="conversations.list",
    ),
    ObserveRule(
        id="conversation-create",
        label="Conversation create",
        description="Agent conversations create action.",
        name="conversations.create",
    ),
)


_RULE_KEYS = {
    "id",
    "label",
    "description",
    "enabled",
    "kind",
    "name",
    "direction",
    "ag_ui_event_type",
}

_TOP_LEVEL_KEYS = {"rules"}
_MATCHER_KEYS = ("kind", "name", "direction", "ag_ui_event_type")


def _preview_data(entry: dict[str, Any]) -> dict[str, Any]:
    preview = entry.get("preview")
    if not isinstance(preview, dict):
        return {}
    data = preview.get("data")
    return data if isinstance(data, dict) else {}


def _rule_matches(entry: dict[str, Any], rule: ObserveRule) -> bool:
    if not rule.enabled:
        return False
    if rule.kind and entry.get("kind") != rule.kind:
        return False
    if rule.name and entry.get("name") != rule.name:
        return False
    if rule.direction and entry.get("direction") != rule.direction:
        return False
    if rule.ag_ui_event_type and _preview_data(entry).get("type") != rule.ag_ui_event_type:
        return False
    return True


def match_rules(entry: dict[str, Any], rules: tuple[ObserveRule, ...] | list[ObserveRule] = DEFAULT_RULES) -> list[str]:
    """Return observe-only rule ids matched by a redacted flow entry."""
    matches: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if _rule_matches(entry, rule) and rule.id not in seen:
            matches.append(rule.id)
            seen.add(rule.id)
    return matches


def _validate_str(value: Any, key: str, index: int) -> str:
    if not isinstance(value, str):
        raise RulesConfigError(f"rules[{index}].{key} must be a string")
    return value


def _rule_from_config(raw_rule: dict[str, Any], index: int) -> ObserveRule:
    unknown_keys = set(raw_rule) - _RULE_KEYS
    if unknown_keys:
        unknown = ", ".join(sorted(unknown_keys))
        raise RulesConfigError(f"rules[{index}] has unknown key(s): {unknown}")

    rule_id = _validate_str(raw_rule.get("id"), "id", index).strip()
    if not rule_id:
        raise RulesConfigError(f"rules[{index}].id must be a non-empty string")

    label = _validate_str(raw_rule.get("label", rule_id), "label", index)
    description = _validate_str(raw_rule.get("description", ""), "description", index)

    enabled = raw_rule.get("enabled", True)
    if not isinstance(enabled, bool):
        raise RulesConfigError(f"rules[{index}].enabled must be a boolean")

    matcher_values = {
        key: _validate_str(raw_rule.get(key, ""), key, index)
        for key in _MATCHER_KEYS
    }

    return ObserveRule(
        id=rule_id,
        label=label,
        description=description,
        enabled=enabled,
        **matcher_values,
    )


def load_rules_config(path: str | Path) -> tuple[ObserveRule, ...]:
    with Path(path).open("rb") as config_file:
        config = tomllib.load(config_file)

    unknown_top_level = set(config) - _TOP_LEVEL_KEYS
    if unknown_top_level:
        unknown = ", ".join(sorted(unknown_top_level))
        raise RulesConfigError(f"unknown top-level key(s): {unknown}")

    raw_rules = config.get("rules")
    if not isinstance(raw_rules, list):
        raise RulesConfigError("top-level rules list is required")

    rules: list[ObserveRule] = []
    seen_ids: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise RulesConfigError(f"rules[{index}] must be an object")
        rule = _rule_from_config(raw_rule, index)
        if rule.id in seen_ids:
            raise RulesConfigError(f"duplicate rule id: {rule.id}")
        seen_ids.add(rule.id)
        rules.append(rule)

    return tuple(rules)
