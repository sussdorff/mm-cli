# Distribution and Packaging

## Package Name vs Import Name

PyPI normalizes package names: hyphens, underscores, and dots collide. So
`nanobanana` and `nano-banana` are treated as the same name.

```toml
# pyproject.toml — distribution name differs from import name
[project]
name = "nanobanana-cli"    # PyPI distribution name (what users install)

[project.scripts]
nanobanana = "nanobanana.cli:main"  # CLI command uses the import name
```

**Checklist before `uv build`:**

1. Search PyPI for similar names.
2. If taken, suffix with `-cli`, `-tool`, or similar.
3. Keep the import name (package directory) unchanged for code simplicity.

**Why:** PyPI rejects uploads when the normalized name matches an existing
package — late discovery of conflicts wastes a release cycle.

## Hatchling — Bundling Non-Python Files

Hatchling only packages `.py` files by default. To include Markdown, YAML, or
asset files in the wheel:

```toml
[tool.hatch.build.targets.wheel.force-include]
"skill/nanobanana" = "nanobanana/skill"
```

At runtime, access bundled files via `importlib.resources`:

```python
from importlib.resources import files
from pathlib import Path

skill_pkg = files("nanobanana") / "skill"
skill_dir = Path(str(skill_pkg))
```

**Why:** Without `force-include`, non-Python files are silently excluded from
the wheel, causing runtime `FileNotFoundError`.

## `install-skill` Subcommand

When a Python CLI tool ships a Claude Code skill:

```
uv tool install <package>         # Step 1: install the CLI
<package> install-skill            # Step 2: copy skill to ~/.claude/skills/
```

Requirements:

1. Bundle skill files in the wheel via `force-include`.
2. Handle `install-skill` before argparse to avoid flag conflicts (e.g. `--claude-dir`).
3. Verify `~/.claude` exists before copying — print a clear error if missing.
4. Accept `--claude-dir <path>` to override the target directory.
5. Support editable installs: fall back to the repo source directory when package data is not found.

```python
def install_skill(claude_dir: str | None = None) -> None:
    claude_path = Path(claude_dir) if claude_dir else Path.home() / ".claude"
    if not claude_path.exists():
        print(f"Claude Code directory not found: {claude_path}")
        print("Install Claude Code first, then re-run this command.")
        return
    # ... copy bundled skill files to claude_path / "skills" / "<name>"
```

**Why:** `uv tool install` does not preserve the source directory, so skills
cannot be symlinked from the repo. Bundling plus an explicit install step is
the only reliable distribution path.
