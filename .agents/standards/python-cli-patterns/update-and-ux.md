# Update Hints and UX Conventions

## Terminal Output — Rich for Humans, Plain for Machines

[Rich](https://rich.readthedocs.io) is the rendering layer for everything a
person reads: tables, panels, rules, progress, syntax highlighting, tracebacks.
It is a runtime dependency of every user-facing CLI (see
`project-scaffold.md`).

The split is by consumer, not by file:

| Output | Renderer |
|--------|----------|
| Human-facing text, tables, panels, progress, tracebacks | `rich.console.Console` |
| Machine-consumable: JSON, IDs, paths, anything a pipe or another program parses | `print()` / `json.dumps()` — never Rich |

```python
from rich.console import Console

console = Console()           # human output -> stdout
err = Console(stderr=True)    # diagnostics, warnings, update hints -> stderr
```

**Why the split:** Rich wraps and truncates to terminal width. A table rendered
into a pipe loses columns, and a JSON document printed through `Console` can be
re-wrapped until it no longer parses.

### Non-TTY Contract

1. Never set `force_terminal=True`. Rich detects the terminal; overriding that
   emits ANSI into files and pipes.
2. No `Progress`, `Status`, or spinner unless `sys.stdout.isatty()`.
3. Honour `NO_COLOR` (Rich does this on its own) and offer an explicit
   `--no-color` flag mapped to `Console(no_color=True)`.
4. Every command that produces data offers a machine mode (`--json`), and that
   path bypasses `Console` entirely.

```python
if args.json:
    print(json.dumps(payload))       # never through Console
else:
    console.print(build_table(payload))
```

### Click / Rich Boundary

Click and Rich overlap. Assign each concern once:

| Concern | Owner |
|---------|-------|
| Argument parsing, `--help`, exit codes | Click (or argparse) |
| Prompts and confirmations | `click.prompt` / `click.confirm` in Click tools, `rich.prompt` in argparse tools |
| Rendering: `Console.print`, `Table`, `Panel`, `Rule`, `Progress`, `Markdown`, `Syntax` | Rich |
| Tracebacks | `rich.traceback.install(show_locals=False)` |

Do not mix within a concern: no `click.echo` for styled output, no
`rich.prompt.Prompt` inside a Click command. `rich-click` is allowed when the
project wants a Rich-rendered `--help`; it does not move the boundary.

### Markup and Emoji

Rich console markup (`[bold]`, `[red]`, `[dim]`) is allowed. Rich's `:shortcode:`
emoji markup and literal emoji are not — the always-on no-emoji rule covers CLI
output like any other string. Carry status with style, plain words, or ASCII
symbols (`->`, `*`, `[ok]`).

### Where These Rules Apply

They bind user-facing CLIs distributed via PyPI and installed with
`uv tool install`. They do **not** bind deterministic helper scripts whose
consumer is an agent, a hook, or another program — those keep plain, stable,
parseable output (see the `execution-result-envelope` standard). Rich there
costs a dependency resolution on every `uv run --script` invocation and
decorates output that something else has to parse.

## Version Self-Check and Update Execution

Detection is decentralized, execution is centralized:

- Every tool checks whether a newer version exists and prints a one-line hint.
- No tool modifies its own installation during a normal command run. These
  tools are mostly invoked by agents and hooks: an install that mutates
  mid-run changes output contracts under the caller, and an interactive
  update prompt hangs in non-TTY contexts.
- Update execution is one implementation, not one per tool: the user or a
  fleet-level updater command runs
  `uv tool install <package> --force --refresh`. The hint prints exactly that
  command.

**Exception:** tools distributed to customers through an entitlement-gated
package index may offer an interactive, TTY-gated update prompt — customers
have no fleet manager. That logic lives in the customer platform's shared
library, never in internal tools.

### Lightweight Inline Check (public PyPI)

Query the PyPI JSON API after the main command completes:

```python
import json, sys
from urllib.request import urlopen
from urllib.error import URLError

def check_for_update(package: str, current: str) -> str | None:
    """Return an update hint string, or None if up-to-date."""
    try:
        with urlopen(f"https://pypi.org/pypi/{package}/json", timeout=3) as resp:
            latest = json.loads(resp.read())["info"]["version"]
            current_norm = normalize_version(current)
            if current_norm != latest:
                return (
                    f"Update available: {current_norm} -> {latest}"
                    f"  (uv tool install {package} --force --refresh)"
                )
            return None
    except (URLError, json.JSONDecodeError, KeyError, OSError):
        return None

# Call in main() after the command completes
hint = check_for_update("my-tool", __version__)
if hint:
    err.print(f"\n[dim]{hint}[/dim]")   # Console(stderr=True)
```

### Private Registry Check (Forgejo)

Private tools check the same registry they install from — never public PyPI,
where the name may be squatted. The Forgejo registry serves a PEP 503 simple
index (`.../api/packages/<owner>/pypi/simple/<package>/`); request it with the
same credentials the `[[index]]` entry in `~/.config/uv/uv.toml` already
holds, and take the highest version from the listed filenames. The timeout,
cache, and never-fail rules below apply unchanged.

### Design Rules

1. Public tools use the PyPI JSON API (`https://pypi.org/pypi/<package>/json`) — `pip index` and `uv pip index` are unreliable or nonexistent. Private tools use their Forgejo simple index.
2. Short timeout: 3 seconds for inline checks, 10 seconds for an adapter pattern.
3. Cache the result for 24 hours.
4. Show a hint only — never modify the tool's own installation during a normal command run. Self-updating mid-run can corrupt the running process and changes behavior under a calling agent.
5. Normalize CalVer versions before comparison (see `versioning-release.md`).
6. Never let check failures affect the CLI (`except ... pass`).

## Shell Completion

Detection follows the same shape as version checks: every tool exposes one
uniform surface, installation is centralized.

Every argparse CLI adds one flag to its root parser, generated from the live
parser with [shtab](https://docs.iterative.ai/shtab/):

```python
import shtab  # small, pure-Python runtime dependency

parser = argparse.ArgumentParser(prog="my-tool")
shtab.add_argument_to(parser, ["--print-completion"])  # bash | zsh | tcsh
```

### Design Rules

1. The flag is `--print-completion {bash,zsh,tcsh}` on the root parser — the
   same surface on every tool, so an installer can enumerate installed tools
   and collect scripts without per-tool knowledge.
2. The generated scripts are static: subcommands and flags complete; dynamic
   values (names, IDs) do not. A tool that needs dynamic completion for one
   argument adds it deliberately, later, per tool.
3. Do not use eval-based per-prompt completion (argcomplete): it starts a
   Python interpreter on every TAB press and puts an `eval` line into every
   shell rc.
4. Installation is centralized, not per tool: the fleet manager collects
   `<tool> --print-completion zsh` output into one completions directory on
   the `fpath` and prints the rc snippet once. Tools never write to shell rc
   files themselves.
5. Click tools keep Click's built-in completion
   (`_TOOL_COMPLETE=zsh_source <tool>`); the installer treats that as the
   second known surface.

## First-Run Setup Wizard

CLI tools that require config should auto-launch a setup wizard on first use
when all three conditions are met:

1. No config file exists.
2. No API key environment variables are set.
3. stdin is a TTY (interactive terminal).

```python
try:
    config = resolve_config(args)
except RuntimeError:
    if not config_path.exists() and not has_env_keys() and sys.stdin.isatty():
        run_setup_wizard()  # Guide user through initial config
        return
    raise  # Non-interactive or partial config -> re-raise
```

In non-TTY mode, print a hint instead of raising:

```
Error: No API key configured.
Run: my-tool setup
```

**Why:** A raw `RuntimeError` on first use is confusing. Auto-launching the
wizard guides users immediately, without requiring them to read docs.

## Output Files — No Auto-Open

When a CLI generates an output file, do NOT auto-open it in a viewer. Use an
explicit opt-in flag (`-open` or `--open`):

```python
if args.open:
    import subprocess, sys
    if sys.platform == "darwin":
        subprocess.run(["open", output_path])
    elif sys.platform == "win32":
        subprocess.run(["start", str(output_path)], shell=True)
    else:
        subprocess.run(["xdg-open", str(output_path)])
```

**Why:** Auto-opening breaks scripting, pipelines, and headless environments.
The flag makes the behavior explicit and opt-in.
