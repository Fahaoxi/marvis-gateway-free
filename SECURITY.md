# Security Policy

## Sensitive Data

Do not publish:

- API keys or bearer tokens
- `config/third-party-api.local.toml`
- `captures/`
- logs, PID records, local databases, or Marvis user data
- built wrapper binaries copied from a local Marvis installation

The config loader rejects raw `api_key` and `raw_api_key` fields. Use `api_key_env` and provide the secret through the environment.

## Reporting Security Issues

If you find a security issue, open a private report if the repository host supports it. Otherwise, contact the maintainer privately before opening a public issue.

When reporting, include enough detail to reproduce the issue but redact secrets, local user identifiers, and captured conversation data.
