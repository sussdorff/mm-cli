# Project Context: mm-cli

> Generated on 2026-04-21 via the manual `project-context` workflow. Edit freely; this document is intentionally static.
> Conventions were derived from `.claude/CLAUDE.md`, `AGENTS.md`, `README.md`, `pyproject.toml`, `.github/workflows/release.yml`, and the current source tree.

## Tech Stack

| Layer | Technology | Version / Notes |
|-------|------------|-----------------|
| Language | Python | `>=3.12` from `pyproject.toml` |
| Runtime | macOS + `osascript` | The CLI only works on macOS and automates the MoneyMoney desktop app through AppleScript |
| CLI framework | Typer | Command tree and argument parsing live in `mm_cli/cli.py` |
| Terminal UI | Rich | Human-readable tables, styled status messages, and CSV/JSON output helpers live in `mm_cli/output.py` |
| Domain modeling | stdlib `dataclasses` + `Enum` | Shared entities and typed value objects live in `mm_cli/models.py` |
| Build backend | Hatchling | Wheel and sdist packaging configured in `pyproject.toml` |
| Dependency / tool manager | `uv` | Used for local development, tool installation, tests, and release builds |
| Test framework | pytest + `typer.testing` | Unit tests focus on pure logic and CLI behavior with mocked AppleScript boundaries |
| Linter | Ruff | Configured in `pyproject.toml` with import sorting and upgrade rules enabled |
| CI / release | GitHub Actions | `.github/workflows/release.yml` runs tests on tag push, builds with `uv`, and publishes to PyPI |

**Package managers detected:** `uv` for dependency resolution and runtime tooling; Hatchling for build artifacts.

## Architecture Principles

> Why the codebase is structured this way.

1. **MoneyMoney is the system of record**: `mm-cli` does not maintain its own transaction store or sync layer. It reads and writes through MoneyMoney's AppleScript API so the desktop app remains the authoritative source for accounts, categories, balances, and transfers.
2. **Keep the platform-specific boundary narrow**: All interaction with `osascript`, MoneyMoney error strings, plist payloads, and transfer execution is isolated in `mm_cli/applescript.py`. That keeps the rest of the codebase testable on machines that do not have MoneyMoney installed.
3. **Separate orchestration from computation and rendering**: `cli.py` assembles workflows, `analysis.py` computes aggregates, `output.py` renders them, and `models.py` carries the typed data structures between layers. The repository prefers explicit module boundaries over a single large command file.
4. **Favor scriptable CLI surfaces over interactive-only behavior**: Most read commands support structured output and deterministic flags. Even human-facing commands are designed to be predictable in shell pipelines, with JSON/CSV output and consistent error exits.
5. **Keep local state minimal and additive**: The only persistent local state in the package is the XDG config file created by `mm init`, which stores transfer filtering and active-group preferences. Everything else is recomputed from live MoneyMoney exports.
6. **Be conservative with financial mutations**: Commands that can change data or initiate money movement validate aggressively, provide dry-run or confirmation paths, and surface clear user-facing errors instead of raw stack traces.
7. **Treat repository operations as part of the architecture**: `AGENTS.md` and `.claude/CLAUDE.md` make issue tracking through `bd`, release hygiene, and live MoneyMoney verification part of the project's expected workflow rather than optional process documentation.

## Module Map

> High-level repository layout. This stays intentionally coarse-grained.

| Module / Directory | Purpose | Key Files |
|-------------------|---------|-----------|
| `mm_cli/` | Core Python package containing command orchestration, AppleScript integration, analysis logic, config handling, output formatting, and rule suggestion logic | `cli.py`, `applescript.py`, `analysis.py` |
| `tests/` | Pytest suite covering CLI behavior, parsing, analysis logic, config handling, and rule suggestion behavior with fixtures and mocks | `test_cli.py`, `conftest.py`, `test_analysis.py` |
| `.github/` | Release automation for test, build, and publish steps | `workflows/release.yml` |
| `.claude/` | Repo-local implementation conventions and project learnings for coding agents | `CLAUDE.md` |
| `.beads/` | Local bead tracking state, hooks, and workflow metadata used by `bd` | `PRIME.md`, `config.yaml` |
| `docs/` | Static architecture and onboarding documents generated manually | `project-context.md` |
| `repository root` | Packaging, release notes, and human-facing project documentation | `pyproject.toml`, `README.md`, `cliff.toml` |

## Established Patterns

> Recurring implementation patterns that show up across the codebase.

### CLI as orchestration layer
**Where**: `mm_cli/cli.py`
**Pattern**: Commands gather arguments, validate user intent, call export or mutation helpers, optionally run analysis helpers, and then delegate final formatting to `output.py`.
**Why**: This keeps command behavior explicit without pushing parsing or terminal rendering down into domain modules.

### Single AppleScript boundary
**Where**: `mm_cli/applescript.py`, `mm_cli/cli.py`
**Pattern**: All calls into MoneyMoney happen through one module that wraps `subprocess.run(["osascript", ...])`, normalizes MoneyMoney failure modes, and converts plist payloads into Python objects.
**Why**: The platform-specific integration stays localized, which reduces accidental coupling and makes unit tests viable with mocks.

### Typed domain objects as the shared contract
**Where**: `mm_cli/models.py`, plus consumers in `analysis.py`, `output.py`, and tests
**Pattern**: Accounts, transactions, categories, portfolios, and analysis outputs are represented as dataclasses and enums with lightweight `to_dict()` helpers.
**Why**: Shared typed objects keep analysis, rendering, and tests aligned on the same data shape and avoid passing raw plist dictionaries through the whole application.

### Pure-ish analysis functions over exported snapshots
**Where**: `mm_cli/analysis.py`
**Pattern**: Spending, cashflow, recurring transaction detection, merchant summaries, balance history, and transfer filtering run over already-exported model lists rather than pulling data themselves.
**Why**: This makes the analysis code reusable, deterministic, and straightforward to test independently of the MoneyMoney integration layer.

### Output adapters separated from business logic
**Where**: `mm_cli/output.py`
**Pattern**: Table, JSON, and CSV rendering are centralized in dedicated output helpers rather than spread across command implementations.
**Why**: Presentation changes can be made without touching the command semantics or the underlying analysis logic.

### Mock the external app, not the internal models
**Where**: `tests/test_cli.py`, `tests/test_applescript.py`, `tests/conftest.py`
**Pattern**: Tests patch export and mutation functions at the CLI boundary and then assert on command output, exit behavior, and computed results using realistic dataclass fixtures.
**Why**: The suite verifies internal behavior without requiring a live MoneyMoney instance, while still modeling the shapes returned by the external API.

### Config-driven transfer filtering
**Where**: `mm_cli/config.py`, `mm_cli/analysis.py`, `mm_cli/cli.py`
**Pattern**: Analysis commands default to removing internal transfers using two signals: configured transfer-category paths and own-account IBAN/account-number detection.
**Why**: Financial analysis is more accurate when internal shuffles do not appear as spending or income, but the behavior remains overridable with explicit flags.

## Critical Invariants

> Rules that should continue to hold as the codebase evolves.

1. **MoneyMoney stays authoritative**: Do not introduce a secondary persistence layer for accounts, transactions, balances, or categories. The CLI may cache nothing durable except user preferences in the config file.
2. **AppleScript errors must be normalized into CLI-safe failures**: MoneyMoney not running, locked databases, and other AppleScript failures should surface as clear user messages and exit codes, not uncaught tracebacks.
3. **Analysis defaults must exclude internal transfers**: Spending, cashflow, recurring detection, merchant views, and top-customer views assume transfer filtering unless the user explicitly opts into `--include-transfers` or `--transfers-only`.
4. **`--include-transfers` and `--transfers-only` remain mutually exclusive**: Any future analysis command using transfer filtering should preserve the same flag contract to avoid ambiguous results.
5. **Configuration must fail open to defaults**: Missing or malformed config files should never block command execution; `load_config()` should keep returning a default `Config`.
6. **Mutation commands stay deliberate**: Transfer creation, category updates, checkmark updates, and comment updates should validate identifiers and keep preview / confirmation paths where available.
7. **Live-app verification is part of feature completion**: `.claude/CLAUDE.md` explicitly requires testing significant changes against the real MoneyMoney app after unit tests, because mocked fixtures do not guarantee real AppleScript payload compatibility.
8. **Repository work is tracked in beads**: New follow-up work belongs in `bd`, not in ad hoc markdown task lists or undocumented TODO piles.

## Enforcement Matrix

> No contracts declared yet - add ADRs to populate this matrix.

---
*Generated by `project-context` · Edit freely · Regenerate manually when architecture changes significantly.*
