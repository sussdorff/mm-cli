# Test Fixtures (python-test reference)

Common `conftest.py` fixtures for testing Python CLI tools that follow
`python-cli-patterns`. Drop these into the project's `tests/conftest.py`.

## Isolated config directory

Redirects `$XDG_CONFIG_HOME` and `%APPDATA%` so the test never touches the
user's real config.

```python
import pytest
from pathlib import Path

@pytest.fixture
def fake_config_dir(tmp_path, monkeypatch):
    """Redirect XDG/APPDATA to a tmp dir; isolates tests from real config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path
```

## Block network for PyPI self-check

Forces `urlopen` to raise `URLError` so the PyPI version-check code path is
exercised in its "no network" branch without actually calling out.

```python
import pytest
from urllib.error import URLError

@pytest.fixture
def no_network(monkeypatch):
    """Block urlopen so PyPI self-check cannot reach the network in tests."""
    def boom(*args, **kwargs):
        raise URLError("blocked in tests")
    monkeypatch.setattr("urllib.request.urlopen", boom)
```

## Stub `key_command`

Lets the test inject a fake API key without invoking `op read`, `pass`, or
similar real key-resolution commands.

```python
import pytest

@pytest.fixture
def fake_key(monkeypatch):
    """Make _run_key_command return a deterministic test key."""
    def fake_run(command):
        return "test-key-deadbeef"
    monkeypatch.setattr("my_tool.config._run_key_command", fake_run)
    return "test-key-deadbeef"
```

## Click CLI invocation

```python
from click.testing import CliRunner
from my_tool.cli import cli

def test_help_works_without_config(fake_config_dir):
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
```

## Argparse CLI invocation

```python
from my_tool.cli import main

def test_subcommand(fake_config_dir, capsys):
    main(["subcommand", "--flag"])
    captured = capsys.readouterr()
    assert "expected output" in captured.out
```
