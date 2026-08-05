---
domain: python-cli-patterns
description: Python CLI tool conventions — project structure, versioning, PyPI distribution, config resolution, update hints, packaging.
---

# Python CLI Patterns

> **Scope**: Loaded by Python development and testing skills that build or
> maintain command-line tools published to PyPI. Covers project layout, release
> flow, runtime config resolution, distribution, and update UX.

## What This Standard Covers

| File | Topic |
|------|-------|
| [project-scaffold.md](project-scaffold.md) | Directory layout and `pyproject.toml` template |
| [versioning-release.md](versioning-release.md) | CalVer, tag-driven GitHub Actions release, Trusted Publishing |
| [config-resolution.md](config-resolution.md) | Platform config paths, `key_command`, lazy click context |
| [distribution-packaging.md](distribution-packaging.md) | Hatchling `force-include`, package vs import names, `install-skill` |
| [update-and-ux.md](update-and-ux.md) | Rich output layer, Click/Rich boundary, PyPI version self-check, first-run wizard, output file conventions |

## When These Patterns Apply

A Python tool is a CLI under this standard when:

- It is invoked by users from a shell (entry point in `[project.scripts]`)
- It is distributed via PyPI and installed with `uv tool install <name>`
- It may require runtime configuration (API keys, server URLs)

For internal libraries without a CLI entry point, only `project-scaffold.md`
applies; the other sub-topics are optional.

## Core Rules

- Use the `src/` layout — prevents accidental local imports during development.
- Version is single-sourced from a git tag, stamped by CI, never hand-edited.
- Config resolution order: env var → `key_command` → explicit setup hint.
- Never self-update; show an upgrade hint and let the user run `uv tool upgrade`.
- Bundle non-Python files explicitly via Hatchling `force-include`.
- Human-facing output goes through Rich; machine-consumable output stays plain
  and Rich-free. Rich does not bind agent- or hook-consumed helper scripts.
