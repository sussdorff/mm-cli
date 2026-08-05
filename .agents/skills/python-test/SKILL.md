---
name: python-test
version: 1.0.0
description: >-
  Test Python CLI tools — pytest layout, click.testing.CliRunner, argparse
  invocation, fixtures, coverage. Use when writing Python tests, running
  pytest, mocking subprocess for key_command, testing a CLI entry point,
  or any Python test context. Triggers on pytest, uv run pytest, test python,
  test cli, CliRunner, conftest, test fixture python, click testing, capsys,
  monkeypatch.
requires_standards: [python-cli-patterns, english-only, no-emoji]
compatibility: {}
metadata: {}
---

# Python Test

Write and run tests for Python CLI tools. Knows the project layout from
`python-cli-patterns` so tests target the right modules, fixtures, and entry
points.

## When to Use

- "Write a test for this CLI"
- "Run pytest" / "uv run pytest"
- "Mock the `key_command`" / "stub `urlopen` for the PyPI check"
- "Test the argparse parser" / "test the click command"
- "Set up `conftest.py` for shared fixtures"

Do NOT use for authoring or release work — that is `python-dev`.

## Workflow

1. **Locate the test target.** Tests live in `tests/` at project root. The CLI
   entry point is `src/<package>/cli.py:main`. Layout per
   `python-cli-patterns/project-scaffold.md`.
2. **Pick the runner per CLI library.**
   - argparse-based CLI: invoke `main([arg, ...])` directly. Capture output
     with `capsys`.
   - click-based CLI: `from click.testing import CliRunner; CliRunner().invoke(cli, [...])`.
3. **Mock external boundaries.** Network calls (PyPI version check), subprocess
   (`key_command`), filesystem (config paths). Use `monkeypatch` for env vars
   and `pathlib` overrides.
4. **Run via `uv run pytest`** — never bare `pytest`. The project uses uv's
   dependency-groups for dev deps.
5. **Coverage and ruff** stay in `pyproject.toml`; tests follow `[tool.ruff]`
   line-length and `[tool.pytest.ini_options]` paths.

## Fixture Patterns

See [references/test-fixtures.md](references/test-fixtures.md) for ready-to-paste
`conftest.py` fixtures: isolated config dir, blocked network for PyPI self-check,
stubbed `key_command`, and CLI invocation patterns (CliRunner for click,
`main([...])` + `capsys` for argparse).

## Boundaries

- This skill covers **testing**. Authoring the CLI is `python-dev`.
- Topic details (CalVer normalization, click lazy context, install-skill) come
  from the auto-loaded `python-cli-patterns` standard — follow the sibling
  links from its entry.

## In-Process Over Subprocess

Default to invoking the CLI **in-process** via its `main(argv=[...])` entry
point + `capsys`, not via `subprocess.run([PYTHON, cli.py, ...])`.

| Style | Tradeoff |
|---|---|
| In-process `main([...])` + `capsys` | Fast (no Python startup per test), full stack traces on failure, easy to share fixtures, easy to monkeypatch internals |
| `subprocess.run([...])` | One Python interpreter launch per test (~100–300 ms each); errors surface as stdout/stderr blobs without tracebacks |

A real measurement from the library/meta repo (CL-uyp): 48 subprocess-based
tests took 154 s (~3.2 s/test). The same suite converted to in-process
invocation ran 113 tests in 9.5 s. Subprocess is the wrong default.

When you must use subprocess (e.g., testing real shell-level argv handling,
hook scripts, or interpreter-startup behaviour), say so explicitly in a
test-file comment so a future reader does not "fix" it back to in-process.

## Do NOT

- Run bare `pytest` — always `uv run pytest`.
- Hit the real network or real filesystem (`~/.config`) in tests — use fixtures.
- Skip the `key_command` mock — tests must not invoke real `op read` or `pass` commands.
- Write tests in any language other than English (`english-only` standard applies).

## Resources

| File | Purpose |
|------|---------|
| `python-cli-patterns` (standard) | Project layout + topic-specific test surfaces, auto-loaded |
| `references/test-fixtures.md` | Drop-in conftest fixtures and CLI invocation examples |
