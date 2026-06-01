# Architecture

This project keeps the official Marvis UI in place and redirects the local Agent model path to a local OpenAI-compatible adapter.

## Runtime Path

```text
Marvis UI
  -> MarvisHost
  -> 127.0.0.1:6161 MarvisAgent.exe
  -> local model mode on port 19080
  -> marvis_gateway_lab local-openai-adapter
  -> third-party OpenAI-compatible API
```

The wrapper flow preserves MarvisAgent's local orchestration path while replacing the model backend with an upstream provider chosen by local configuration.

## Main Components

- `src/marvis_gateway_lab/local_openai_adapter.py`: local HTTP adapter that exposes OpenAI-compatible endpoints used by MarvisAgent.
- `src/marvis_gateway_lab/providers/openai_compatible.py`: upstream OpenAI-compatible provider client.
- `src/marvis_gateway_lab/launcher_config.py`: strict TOML config loader that rejects raw API key fields.
- `src/marvis_gateway_lab/agent_wrapper.py`: wrapper argument handling for launching the official Agent binary.
- `scripts/start-local-model-adapter.ps1`: starts the adapter on `127.0.0.1:19080`.
- `scripts/start-marvis-wrapper-shell.ps1`: installs the wrapper, starts the adapter, then starts Marvis.
- `scripts/restore-marvis-agent-wrapper.ps1`: restores the official Agent binary from `MarvisAgent.real.exe`.

## Configuration Model

The committed file `config/third-party-api.example.toml` documents the provider config shape. Users create `config/third-party-api.local.toml` locally.

Raw API keys are intentionally rejected. The config stores only the environment variable name:

```toml
[provider]
base_url = "https://api.example.com/v1"
model = "your-model-name"
api_key_env = "MARVIS_THIRD_PARTY_API_KEY"
timeout_seconds = 120
```

## Runtime Artifacts

Scripts write process state, logs, wrapper builds, and patch backups under `captures/`. That directory is intentionally ignored and should not be published.

## Verification Strategy

- Unit tests cover config validation, adapter forwarding behavior, wrapper arguments, and script syntax.
- `test-marvis-third-party-canary.js` confirms that the Marvis Agent request path reaches the local adapter.
- `smoke-marvis-agent.js` can exercise simple conversation and tool-call paths through a live Marvis Agent.
