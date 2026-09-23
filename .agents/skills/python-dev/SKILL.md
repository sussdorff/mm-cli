---
name: python-dev
version: 1.0.0
description: Build and package Python CLI tools, including entry points, configuration and PyPI releases.
requires_standards: [python-cli-patterns, cli-versioning, sdk-versioning, db-migrations]
compatibility: {}
metadata: {}
---

# Python Dev

Author Python CLI tools that follow the project conventions: src/ layout,
hatchling build, and SemVer for importable libraries (`sdk-versioning`).
Independently distributed operator CLIs use `cli-versioning`; generic standalone
Python CLIs use `python-cli-patterns`.

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
2. **Select the release contract.** Project layout comes from
   `python-cli-patterns`. An independently distributed operator CLI uses
   `cli-versioning`: its committed `pyproject.toml` CalVer matches a
   `<tool>-vYYYY.M.N` tag. A generic standalone CLI uses the generic
   `python-cli-patterns` tag-stamping flow.
3. **Keep one source of truth for the applicable flow.** An operator CLI keeps
   its actual CalVer in the committed manifest and the workflow verifies it.
   A generic standalone CLI keeps the `0.0.0.dev0` sentinel and CI stamps it
   from the unscoped tag.
4. **Config resolution.** Env var first, then `key_command`, then a clear setup
   hint. Platform-aware paths only (no hardcoded `~/.config`).
5. **Distribution.** Hatchling `force-include` for non-Python assets. PyPI
   distribution name may differ from import name; verify name availability
   before the first `uv build`. Public tools release to PyPI via Trusted
   Publishing; private tools publish to the Forgejo registry
   (`python-cli-patterns/forgejo-registry.md`) so target machines install and
   upgrade with plain `uv tool install` / `uv tool upgrade`.
6. **No self-update at runtime.** Show a hint and rely on the user running
   `uv tool install <pkg> --force --refresh`.

## Boundaries

- This skill covers **authoring** the CLI. Testing it is `python-test`.
- For deeper details (release.yml, Trusted Publishing, click lazy context,
  install-skill, etc.) the loaded `python-cli-patterns` standard has the
  per-topic sibling files — follow the links from its entry.

## Do NOT

- Hand-edit a generic standalone CLI version in `pyproject.toml` or
  `__init__.py`; its CI stamps the release version. An operator CLI commits its
  actual CalVer before its matching scoped tag under `cli-versioning`.
- Use API tokens (`UV_PUBLISH_TOKEN`, `TWINE_PASSWORD`) against public PyPI —
  use Trusted Publishing. Exception: private tools publish to the Forgejo
  registry with a package-scoped token, see
  `python-cli-patterns/forgejo-registry.md`.
- Hardcode `~/.config` — use the platform-aware resolver.
- Auto-open output files — gate behind an explicit `--open` flag.
- Self-update during execution — show a hint only.
- Render machine-consumable output (`--json`, IDs, paths) through Rich — Rich is
  for human-facing output only.

## Resources

| File | Purpose |
|------|---------|
| `python-cli-patterns` (standard) | Full conventions, auto-loaded via `requires_standards` |
| `cli-versioning` (standard) | Independent operator CLI CalVer, committed-manifest, and scoped-tag contract |
