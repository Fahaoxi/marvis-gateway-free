from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from marvis_gateway_lab.protocol import (
    classify_message,
    parse_json_message,
    redact_json,
    redact_url,
)
from marvis_gateway_lab.rules import (
    DEFAULT_RULES,
    ObserveRule,
    RulesConfigError,
    load_rules_config,
    match_rules,
)


CONTROL_OPCODES = {"ping", "pong", "close", "continuation"}
LIVE_INTERVENTION_SAFE_FIELDS = (
    "ts",
    "id",
    "rule_id",
    "action",
    "direction",
    "kind",
    "name",
    "request_id",
    "blocked",
    "rewrite_applied",
    "sha256_before",
    "sha256_after",
)
LAUNCHER_EVENT_TYPES = {"launcher_agent_run", "launcher_provider_error"}
LAUNCHER_EVENT_SAFE_FIELDS = (
    "ts",
    "type",
    "request_id",
    "conversation_id",
    "provider_type",
    "model",
    "status",
    "error_type",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _session_fields(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "connection_id": session.get("connection_id"),
        "started_at": session.get("started_at"),
        "ended_at": session.get("ended_at"),
        "listen_host": session.get("listen_host"),
        "listen_port": session.get("listen_port"),
        "upstream_url": (
            redact_url(session["upstream_url"])
            if isinstance(session.get("upstream_url"), str)
            else session.get("upstream_url")
        ),
        "client_remote": session.get("client_remote"),
    }


def _count_frames(frames: list[dict[str, Any]]) -> dict[str, int]:
    frame_events = [event for event in frames if event.get("type") == "frame"]
    return {
        "frames_total": len(frame_events),
        "text_frames": sum(1 for event in frame_events if event.get("opcode") == "text"),
        "binary_frames": sum(1 for event in frame_events if event.get("opcode") == "binary"),
        "control_frames": sum(
            1 for event in frame_events if event.get("opcode") in CONTROL_OPCODES
        ),
    }


def _live_interventions_summary(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    live_events = [event for event in frames if event.get("type") == "live_intervention"]
    if not live_events:
        return None

    safe_events = [
        {field: event.get(field) for field in LIVE_INTERVENTION_SAFE_FIELDS if field in event}
        for event in live_events
    ]
    by_action = Counter(
        event["action"]
        for event in safe_events
        if isinstance(event.get("action"), str) and event["action"]
    )
    by_id = Counter(
        event["id"]
        for event in safe_events
        if isinstance(event.get("id"), str) and event["id"]
    )

    return {
        "total": len(safe_events),
        "by_action": dict(sorted(by_action.items())),
        "by_id": dict(sorted(by_id.items())),
        "blocked": sum(1 for event in safe_events if event.get("blocked") is True),
        "rewrite_applied": sum(
            1 for event in safe_events if event.get("rewrite_applied") is True
        ),
        "events": safe_events,
    }


def _launcher_events_summary(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    launcher_events = [
        event for event in frames if event.get("type") in LAUNCHER_EVENT_TYPES
    ]
    if not launcher_events:
        return None

    safe_events = [
        {field: event.get(field) for field in LAUNCHER_EVENT_SAFE_FIELDS if field in event}
        for event in launcher_events
    ]
    return {
        "total": len(safe_events),
        "events": safe_events,
    }


def _flow_entry(
    frame: dict[str, Any],
    rules: tuple[ObserveRule, ...] = DEFAULT_RULES,
) -> dict[str, Any] | None:
    if frame.get("type") != "frame" or frame.get("opcode") != "text":
        return None

    preview = frame.get("text_preview")
    if not isinstance(preview, str):
        return None

    parsed = parse_json_message(preview)
    classification = classify_message(parsed if parsed is not None else preview)
    if classification.kind in {"invalid_json", "unknown"}:
        return None

    entry = {
        "direction": frame.get("direction"),
        "kind": classification.kind,
        "name": classification.name,
        "request_id": classification.request_id,
        "size": frame.get("size"),
        "sha256": frame.get("sha256"),
        "ts": frame.get("ts"),
    }
    if parsed is not None:
        entry["preview"] = redact_json(parsed)
    entry["matched_rules"] = match_rules(entry, rules=rules)
    return entry


def _ag_ui_event_type(entry: dict[str, Any]) -> str:
    preview = entry.get("preview")
    if not isinstance(preview, dict) or preview.get("event") != "ag_ui_event":
        return ""
    data = preview.get("data")
    if not isinstance(data, dict):
        return ""
    event_type = data.get("type")
    return event_type if isinstance(event_type, str) else ""


def _preview_data(entry: dict[str, Any]) -> dict[str, Any]:
    preview = entry.get("preview")
    if not isinstance(preview, dict):
        return {}
    data = preview.get("data")
    return data if isinstance(data, dict) else {}


def _preview_payload(entry: dict[str, Any]) -> dict[str, Any]:
    preview = entry.get("preview")
    if not isinstance(preview, dict):
        return {}
    payload = preview.get("payload")
    return payload if isinstance(payload, dict) else {}


def _new_run() -> dict[str, Any]:
    return {
        "agent_run_request_id": None,
        "conversation_id": "",
        "event_counts": {},
        "first_ts": None,
        "last_ts": None,
        "reasoning_chunks": 0,
        "response_id": "",
        "status": "unknown",
        "text_chunks": 0,
        "tool_call_chunks": 0,
    }


def _touch_run_time(run: dict[str, Any], ts: Any) -> None:
    if not isinstance(ts, str) or not ts:
        return
    if run["first_ts"] is None:
        run["first_ts"] = ts
    run["last_ts"] = ts


def _run_key(conversation_id: str, response_id: str = "") -> str:
    return response_id or conversation_id


def _sorted_runs(runs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for run in runs.values():
        event_counts = run["event_counts"]
        run["event_counts"] = dict(sorted(event_counts.items()))
        result.append(run)
    return sorted(result, key=lambda item: item.get("first_ts") or "")


def _build_runs(flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    pending_by_request_id: dict[str, str] = {}

    for entry in flow:
        if entry["kind"] == "agent.run" and entry["direction"] == "client_to_upstream":
            payload = _preview_payload(entry)
            conversation_id = payload.get("conversation_id")
            if not isinstance(conversation_id, str) or not conversation_id:
                continue
            key = _run_key(conversation_id)
            run = runs.setdefault(key, _new_run())
            run["agent_run_request_id"] = entry.get("request_id")
            run["conversation_id"] = conversation_id
            _touch_run_time(run, entry.get("ts"))
            request_id = entry.get("request_id")
            if isinstance(request_id, str):
                pending_by_request_id[request_id] = key
            continue

        if entry["kind"] == "ack" and entry["name"] == "agent.run":
            data = _preview_data(entry)
            request_id = entry.get("request_id")
            old_key = pending_by_request_id.get(request_id) if isinstance(request_id, str) else None
            conversation_id = data.get("conversation_id")
            response_id = data.get("response_id")
            if not isinstance(conversation_id, str) or not isinstance(response_id, str):
                continue
            new_key = _run_key(conversation_id, response_id)
            run = runs.pop(old_key, _new_run()) if old_key else _new_run()
            run["conversation_id"] = conversation_id
            run["response_id"] = response_id
            if run["agent_run_request_id"] is None:
                run["agent_run_request_id"] = request_id
            _touch_run_time(run, entry.get("ts"))
            runs[new_key] = run
            if isinstance(request_id, str):
                pending_by_request_id[request_id] = new_key
            continue

        if entry.get("name") != "ag_ui_event":
            continue

        data = _preview_data(entry)
        conversation_id = data.get("conversation_id")
        response_id = data.get("response_id")
        event_type = data.get("type")
        if not isinstance(conversation_id, str) or not isinstance(event_type, str):
            continue
        response_id = response_id if isinstance(response_id, str) else ""
        key = _run_key(conversation_id, response_id)
        run = runs.setdefault(key, _new_run())
        run["conversation_id"] = conversation_id
        if response_id:
            run["response_id"] = response_id
        event_counts = run["event_counts"]
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type == "REASONING_CONTENT":
            run["reasoning_chunks"] += 1
        elif event_type == "TEXT_MESSAGE_CONTENT":
            run["text_chunks"] += 1
        elif event_type.startswith("TOOL_CALL"):
            run["tool_call_chunks"] += 1
        if event_type == "RUN_FINISHED":
            run["status"] = "finished"
        elif event_type == "RUN_ERROR":
            run["status"] = "error"
        elif run["status"] == "unknown":
            run["status"] = "running"
        _touch_run_time(run, entry.get("ts"))

    return _sorted_runs(runs)


def _load_rules_for_summary(
    rules_config_path: str | Path | None,
) -> tuple[tuple[ObserveRule, ...], dict[str, Any]]:
    if rules_config_path is None:
        return DEFAULT_RULES, {
            "error": "",
            "loaded": True,
            "source": "builtin",
        }

    source = str(Path(rules_config_path))
    try:
        return load_rules_config(rules_config_path), {
            "error": "",
            "loaded": True,
            "source": source,
        }
    except (OSError, RulesConfigError) as exc:
        return DEFAULT_RULES, {
            "error": str(exc),
            "loaded": False,
            "source": source,
        }


def build_session_summary(
    session_dir: str | Path,
    rules_config_path: str | Path | None = None,
) -> dict[str, Any]:
    session_path = Path(session_dir) / "session.json"
    frames_path = Path(session_dir) / "frames.ndjson"
    session = _read_json(session_path)
    frames = _read_ndjson(frames_path)
    rules, rules_config = _load_rules_for_summary(rules_config_path)
    flow = [
        entry
        for entry in (_flow_entry(frame, rules=rules) for frame in frames)
        if entry is not None
    ]
    by_kind = Counter(entry["kind"] for entry in flow)
    by_name = Counter(entry["name"] for entry in flow if entry["name"])
    by_rule_id = Counter(
        rule_id
        for entry in flow
        for rule_id in entry.get("matched_rules", [])
    )
    ag_ui_event_by_type = Counter(
        event_type
        for event_type in (_ag_ui_event_type(entry) for entry in flow)
        if event_type
    )

    summary = {
        "session": _session_fields(session),
        "counts": _count_frames(frames),
        "protocol": {
            "ag_ui_event_by_type": dict(sorted(ag_ui_event_by_type.items())),
            "by_kind": dict(sorted(by_kind.items())),
            "by_name": dict(sorted(by_name.items())),
        },
        "rules": {
            "by_id": dict(sorted(by_rule_id.items())),
            "config": rules_config,
        },
        "runs": _build_runs(flow),
        "flow": flow,
    }
    live_interventions = _live_interventions_summary(frames)
    if live_interventions is not None:
        summary["live_interventions"] = live_interventions
    launcher_events = _launcher_events_summary(frames)
    if launcher_events is not None:
        summary["launcher_events"] = launcher_events
    return summary


def write_session_summary(
    session_dir: str | Path,
    rules_config_path: str | Path | None = None,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    summary = build_session_summary(session_dir, rules_config_path=rules_config_path)
    (session_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary
