from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from marvis_gateway_lab.api_launcher import ApiLauncherAgentRunHandler
from marvis_gateway_lab.conversation_store import ConversationStore
from marvis_gateway_lab.explain import collect_rule_examples
from marvis_gateway_lab.handoff import export_handoff_package
from marvis_gateway_lab.interventions import (
    InterventionPlanError,
    load_intervention_plan,
    preview_interventions,
)
from marvis_gateway_lab.launcher_config import (
    ConfigError,
    LauncherConfig,
    load_launcher_config,
    load_provider_config,
)
from marvis_gateway_lab.live import LiveInterventionError, load_live_interventions
from marvis_gateway_lab.local_openai_adapter import (
    LocalOpenAIAdapterConfig,
    run_local_openai_adapter,
)
from marvis_gateway_lab.providers.openai_compatible import OpenAICompatibleProvider
from marvis_gateway_lab.protocol import redact_url
from marvis_gateway_lab.probe import GatewayAction, probe_gateway_actions
from marvis_gateway_lab.report import format_latest_run_summary
from marvis_gateway_lab.relay import GatewayRelayConfig, run_gateway_relay
from marvis_gateway_lab.rules import load_rules_config
from marvis_gateway_lab.sanitize import sanitize_session
from marvis_gateway_lab.status import RuntimeStatus, read_status, write_status
from marvis_gateway_lab.summary import build_session_summary


DEFAULT_STATUS_PATH = Path("captures/runtime-status.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marvis-gateway-lab",
        description="Transparent WebSocket relay lab for Marvis local gateway research.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    relay = subparsers.add_parser("relay", help="Run the WebSocket relay.")
    relay.add_argument("--upstream-url", required=True)
    relay.add_argument("--listen-host", default="127.0.0.1")
    relay.add_argument("--listen-port", type=int, default=10123)
    relay.add_argument("--captures-dir", type=Path, default=Path("captures"))
    relay.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    relay.add_argument("--stop-file", type=Path)
    relay.add_argument("--include-payload", action="store_true")
    relay.add_argument("--live-config", type=Path)
    relay.add_argument("--rules-config", type=Path)

    api_launcher = subparsers.add_parser(
        "api-launcher",
        help="Run the relay with local API-backed agent.run handling.",
    )
    api_launcher.add_argument("--config", required=True, type=Path)
    api_launcher.add_argument("--local-config", type=Path)
    api_launcher.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    api_launcher.add_argument("--stop-file", type=Path)

    local_adapter = subparsers.add_parser(
        "local-openai-adapter",
        help="Run a local OpenAI-compatible adapter for MarvisAgent local mode.",
    )
    local_adapter.add_argument("--config", required=True, type=Path)
    local_adapter.add_argument("--local-config", type=Path)
    local_adapter.add_argument("--listen-host", default="127.0.0.1")
    local_adapter.add_argument("--listen-port", type=int, default=19080)
    local_adapter.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    local_adapter.add_argument("--stop-file", type=Path)

    status = subparsers.add_parser("status", help="Print runtime status JSON.")
    status.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)

    latest = subparsers.add_parser(
        "latest-run-summary",
        help="Print a plain-language summary for the latest captured run.",
    )
    latest.add_argument("--captures-dir", type=Path, default=Path("captures"))

    probe = subparsers.add_parser("probe", help="Run read-only gateway action probes.")
    probe.add_argument("--uri", required=True)
    probe.add_argument("--timeout-seconds", type=float, default=5)
    probe.add_argument("--request-prefix", default="probe")
    probe.add_argument(
        "--action",
        action="append",
        default=[],
        help=(
            "Gateway action to call. May be repeated. "
            "Supported forms: action.name or action.name={json-object-data}."
        ),
    )

    sanitize = subparsers.add_parser(
        "sanitize-captures",
        help="Export sanitized copies of captured gateway sessions.",
    )
    sanitize.add_argument("--captures-dir", required=True, type=Path)
    sanitize.add_argument("--output-dir", required=True, type=Path)
    sanitize.add_argument("--session", action="append", default=[])
    sanitize.add_argument("--overwrite", action="store_true")

    handoff = subparsers.add_parser(
        "export-handoff",
        help="Build a sanitized handoff package from sanitized captures.",
    )
    handoff.add_argument("--sanitized-dir", required=True, type=Path)
    handoff.add_argument("--output-dir", required=True, type=Path)
    handoff.add_argument("--runtime-status", type=Path)
    handoff.add_argument("--captures-dir", type=Path)
    handoff.add_argument("--overwrite", action="store_true")

    rules_preview = subparsers.add_parser(
        "rules-preview",
        help="Print observe-only rule matches for a captured session.",
    )
    rules_preview.add_argument("--session-dir", required=True, type=Path)
    rules_preview.add_argument("--rules-config", type=Path)
    rules_preview.add_argument("--include-examples", action="store_true")
    rules_preview.add_argument("--example-limit", type=int, default=3)

    intervention = subparsers.add_parser(
        "intervention-preview",
        help="Preview offline block/rewrite/flag interventions for a captured session.",
    )
    intervention.add_argument("--session-dir", required=True, type=Path)
    intervention.add_argument("--plan-config", required=True, type=Path)
    intervention.add_argument("--rules-config", type=Path)
    intervention.add_argument("--example-limit", type=int, default=3)

    return parser


def _status_from_args(args: argparse.Namespace, active: bool, message: str) -> RuntimeStatus:
    return RuntimeStatus(
        mode="relay" if active else "stopped",
        active=active,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        upstream_url=redact_url(args.upstream_url),
        captures_dir=str(args.captures_dir),
        pid=os.getpid(),
        message=message,
    )


def _status_from_launcher_config(
    config: LauncherConfig,
    active: bool,
    message: str,
) -> RuntimeStatus:
    return RuntimeStatus(
        mode="api-launcher" if active else "stopped",
        active=active,
        listen_host=config.launcher.listen_host,
        listen_port=config.launcher.listen_port,
        upstream_url=redact_url(config.launcher.upstream_url),
        captures_dir=config.launcher.captures_dir,
        pid=os.getpid(),
        message=message,
    )


def _build_api_launcher_handler(
    config: LauncherConfig,
) -> ApiLauncherAgentRunHandler:
    if config.provider.type != "openai_compatible":
        raise ConfigError(f"unsupported provider.type: {config.provider.type}")

    provider = OpenAICompatibleProvider(
        base_url=config.provider.base_url,
        api_key=config.provider.api_key,
        model=config.provider.model,
        temperature=config.provider.temperature,
        timeout_seconds=config.provider.timeout_seconds,
    )
    conversation_store = ConversationStore(
        enabled=config.history.enabled,
        max_turns=config.history.max_turns,
    )
    return ApiLauncherAgentRunHandler(
        provider=provider,
        conversation_store=conversation_store,
        provider_type=config.provider.type,
        model=config.provider.model,
    )


async def _run_api_launcher_command(args: argparse.Namespace) -> int:
    launcher_config = load_launcher_config(args.config, local_config_path=args.local_config)
    handler = _build_api_launcher_handler(launcher_config)
    config = GatewayRelayConfig(
        listen_host=launcher_config.launcher.listen_host,
        listen_port=launcher_config.launcher.listen_port,
        upstream_url=launcher_config.launcher.upstream_url,
        captures_dir=Path(launcher_config.launcher.captures_dir),
        agent_run_handler=handler.handle,
    )
    write_status(
        args.status_path,
        _status_from_launcher_config(launcher_config, True, "API launcher started."),
    )
    stop_event = asyncio.Event()
    stop_watcher = (
        asyncio.create_task(_watch_stop_file(args.stop_file, stop_event))
        if args.stop_file is not None
        else None
    )

    try:
        await run_gateway_relay(config, stop_event=stop_event)
    except asyncio.CancelledError:
        write_status(
            args.status_path,
            _status_from_launcher_config(launcher_config, False, "API launcher stopped."),
        )
        raise
    except Exception as exc:
        failed = _status_from_launcher_config(
            launcher_config,
            False,
            "API launcher failed.",
        )
        failed.mode = "api-launcher"
        failed.last_error = str(exc)
        write_status(args.status_path, failed)
        raise
    finally:
        if stop_watcher is not None:
            stop_watcher.cancel()
            await asyncio.gather(stop_watcher, return_exceptions=True)

    write_status(
        args.status_path,
        _status_from_launcher_config(launcher_config, False, "API launcher stopped."),
    )
    return 0


async def _run_relay_command(args: argparse.Namespace) -> int:
    live_interventions = (
        load_live_interventions(args.live_config)
        if args.live_config is not None
        else None
    )
    live_rules = load_rules_config(args.rules_config) if args.rules_config is not None else None
    config = GatewayRelayConfig(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        upstream_url=args.upstream_url,
        captures_dir=args.captures_dir,
        include_payload=args.include_payload,
        live_interventions=live_interventions,
    )
    if live_rules is not None:
        config.live_rules = live_rules
    write_status(args.status_path, _status_from_args(args, True, "Relay started."))
    stop_event = asyncio.Event()
    stop_watcher = (
        asyncio.create_task(_watch_stop_file(args.stop_file, stop_event))
        if args.stop_file is not None
        else None
    )

    try:
        await run_gateway_relay(config, stop_event=stop_event)
    except asyncio.CancelledError:
        write_status(args.status_path, _status_from_args(args, False, "Relay stopped."))
        raise
    except Exception as exc:
        failed = _status_from_args(args, False, "Relay failed.")
        failed.mode = "relay"
        failed.last_error = str(exc)
        write_status(args.status_path, failed)
        raise
    finally:
        if stop_watcher is not None:
            stop_watcher.cancel()
            await asyncio.gather(stop_watcher, return_exceptions=True)

    write_status(args.status_path, _status_from_args(args, False, "Relay stopped."))
    return 0


async def _watch_stop_file(path: Path, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        if path.exists():
            stop_event.set()
            return
        await asyncio.sleep(0.25)


def _run_local_openai_adapter_command(args: argparse.Namespace) -> int:
    provider_config = load_provider_config(args.config, local_config_path=args.local_config)
    stop_event = threading.Event()
    adapter_config = LocalOpenAIAdapterConfig(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        upstream_base_url=provider_config.base_url,
        upstream_api_key=provider_config.api_key,
        model=provider_config.model,
        timeout_seconds=provider_config.timeout_seconds,
        status_path=args.status_path,
    )
    server = run_local_openai_adapter(adapter_config, stop_event=stop_event)
    try:
        while not stop_event.is_set():
            if args.stop_file is not None and args.stop_file.exists():
                stop_event.set()
                break
            time.sleep(0.25)
    finally:
        stop_event.set()
        server.shutdown()
        write_status(
            args.status_path,
            RuntimeStatus(
                mode="local-openai-adapter",
                active=False,
                listen_host=args.listen_host,
                listen_port=server.server_port,
                upstream_url=redact_url(provider_config.base_url),
                captures_dir=str(args.status_path.parent),
                pid=os.getpid(),
                message="Local OpenAI adapter stopped.",
            ),
        )
    return 0


def _print_status(args: argparse.Namespace) -> int:
    status = read_status(args.status_path)
    print(json.dumps(asdict(status), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _print_latest_run_summary(args: argparse.Namespace) -> int:
    print(format_latest_run_summary(args.captures_dir))
    return 0


def _parse_gateway_action(value: str) -> GatewayAction:
    if "=" not in value:
        return GatewayAction(action=value)
    action, data_text = value.split("=", 1)
    data = json.loads(data_text)
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError("action data must be a JSON object")
    return GatewayAction(action=action, data=data)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _resolve_session_names(captures_dir: Path, sessions: list[str]) -> list[str]:
    if sessions:
        return sessions

    sessions_dir = captures_dir / "gateway-sessions"
    if not sessions_dir.exists():
        return []
    return sorted(path.name for path in sessions_dir.iterdir() if path.is_dir())


def sanitize_captures(
    captures_dir: Path,
    output_dir: Path,
    sessions: list[str],
    overwrite: bool = False,
) -> dict[str, object]:
    captures_dir = Path(captures_dir)
    output_dir = Path(output_dir)
    resolved_captures_dir = captures_dir.resolve()
    resolved_output_dir = output_dir.resolve()

    if resolved_output_dir == resolved_captures_dir or _is_relative_to(
        resolved_output_dir,
        resolved_captures_dir,
    ):
        raise ValueError("output-dir must not be inside captures-dir or equal captures-dir")

    if output_dir.exists() and not overwrite:
        raise FileExistsError("output-dir already exists; pass --overwrite to reuse it")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("output-dir exists and is not a directory")

    session_manifests = []
    for index, session_name in enumerate(_resolve_session_names(captures_dir, sessions), start=1):
        anonymized_id = f"session-{index:03d}"
        source_session_dir = captures_dir / "gateway-sessions" / session_name
        output_session_dir = output_dir / "captures" / "sanitized" / anonymized_id
        session_manifest = sanitize_session(
            source_session_dir,
            output_session_dir,
            anonymized_id=anonymized_id,
        )
        session_manifest["source_session_name"] = session_name
        session_manifests.append(session_manifest)

    return {
        "captures_dir": str(captures_dir),
        "output_dir": str(output_dir),
        "sessions": session_manifests,
        "sessions_total": len(session_manifests),
    }


def _run_sanitize_captures_command(args: argparse.Namespace) -> int:
    manifest = sanitize_captures(
        args.captures_dir,
        args.output_dir,
        args.session,
        overwrite=args.overwrite,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_export_handoff_command(args: argparse.Namespace) -> int:
    latest_report = (
        format_latest_run_summary(args.captures_dir)
        if args.captures_dir is not None
        else ""
    )
    manifest = export_handoff_package(
        args.sanitized_dir,
        args.output_dir,
        runtime_status_path=args.runtime_status,
        latest_report=latest_report,
        overwrite=args.overwrite,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_rules_preview_command(args: argparse.Namespace) -> int:
    summary = build_session_summary(
        args.session_dir,
        rules_config_path=args.rules_config,
    )
    rule_summary = summary.get("rules", {})
    result = {
        "config": rule_summary.get("config", {}),
        "rules": rule_summary.get("by_id", {}),
        "session": Path(args.session_dir).name,
    }
    if args.include_examples:
        result["examples"] = collect_rule_examples(
            summary.get("flow", []),
            limit_per_rule=args.example_limit,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_intervention_preview_command(args: argparse.Namespace) -> int:
    summary = build_session_summary(
        args.session_dir,
        rules_config_path=args.rules_config,
    )
    plan_config = {
        "error": "",
        "loaded": True,
        "source": str(args.plan_config),
    }

    try:
        plans = load_intervention_plan(args.plan_config)
        preview = preview_interventions(
            summary.get("flow", []),
            plans,
            limit_per_intervention=args.example_limit,
        )
    except (OSError, InterventionPlanError) as exc:
        plan_config["loaded"] = False
        plan_config["error"] = str(exc)
        preview = {
            "summary": {
                "actions": {},
                "interventions": {},
                "matched_entries": 0,
            },
            "interventions": [],
            "limitations": [
                "Offline preview only; relay behavior and captured data are not changed.",
                "Intervention plan could not be loaded, so no interventions were simulated.",
            ],
        }

    result = {
        "interventions": preview["interventions"],
        "limitations": preview["limitations"],
        "mode": "offline-preview",
        "plan_config": plan_config,
        "rules_config": summary.get("rules", {}).get("config", {}),
        "session": Path(args.session_dir).name,
        "summary": preview["summary"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


async def _run_probe_command(args: argparse.Namespace) -> int:
    action_values = args.action or [
        "weixin.getStatus",
        "schedule.action.list",
        'message.action.list={"page":1,"page_size":20}',
    ]
    actions = [_parse_gateway_action(value) for value in action_values]
    result = await probe_gateway_actions(
        uri=args.uri,
        actions=actions,
        request_prefix=args.request_prefix,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "status":
        return _print_status(args)

    if args.command == "latest-run-summary":
        return _print_latest_run_summary(args)

    if args.command == "probe":
        return asyncio.run(_run_probe_command(args))

    if args.command == "sanitize-captures":
        return _run_sanitize_captures_command(args)

    if args.command == "export-handoff":
        return _run_export_handoff_command(args)

    if args.command == "rules-preview":
        return _run_rules_preview_command(args)

    if args.command == "intervention-preview":
        return _run_intervention_preview_command(args)

    if args.command == "relay":
        try:
            return asyncio.run(_run_relay_command(args))
        except KeyboardInterrupt:
            return 0

    if args.command == "api-launcher":
        try:
            return asyncio.run(_run_api_launcher_command(args))
        except ConfigError as exc:
            print(f"api-launcher config error: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return 0

    if args.command == "local-openai-adapter":
        try:
            return _run_local_openai_adapter_command(args)
        except ConfigError as exc:
            print(f"local-openai-adapter config error: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
