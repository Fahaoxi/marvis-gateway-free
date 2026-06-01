from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when launcher configuration is invalid."""


@dataclass(frozen=True)
class LauncherSettings:
    listen_host: str
    listen_port: int
    upstream_url: str
    captures_dir: str


@dataclass(frozen=True)
class ProviderSettings:
    type: str
    base_url: str
    api_key_env: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: float


@dataclass(frozen=True)
class HistorySettings:
    enabled: bool
    max_turns: int


@dataclass(frozen=True)
class LauncherConfig:
    launcher: LauncherSettings
    provider: ProviderSettings
    history: HistorySettings


ALLOWED_FIELDS = {
    "launcher": {"listen_host", "listen_port", "upstream_url", "captures_dir"},
    "provider": {
        "type",
        "base_url",
        "api_key_env",
        "model",
        "temperature",
        "timeout_seconds",
    },
    "history": {"enabled", "max_turns"},
}

SECRET_FIELD_NAMES = {"api_key", "raw_api_key"}


def load_launcher_config(
    config_path: str | Path,
    local_config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> LauncherConfig:
    config_data = _read_config_file(Path(config_path))

    if local_config_path is not None:
        local_path = Path(local_config_path)
        if local_path.exists():
            _deep_merge(config_data, _read_config_file(local_path))

    return _build_config(config_data, os.environ if environ is None else environ)


def load_provider_config(
    config_path: str | Path,
    local_config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ProviderSettings:
    config_data = _read_config_file(Path(config_path))

    if local_config_path is not None:
        local_path = Path(local_config_path)
        if local_path.exists():
            _deep_merge(config_data, _read_config_file(local_path))

    provider = _required_section(config_data, "provider")
    return _build_provider(provider, os.environ if environ is None else environ)


def _read_config_file(path: Path) -> dict[str, dict[str, object]]:
    data = tomllib.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain TOML tables.")

    _validate_schema(data)
    return data


def _validate_schema(data: Mapping[str, object]) -> None:
    for section, values in data.items():
        if section not in ALLOWED_FIELDS:
            raise ConfigError(f"unknown section: {section}")
        if not isinstance(values, dict):
            raise ConfigError(f"section {section} must be a table")

        for field in values:
            if field in SECRET_FIELD_NAMES:
                raise ConfigError("TOML config must not contain raw api_key fields")
            if field not in ALLOWED_FIELDS[section]:
                raise ConfigError(f"unknown field: {section}.{field}")


def _deep_merge(
    base: dict[str, dict[str, object]],
    override: Mapping[str, Mapping[str, object]],
) -> None:
    for section, values in override.items():
        base.setdefault(section, {})
        base[section].update(values)


def _build_config(
    data: Mapping[str, Mapping[str, object]],
    environ: Mapping[str, str],
) -> LauncherConfig:
    launcher = _required_section(data, "launcher")
    provider = _required_section(data, "provider")
    history = _required_section(data, "history")
    provider_settings = _build_provider(provider, environ)

    max_turns = _required_int(history, "max_turns")
    if max_turns <= 0:
        raise ConfigError("history.max_turns must be a positive integer")

    return LauncherConfig(
        launcher=LauncherSettings(
            listen_host=_required_str(launcher, "listen_host"),
            listen_port=_required_int(launcher, "listen_port"),
            upstream_url=_required_str(launcher, "upstream_url"),
            captures_dir=_required_str(launcher, "captures_dir"),
        ),
        provider=provider_settings,
        history=HistorySettings(
            enabled=_required_bool(history, "enabled"),
            max_turns=max_turns,
        ),
    )


def _build_provider(
    provider: Mapping[str, object],
    environ: Mapping[str, str],
) -> ProviderSettings:
    base_url = _required_str(provider, "base_url")
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError("provider.base_url must be an http or https URL")

    api_key_env = _required_str(provider, "api_key_env")
    api_key = environ.get(api_key_env)
    if not api_key:
        raise ConfigError(f"Missing API key environment variable: {api_key_env}")

    return ProviderSettings(
        type=_optional_str(provider, "type", "openai_compatible"),
        base_url=base_url,
        api_key_env=api_key_env,
        api_key=api_key,
        model=_required_str(provider, "model"),
        temperature=_optional_number(provider, "temperature", 0.7),
        timeout_seconds=_required_number(provider, "timeout_seconds"),
    )


def _required_section(
    data: Mapping[str, Mapping[str, object]],
    section: str,
) -> Mapping[str, object]:
    values = data.get(section)
    if values is None:
        raise ConfigError(f"Missing required section: {section}")
    return values


def _required_str(values: Mapping[str, object], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{field} must be a non-empty string")
    return value


def _optional_str(values: Mapping[str, object], field: str, default: str) -> str:
    value = values.get(field, default)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{field} must be a non-empty string")
    return value


def _required_int(values: Mapping[str, object], field: str) -> int:
    value = values.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{field} must be an integer")
    return value


def _required_number(values: Mapping[str, object], field: str) -> float:
    value = values.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field} must be a number")
    return float(value)


def _optional_number(
    values: Mapping[str, object],
    field: str,
    default: float,
) -> float:
    value = values.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field} must be a number")
    return float(value)


def _required_bool(values: Mapping[str, object], field: str) -> bool:
    value = values.get(field)
    if not isinstance(value, bool):
        raise ConfigError(f"{field} must be a boolean")
    return value
