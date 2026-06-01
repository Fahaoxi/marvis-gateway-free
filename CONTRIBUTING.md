# Contributing

Thanks for helping make this project easier to run and safer to publish.

## Development Setup

```powershell
python -m pip install -e .[dev]
npm install
```

Run tests before submitting changes:

```powershell
python -m pytest
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-before-publish.ps1
```

## Guidelines

- Keep API keys and local provider settings out of commits.
- Prefer environment variables for sensitive values.
- Keep runtime output under `captures/`.
- Update README or docs when changing launch behavior.
- Add or update tests for config, adapter, wrapper, or script behavior changes.

## Reporting Issues

Please include:

- Windows version
- PowerShell version
- Python version
- Marvis version if known
- The command you ran
- Sanitized error output

Do not include API keys, raw captures, local databases, cookies, or account identifiers.
