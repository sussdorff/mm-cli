---
name: python-dev
version: 1.0.0
description: >-
  Develop Python CLI tools — project scaffold, CLI entry points, packaging,
  PyPI release, config resolution. Use when writing Python, creating a CLI
  tool, setting up pyproject.toml, working with argparse or click, structuring
  a new Python project, adding uv tool support, or any Python development
  context that is not test-focused. Triggers on write python, python tool,
  python cli, build cli, argparse, click, pyproject.toml, uv tool, src layout,
  hatchling, pypi, calver.
requires_standards: [python-cli-patterns, english-only, no-emoji]
compatibility: {}
metadata: {}
---

# Python Dev

Author Python CLI tools that follow the project conventions: src/ layout,
hatchling build, CalVer versioning, PyPI release via Trusted Publishing.

## When to Use

- "Write a Python CLI tool"
- "Create a new Python project"
- "Set up pyproject.toml for a CLI"
- "Add argparse / click entry point"
- "Build and publish to PyPI"
- "Resolve config / API keys for a CLI"
- "Bundle assets in a wheel"

Do NOT use for test work — that is `python-test`.

## Workflow

1. **Confirm scope.** Is this a new project or a change to an existing one? If
   new, scaffold per `python-cli-patterns/project-scaffold.md`.
2. **Stick to the standard.** Project layout, `pyproject.toml`, and release flow
   come from `python-cli-patterns` (auto-loaded via `requires_standards`). Do
   not invent alternatives without an explicit reason.
3. **One source of truth for the version.** `__version__ = "0.0.0.dev0"` in the
   package, CI stamps from the git tag. Never hand-edit the version.
4. **Config resolution.** Env var first, then `key_command`, then a clear setup
   hint. Platform-aware paths only (no hardcoded `~/.config`).
5. **Distribution.** Hatchling `force-include` for non-Python assets. PyPI
   distribution name may differ from import name; verify name availability
   before the first `uv build`.
6. **No self-update at runtime.** Show a hint and rely on the user running
   `uv tool install <pkg> --force --refresh`.

## Boundaries

- This skill covers **authoring** the CLI. Testing it is `python-test`.
- For deeper details (release.yml, Trusted Publishing, click lazy context,
  install-skill, etc.) the loaded `python-cli-patterns` standard has the
  per-topic sibling files — follow the links from its entry.

## Do NOT

- Hand-edit the version in `pyproject.toml` or `__init__.py`.
- Use API tokens (`UV_PUBLISH_TOKEN`, `TWINE_PASSWORD`) — use Trusted Publishing.
- Hardcode `~/.config` — use the platform-aware resolver.
- Auto-open output files — gate behind an explicit `--open` flag.
- Self-update during execution — show a hint only.
- Render machine-consumable output (`--json`, IDs, paths) through Rich — Rich is
  for human-facing output only.

## Resources

| File | Purpose |
|------|---------|
| `python-cli-patterns` (standard) | Full conventions, auto-loaded via `requires_standards` |
