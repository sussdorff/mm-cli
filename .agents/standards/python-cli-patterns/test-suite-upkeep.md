# Test Suite Upkeep

A CLI built test-first accumulates one test per RED step. Once the feature is
green, many of those tests have done their job. They pin wording, docs,
templates or intermediate shapes, and they add runtime without adding
protection. Review the suite on a schedule, run it in parallel, and isolate it
from the developer's machine.

## Value Review

Review the suite at least once per release train. Review it sooner when a
serial local run exceeds about one minute, or when CI and local runtimes differ
by more than a factor of three. A gap that size means the environment is
leaking into the tests; see Isolation below.

Keep a test when it proves one of these:

- the CLI starts, parses its commands and emits its documented output contract
  (JSON envelope, exit codes)
- a refusal happens before any side effect (validation, prohibited input,
  missing authority)
- a data-loss guard holds (dirty worktree, protected branch, a directory the
  tool must not delete)
- a security boundary holds (no credential in output or logs, no argument
  injection, no plain-http token transport, no SSRF)
- idempotency or recovery holds (replay, conflict, uncertain outcome)
- a regression that actually happened stays fixed

Delete a test when it:

- asserts prose in README, SKILL.md, CHANGELOG, release docs or templates
- duplicates a stronger test at the same seam, including parameter sweeps
  where one case per failure class suffices
- pins an intermediate TDD step or an implementation detail that no user or
  caller depends on
- is permanently skipped, or needs an environment that CI never has

Evidence for a deletion: the pull request lists each kept test and the
invariant it covers, and states the before and after count and runtime. Delete
fixtures and helpers that no remaining test references. When in doubt about a
real-git or real-filesystem data-loss test, keep it and make it fast instead.

## Parallel Execution

Run the suite with pytest-xdist by default:

```toml
[dependency-groups]
dev = ["pytest>=8.0", "pytest-xdist>=3.8", "ruff>=0.9"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-n auto"
```

`-n0` runs serially for debugging. A test that fails only in parallel shares
state through the home directory, a fixed port, a fixed path or the working
directory. Fix the sharing; do not mark the test serial.

## Isolation

One autouse fixture in `tests/conftest.py` keeps every test and every worker
away from the real home directory and the developer's git configuration:

```python
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
```

Without `GIT_CONFIG_GLOBAL`, a global `core.hooksPath`, commit signing or
templates run on every fixture commit. In ccore that took a commit from
0.03 s to 3.8 s, and a 90-second CI suite took 27 minutes locally. Add any
tool-specific state paths (metrics databases, journals) to the same fixture.

## Subprocess Calls

Tests that exercise the CLI as a process call the installed entry point of the
test environment directly:

```python
import sys
from pathlib import Path

TOOL = str(Path(sys.executable).with_name("my-tool"))
```

Do not call `uv run my-tool` from a test. Each call resolves and syncs the
environment again, and parallel workers contend for the same lock. Prefer
calling `main(argv)` in-process where the test does not need a real process
boundary.

## Lint Scope

`ruff check .` lints only the project's own sources. Library-managed copies of
skills and standards (`.agents/`, `.claude/`) are linted in their source
repository:

```toml
[tool.ruff]
extend-exclude = [".agents", ".claude"]
```

Otherwise the first Library sync that tracks those directories fails every CI
run for reasons outside the project.
