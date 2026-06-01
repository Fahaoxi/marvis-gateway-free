from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _session_dirs(captures_dir: str | Path) -> list[Path]:
    sessions_dir = Path(captures_dir) / "gateway-sessions"
    if not sessions_dir.exists():
        return []
    sessions = [path for path in sessions_dir.iterdir() if path.is_dir()]
    return sorted(sessions, key=lambda path: path.name, reverse=True)


def _read_summary(session_dir: Path) -> dict[str, Any]:
    summary_path = session_dir / "summary.json"
    if not summary_path.exists():
        return {}
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _status_text(status: str) -> str:
    return {
        "finished": "正常结束",
        "error": "出错结束",
        "running": "仍在运行",
        "unknown": "状态未知",
    }.get(status, status or "状态未知")


def _tool_text(tool_call_chunks: int) -> str:
    if tool_call_chunks <= 0:
        return "无工具调用"
    return f"工具调用相关片段 {tool_call_chunks} 段"


def _int_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def format_latest_run_summary(captures_dir: str | Path) -> str:
    sessions = _session_dirs(captures_dir)
    if not sessions:
        return "暂无 gateway session"

    latest_empty_session = sessions[0]
    latest_runs: list[Any] = []
    latest_summary: dict[str, Any] = {}
    latest_run_session = None
    for session_dir in sessions:
        summary = _read_summary(session_dir)
        runs = summary.get("runs")
        if isinstance(runs, list) and runs:
            latest_runs = runs
            latest_summary = summary
            latest_run_session = session_dir
            break

    if latest_run_session is None:
        return "\n".join(
            [
                f"最近 session: {latest_empty_session.name}",
                "- 暂未捕获到回复运行记录",
            ]
        )

    run_count = len(latest_runs)
    latest_run = latest_runs[-1] if isinstance(latest_runs[-1], dict) else {}
    reasoning_chunks = int(latest_run.get("reasoning_chunks") or 0)
    text_chunks = int(latest_run.get("text_chunks") or 0)
    tool_call_chunks = int(latest_run.get("tool_call_chunks") or 0)
    status = str(latest_run.get("status") or "unknown")

    lines = [
        f"最近 session: {latest_run_session.name}",
        f"- {run_count} 次回复",
        f"- {_status_text(status)}",
        f"- 推理 {reasoning_chunks} 段",
        f"- 回复 {text_chunks} 段",
        f"- {_tool_text(tool_call_chunks)}",
    ]
    live_interventions = latest_summary.get("live_interventions")
    if isinstance(live_interventions, dict):
        total = _int_count(live_interventions.get("total"))
        by_action = live_interventions.get("by_action")
        if total > 0 and isinstance(by_action, dict):
            action_counts = ", ".join(
                f"{action} {_int_count(count)}"
                for action, count in sorted(by_action.items())
            )
            lines.append(f"- live 干预 {total} 次: {action_counts}")
            lines.append(
                "- block "
                f"{_int_count(live_interventions.get('blocked'))} 次，rewrite "
                f"{_int_count(live_interventions.get('rewrite_applied'))} 次"
            )

    return "\n".join(lines)
