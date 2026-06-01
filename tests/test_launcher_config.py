import pytest

from marvis_gateway_lab.launcher_config import (
    ConfigError,
    load_launcher_config,
    load_provider_config,
)


def write_toml(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def third_party_config(tmp_path):
    return write_toml(
        tmp_path / "third-party-api.local.toml",
        r"""
[provider]
base_url = "https://api.example.test/v1"
api_key_env = "MARVIS_THIRD_PARTY_API_KEY"
model = "gpt-test"
timeout_seconds = 30
""".strip(),
    )


def base_config(tmp_path):
    return write_toml(
        tmp_path / "launcher.toml",
        r"""
[launcher]
listen_host = "127.0.0.1"
listen_port = 8765
upstream_url = "ws://127.0.0.1:10123"
captures_dir = 'D:\Practice\idea\captures\api-launcher'

[provider]
type = "openai_compatible"
base_url = "https://api.example.test/v1"
api_key_env = "TEST_API_KEY"
model = "gpt-test"
temperature = 0.25
timeout_seconds = 30

[history]
enabled = true
max_turns = 8
""".strip(),
    )


def test_loads_third_party_provider_config_and_resolves_api_key_from_environ(tmp_path):
    config_path = third_party_config(tmp_path)

    config = load_provider_config(
        config_path,
        environ={"MARVIS_THIRD_PARTY_API_KEY": "secret-value"},
    )

    assert config.type == "openai_compatible"
    assert config.base_url == "https://api.example.test/v1"
    assert config.api_key_env == "MARVIS_THIRD_PARTY_API_KEY"
    assert config.api_key == "secret-value"
    assert config.model == "gpt-test"
    assert config.temperature == 0.7
    assert config.timeout_seconds == 30


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[provider]\napi_key = \"secret\"", "raw api_key"),
        ("[provider]\nraw_api_key = \"secret\"", "raw api_key"),
    ],
)
def test_third_party_provider_config_rejects_raw_api_keys(tmp_path, text, message):
    config_path = write_toml(tmp_path / "third-party-api.local.toml", text)

    with pytest.raises(ConfigError, match=message):
        load_provider_config(
            config_path,
            environ={"MARVIS_THIRD_PARTY_API_KEY": "secret-value"},
        )


def test_third_party_provider_config_rejects_missing_api_key_env(tmp_path):
    config_path = third_party_config(tmp_path)

    with pytest.raises(ConfigError, match="MARVIS_THIRD_PARTY_API_KEY"):
        load_provider_config(config_path, environ={})


def test_third_party_provider_local_config_overrides_base_config(tmp_path):
    config_path = third_party_config(tmp_path)
    local_path = write_toml(
        tmp_path / "third-party-api.override.toml",
        r"""
[provider]
base_url = "http://localhost:11434/v1"
api_key_env = "LOCAL_API_KEY"
model = "local-model"
timeout_seconds = 10
""".strip(),
    )

    config = load_provider_config(
        config_path,
        local_config_path=local_path,
        environ={
            "MARVIS_THIRD_PARTY_API_KEY": "base-secret",
            "LOCAL_API_KEY": "local-secret",
        },
    )

    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key_env == "LOCAL_API_KEY"
    assert config.api_key == "local-secret"
    assert config.model == "local-model"
    assert config.timeout_seconds == 10


def test_loads_launcher_config_and_resolves_api_key_from_environ(tmp_path):
    config_path = base_config(tmp_path)

    config = load_launcher_config(config_path, environ={"TEST_API_KEY": "secret-value"})

    assert config.launcher.listen_host == "127.0.0.1"
    assert config.launcher.listen_port == 8765
    assert config.launcher.upstream_url == "ws://127.0.0.1:10123"
    assert config.launcher.captures_dir == "D:\\Practice\\idea\\captures\\api-launcher"
    assert config.provider.type == "openai_compatible"
    assert config.provider.base_url == "https://api.example.test/v1"
    assert config.provider.api_key_env == "TEST_API_KEY"
    assert config.provider.api_key == "secret-value"
    assert config.provider.model == "gpt-test"
    assert config.provider.temperature == 0.25
    assert config.provider.timeout_seconds == 30
    assert config.history.enabled is True
    assert config.history.max_turns == 8


def test_local_config_accepts_utf8_bom_from_windows_powershell(tmp_path):
    config_path = base_config(tmp_path)
    local_path = tmp_path / "launcher.local.toml"
    local_path.write_bytes(
        "\ufeff[provider]\nmodel = \"bom-local-model\"\n".encode("utf-8")
    )

    config = load_launcher_config(
        config_path,
        local_config_path=local_path,
        environ={"TEST_API_KEY": "secret-value"},
    )

    assert config.provider.model == "bom-local-model"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[unknown]\nvalue = 1", "unknown section"),
        ("[launcher]\nextra = true", "unknown field"),
        ("[provider]\nraw_api_key = \"secret\"", "raw api_key"),
        ("[provider]\napi_key = \"secret\"", "raw api_key"),
    ],
)
def test_rejects_unknown_sections_fields_and_raw_api_keys(tmp_path, text, message):
    config_path = base_config(tmp_path)
    local_path = write_toml(tmp_path / "launcher.local.toml", text)

    with pytest.raises(ConfigError, match=message):
        load_launcher_config(
            config_path,
            local_config_path=local_path,
            environ={"TEST_API_KEY": "secret-value"},
        )
