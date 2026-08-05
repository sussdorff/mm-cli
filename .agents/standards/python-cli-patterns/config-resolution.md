# Config Resolution

CLI tools that need configuration (API keys, server URLs) resolve sources in
this order:

```
1. Environment variable (e.g. GEMINI_API_KEY, OPENROUTER_API_KEY)
2. key_command from the config file (shell command whose stdout is the key)
3. Explicit error with a clear setup hint
```

## `key_command`

The `key_command` field in a CLI's config holds an arbitrary shell command whose
stdout is the API key. This avoids vendor-specific integrations (e.g. binding
to 1Password only).

```json
{
  "api": "openrouter",
  "key_command": "op read 'op://API Keys/OpenRouter/credential'"
}
```

```python
import subprocess

def _run_key_command(command: str) -> str:
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"key_command failed: {result.stderr.strip()}")
    key = result.stdout.strip()
    if not key:
        raise RuntimeError(f"key_command returned empty output: {command}")
    return key
```

## Platform-Aware Config Paths

Do NOT hardcode `~/.config` for all platforms.

```python
import os, sys
from pathlib import Path

def get_config_dir(tool_name: str) -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / tool_name
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / tool_name if xdg else Path.home() / ".config" / tool_name
```

| Platform | Path | Source |
|----------|------|--------|
| macOS / Linux | `$XDG_CONFIG_HOME/<tool>/` or `~/.config/<tool>/` | XDG spec |
| Windows | `%APPDATA%\<tool>\` | Windows convention |

**Why:** Hardcoding `~/.config` breaks Windows, where `%APPDATA%` is the
standard config location.

## Click Lazy Context Loading

Click runs the group callback before subcommands, which blocks `--help` when no
config file exists yet. Use a `_LazyContext` dict subclass that only loads
config on first access:

```python
class _LazyContext(dict[str, Any]):
    def __init__(self, config_loader: Callable[[], Config]) -> None:
        super().__init__()
        self._config_loader = config_loader
        self._client: Client | None = None

    def __getitem__(self, key: str) -> Any:
        if key == "client":
            if self._client is None:
                cfg = self._config_loader()
                self._client = Client(cfg.server_url, cfg.api_token)
            return self._client
        return super().__getitem__(key)

@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)
    ctx.obj = _LazyContext(load_config)
```

**Why:** Without lazy init, `cli --help` or `cli subgroup --help` fails with
`FileNotFoundError` when no config exists yet.
