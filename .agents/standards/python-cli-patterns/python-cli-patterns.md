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
| [versioning-release.md](versioning-release.md) | Generic standalone-Python-CLI CalVer, tag-driven GitHub Actions release, Trusted Publishing; independent operator CLIs use `cli-versioning` |
| [forgejo-registry.md](forgejo-registry.md) | Private distribution via the Forgejo PyPI registry — publish with twine, install/upgrade on target machines |
| [config-resolution.md](config-resolution.md) | Platform config paths, `key_command`, lazy click context |
| [distribution-packaging.md](distribution-packaging.md) | Hatchling `force-include`, package vs import names, `install-skill` |
| [update-and-ux.md](update-and-ux.md) | Rich output layer, Click/Rich boundary, version self-check and update execution, shell completion, first-run wizard, output file conventions |

## When These Patterns Apply

A Python tool is a CLI under this standard when:

- It is invoked by users from a shell (entry point in `[project.scripts]`)
- It is distributed via PyPI (public tools) or the Forgejo registry (private
  tools, see [forgejo-registry.md](forgejo-registry.md)) and installed with
  `uv tool install <name>`
- It may require runtime configuration (API keys, server URLs)

For internal libraries without a CLI entry point, only `project-scaffold.md`
applies; the other sub-topics are optional.

## Core Rules

- Use the `src/` layout — prevents accidental local imports during development.
- Generic standalone CLIs derive the version from a git tag and CI stamps
  `pyproject.toml` and `__version__`; no `VERSION` file or other source exists.
  Independently distributed operator CLIs instead use `cli-versioning`: their
  manifest version is committed before the matching scoped tag and is verified,
  never CI-stamped.
- Config resolution order: env var → `key_command` → explicit setup hint.
- Version checks are decentralized, update execution is centralized: every
  tool detects staleness and prints the exact
  `uv tool install <package> --force --refresh` line; no tool modifies its own
  installation during a normal command run. Customer-distributed tools on an
  entitlement-gated index are the documented exception.
- Bundle non-Python files explicitly via Hatchling `force-include`.
- Human-facing output goes through Rich; machine-consumable output stays plain
  and Rich-free. Rich does not bind agent- or hook-consumed helper scripts.
