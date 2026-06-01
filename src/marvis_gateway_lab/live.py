from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tomllib
from typing import Any

from marvis_gateway_lab.protocol import classify_message, parse_json_message, redact_json
from marvis_gateway_lab.rules import DEFAULT_RULES, ObserveRule, match_rules


ALLOWED_ACTIONS = {"flag", "block", "rewrite_text"}
ALLOWED_DIRECTIONS = {"client_to_upstream", "upstream_to_client"}
INTERVENTION_KEYS = {
    "id",
    "rule_id",
    "action",
    "enabled",
    "reason",
    "direction",
    "json_path",
    "replacement",
    "payload_contains",
    "arm_rule_id",
    "arm_direction",
    "arm_payload_contains",
    "arm_scope_json_path",
    "scope_json_path",
}
TOP_LEVEL_KEYS = {"interventions"}


class LiveInterventionError(ValueError):
    pass


@dataclass(frozen=True)
class LiveIntervention:
    id: str
    rule_id: str
    action: str
    enabled: bool = False
    reason: str = ""
    direction: str = ""
    json_path: str = ""
    replacement: str = ""
    payload_contains: str = ""
    arm_rule_id: str = ""
    arm_direction: str = ""
    arm_payload_contains: str = ""
    arm_scope_json_path: str = ""
    scope_json_path: str = ""


@dataclass(frozen=True)
class LiveDecision:
    forward_payload: str | None
    blocked: bool
    audit: dict[str, Any] | None = None


def _validate_string(raw: dict[str, Any], key: str, index: int, required: bool = False) -> str:
    if key not in raw:
        if required:
            raise LiveInterventionError(f"interventions[{index}].{key} is required")
        return ""
    value = raw[key]
    if not isinstance(value, str):
        raise LiveInterventionError(f"interventions[{index}].{key} must be a string")
    if required and not value.strip():
        raise LiveInterventionError(f"interventions[{index}].{key} must be a non-empty string")
    return value.strip() if required else value


def _intervention_from_config(raw: dict[str, Any], index: int) -> LiveIntervention:
    unknown = set(raw) - INTERVENTION_KEYS
    if unknown:
        raise LiveInterventionError(
            f"interventions[{index}] has unknown key(s): {', '.join(sorted(unknown))}"
        )

    intervention_id = _validate_string(raw, "id", index, required=True)
    rule_id = _validate_string(raw, "rule_id", index, required=True)
    action = _validate_string(raw, "action", index, required=True)
    if action not in ALLOWED_ACTIONS:
        raise LiveInterventionError(
            f"interventions[{index}].action must be one of: {', '.join(sorted(ALLOWED_ACTIONS))}"
        )

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise LiveInterventionError(f"interventions[{index}].enabled must be a boolean")

    reason = _validate_string(raw, "reason", index)
    direction = _validate_string(raw, "direction", index)
    if direction and direction not in ALLOWED_DIRECTIONS:
        raise LiveInterventionError(
            f"interventions[{index}].direction must be client_to_upstream or upstream_to_client"
        )

    json_path = _validate_string(raw, "json_path", index)
    replacement = _validate_string(raw, "replacement", index)
    payload_contains = _validate_string(raw, "payload_contains", index)
    if "payload_contains" in raw and not payload_contains:
        raise LiveInterventionError(
            f"interventions[{index}].payload_contains must be a non-empty string"
        )
    arm_rule_id = _validate_string(raw, "arm_rule_id", index)
    arm_direction = _validate_string(raw, "arm_direction", index)
    arm_payload_contains = _validate_string(raw, "arm_payload_contains", index)
    arm_scope_json_path = _validate_string(raw, "arm_scope_json_path", index)
    scope_json_path = _validate_string(raw, "scope_json_path", index)
    arm_fields = {
        "arm_rule_id": arm_rule_id,
        "arm_direction": arm_direction,
        "arm_payload_contains": arm_payload_contains,
        "arm_scope_json_path": arm_scope_json_path,
        "scope_json_path": scope_json_path,
    }
    if any(arm_fields.values()) and not all(arm_fields.values()):
        missing = ", ".join(key for key, value in arm_fields.items() if not value)
        raise LiveInterventionError(
            f"interventions[{index}] session gate requires non-empty: {missing}"
        )
    if arm_direction and arm_direction not in ALLOWED_DIRECTIONS:
        raise LiveInterventionError(
            f"interventions[{index}].arm_direction must be client_to_upstream or upstream_to_client"
        )
    if action == "rewrite_text":
        if not json_path.strip():
            raise LiveInterventionError(
                f"interventions[{index}].json_path is required for rewrite_text"
            )
        if not replacement:
            raise LiveInterventionError(
                f"interventions[{index}].replacement is required for rewrite_text"
            )

    return LiveIntervention(
        id=intervention_id,
        rule_id=rule_id,
        action=action,
        enabled=enabled,
        reason=reason,
        direction=direction,
        json_path=json_path.strip(),
        replacement=replacement,
        payload_contains=payload_contains,
        arm_rule_id=arm_rule_id,
        arm_direction=arm_direction,
        arm_payload_contains=arm_payload_contains,
        arm_scope_json_path=arm_scope_json_path,
        scope_json_path=scope_json_path,
    )


def load_live_interventions(path: str | Path) -> tuple[LiveIntervention, ...]:
    with Path(path).open("rb") as config_file:
        config = tomllib.load(config_file)

    unknown_top_level = set(config) - TOP_LEVEL_KEYS
    if unknown_top_level:
        raise LiveInterventionError(
            f"unknown top-level key(s): {', '.join(sorted(unknown_top_level))}"
        )

    raw_interventions = config.get("interventions")
    if not isinstance(raw_interventions, list):
        raise LiveInterventionError("top-level interventions list is required")
    if not raw_interventions:
        raise LiveInterventionError("top-level interventions list must be non-empty")

    interventions: list[LiveIntervention] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_interventions):
        if not isinstance(raw, dict):
            raise LiveInterventionError(f"interventions[{index}] must be an object")
        intervention = _intervention_from_config(raw, index)
        if intervention.id in seen:
            raise LiveInterventionError(f"duplicate intervention id: {intervention.id}")
        seen.add(intervention.id)
        interventions.append(intervention)

    return tuple(interventions)


def _entry_for_payload(payload: str, direction: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = parse_json_message(payload)
    if parsed is None:
        return {}, {}
    classification = classify_message(parsed)
    entry = {
        "direction": direction,
        "kind": classification.kind,
        "name": classification.name,
        "request_id": classification.request_id,
        "preview": redact_json(parsed),
    }
    return parsed, entry


def _enabled_matches(
    matched_rule_ids: list[str],
    direction: str,
    payload: str,
    parsed: dict[str, Any],
    interventions: tuple[LiveIntervention, ...] | list[LiveIntervention],
    armed_scopes: dict[str, set[str]] | None = None,
) -> list[LiveIntervention]:
    matched = set(matched_rule_ids)
    return [
        intervention
        for intervention in interventions
        if intervention.enabled
        and intervention.rule_id in matched
        and (not intervention.direction or intervention.direction == direction)
        and (not intervention.payload_contains or intervention.payload_contains in payload)
        and _session_gate_allows(intervention, parsed, armed_scopes)
    ]


def _session_gate_allows(
    intervention: LiveIntervention,
    parsed: dict[str, Any],
    armed_scopes: dict[str, set[str]] | None,
) -> bool:
    if not intervention.arm_payload_contains:
        return True
    if armed_scopes is None:
        return False
    scope = json_path_string(parsed, intervention.scope_json_path)
    return bool(scope and scope in armed_scopes.get(intervention.id, set()))


def _rewrite_text(parsed: dict[str, Any], json_path: str, replacement: str) -> str:
    current: Any = parsed
    parts = json_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise LiveInterventionError(f"rewrite_text path not found: {json_path}")
        current = current[part]
    leaf = parts[-1]
    if not isinstance(current, dict) or leaf not in current:
        raise LiveInterventionError(f"rewrite_text path not found: {json_path}")
    if not isinstance(current[leaf], str):
        raise LiveInterventionError(f"rewrite_text path is not a string: {json_path}")
    current[leaf] = replacement
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def json_path_string(parsed: dict[str, Any], json_path: str) -> str:
    current: Any = parsed
    for part in json_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    return current if isinstance(current, str) else ""


def _audit_event(
    intervention: LiveIntervention,
    entry: dict[str, Any],
    direction: str,
    before: str,
    after: str | None,
    blocked: bool,
    rewrite_applied: bool,
) -> dict[str, Any]:
    after_payload = "" if after is None else after
    return {
        "id": intervention.id,
        "rule_id": intervention.rule_id,
        "action": intervention.action,
        "direction": direction,
        "kind": entry.get("kind", ""),
        "name": entry.get("name", ""),
        "request_id": entry.get("request_id"),
        "sha256_before": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "sha256_after": hashlib.sha256(after_payload.encode("utf-8")).hexdigest(),
        "blocked": blocked,
        "rewrite_applied": rewrite_applied,
    }


def collect_live_session_arms(
    payload: str,
    direction: str,
    interventions: tuple[LiveIntervention, ...] | list[LiveIntervention],
    rules: tuple[ObserveRule, ...] | list[ObserveRule] = DEFAULT_RULES,
) -> list[tuple[str, str]]:
    parsed, entry = _entry_for_payload(payload, direction)
    if not entry:
        return []

    matched = set(match_rules(entry, rules=rules))
    arms: list[tuple[str, str]] = []
    for intervention in interventions:
        if not intervention.enabled or not intervention.arm_payload_contains:
            continue
        if intervention.arm_rule_id not in matched:
            continue
        if intervention.arm_direction != direction:
            continue
        if intervention.arm_payload_contains not in payload:
            continue
        scope = json_path_string(parsed, intervention.arm_scope_json_path)
        if scope:
            arms.append((intervention.id, scope))
    return arms


def apply_live_interventions(
    payload: str,
    direction: str,
    interventions: tuple[LiveIntervention, ...] | list[LiveIntervention],
    rules: tuple[ObserveRule, ...] | list[ObserveRule] = DEFAULT_RULES,
    armed_scopes: dict[str, set[str]] | None = None,
) -> LiveDecision:
    parsed, entry = _entry_for_payload(payload, direction)
    if not entry:
        return LiveDecision(forward_payload=payload, blocked=False)

    matched = _enabled_matches(
        match_rules(entry, rules=rules),
        direction,
        payload,
        parsed,
        interventions,
        armed_scopes,
    )
    if not matched:
        return LiveDecision(forward_payload=payload, blocked=False)
    if len(matched) > 1:
        ids = ", ".join(intervention.id for intervention in matched)
        raise LiveInterventionError(f"multiple live interventions matched one frame: {ids}")

    intervention = matched[0]
    if intervention.action == "flag":
        audit = _audit_event(intervention, entry, direction, payload, payload, False, False)
        return LiveDecision(forward_payload=payload, blocked=False, audit=audit)

    if intervention.action == "block":
        audit = _audit_event(intervention, entry, direction, payload, None, True, False)
        return LiveDecision(forward_payload=None, blocked=True, audit=audit)

    if intervention.action == "rewrite_text":
        rewritten = _rewrite_text(parsed, intervention.json_path, intervention.replacement)
        audit = _audit_event(intervention, entry, direction, payload, rewritten, False, True)
        return LiveDecision(forward_payload=rewritten, blocked=False, audit=audit)

    raise LiveInterventionError(f"unsupported live intervention action: {intervention.action}")
