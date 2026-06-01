from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Iterable

from marvis_gateway_lab.explain import _ag_ui_event_type


ALLOWED_ACTIONS = {"flag", "block", "rewrite_preview"}
INTERVENTION_FIELDS = {
    "action",
    "enabled",
    "id",
    "reason",
    "replacement",
    "rule_id",
}
SAFE_ENTRY_FIELDS = (
    "ts",
    "direction",
    "kind",
    "name",
    "request_id",
    "sha256",
)


@dataclass(frozen=True)
class InterventionPlan:
    id: str
    rule_id: str
    action: str
    reason: str = ""
    enabled: bool = True
    replacement: str = ""


class InterventionPlanError(ValueError):
    pass


def _require_string(item: dict[str, Any], field: str, index: int) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise InterventionPlanError(f"intervention {index}: missing {field}")
    return value


def _optional_string(item: dict[str, Any], field: str, index: int) -> str:
    value = item.get(field, "")
    if not isinstance(value, str):
        raise InterventionPlanError(f"intervention {index}: {field} must be a string")
    return value


def _optional_bool(item: dict[str, Any], field: str, index: int) -> bool:
    value = item.get(field, True)
    if not isinstance(value, bool):
        raise InterventionPlanError(f"intervention {index}: {field} must be a boolean")
    return value


def load_intervention_plan(path: str | Path) -> tuple[InterventionPlan, ...]:
    try:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise InterventionPlanError(str(exc)) from exc

    top_level_keys = set(raw)
    if top_level_keys - {"interventions"}:
        unknown = sorted(top_level_keys - {"interventions"})[0]
        raise InterventionPlanError(f"unknown top-level key: {unknown}")

    interventions = raw.get("interventions")
    if not isinstance(interventions, list) or not interventions:
        raise InterventionPlanError("missing interventions")

    plans: list[InterventionPlan] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(interventions, start=1):
        if not isinstance(item, dict):
            raise InterventionPlanError(f"intervention {index}: must be a table")

        unknown_fields = set(item) - INTERVENTION_FIELDS
        if unknown_fields:
            unknown = sorted(unknown_fields)[0]
            raise InterventionPlanError(f"unknown intervention field: {unknown}")

        plan_id = _require_string(item, "id", index)
        if plan_id in seen_ids:
            raise InterventionPlanError(f"duplicate intervention id: {plan_id}")
        seen_ids.add(plan_id)

        rule_id = _require_string(item, "rule_id", index)
        action = _require_string(item, "action", index)
        if action not in ALLOWED_ACTIONS:
            raise InterventionPlanError(f"unsupported action: {action}")

        replacement = _optional_string(item, "replacement", index)
        if action == "rewrite_preview" and not replacement:
            raise InterventionPlanError("rewrite_preview requires replacement")

        plans.append(
            InterventionPlan(
                id=plan_id,
                rule_id=rule_id,
                action=action,
                reason=_optional_string(item, "reason", index),
                enabled=_optional_bool(item, "enabled", index),
                replacement=replacement,
            )
        )

    return tuple(plans)


def _safe_entry(entry: dict[str, Any]) -> dict[str, Any]:
    safe = {field: entry.get(field) for field in SAFE_ENTRY_FIELDS}
    safe["ag_ui_event_type"] = _ag_ui_event_type(entry)
    return safe


def _effect(plan: InterventionPlan) -> dict[str, Any]:
    effect: dict[str, Any] = {
        "would": plan.action,
        "writes_capture": False,
        "writes_payload": False,
    }
    if plan.action == "rewrite_preview":
        effect["replacement"] = plan.replacement
    return effect


def _matches_rule(entry: dict[str, Any], rule_id: str) -> bool:
    matched_rules = entry.get("matched_rules")
    return isinstance(matched_rules, list) and rule_id in matched_rules


def preview_interventions(
    flow: list[dict[str, Any]],
    plans: Iterable[InterventionPlan],
    limit_per_intervention: int = 3,
) -> dict[str, Any]:
    enabled_plans = [plan for plan in plans if plan.enabled]
    action_counts: Counter[str] = Counter()
    intervention_counts: Counter[str] = Counter()
    matched_entries = 0
    results = []

    for plan in enabled_plans:
        matches = []
        plan_match_count = 0
        for entry in flow:
            if not _matches_rule(entry, plan.rule_id):
                continue
            plan_match_count += 1
            if limit_per_intervention > 0 and len(matches) < limit_per_intervention:
                match = _safe_entry(entry)
                match["effect"] = _effect(plan)
                matches.append(match)

        matched_entries += plan_match_count
        if plan_match_count:
            action_counts[plan.action] += plan_match_count
            intervention_counts[plan.id] += plan_match_count
        results.append(
            {
                "action": plan.action,
                "id": plan.id,
                "matches": matches,
                "reason": plan.reason,
                "rule_id": plan.rule_id,
            }
        )

    return {
        "summary": {
            "actions": dict(sorted(action_counts.items())),
            "interventions": dict(sorted(intervention_counts.items())),
            "matched_entries": matched_entries,
        },
        "interventions": results,
        "limitations": [
            "Offline preview only; no relay behavior changed.",
            "Raw payloads are unavailable; rewrite_preview is synthetic.",
        ],
    }
