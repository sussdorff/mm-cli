# Project Scaffold

Every Python CLI tool follows this directory layout.

```
my-tool/
├── src/my_tool/
│   ├── __init__.py          # __version__ = "0.0.0.dev0"
│   ├── cli.py               # argparse or click entry point
│   ├── config.py            # platform-aware config loading (TOML)
│   └── ...
├── tests/
│   ├── conftest.py
│   └── test_*.py
├── .github/workflows/
│   └── release.yml          # tag-triggered PyPI publish
├── pyproject.toml
└── CHANGELOG.md
```

## pyproject.toml Template

```toml
[project]
name = "my-tool"
version = "0.0.0.dev0"       # stamped by CI, never edited manually
description = "What it does"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = ["rich>=14"]  # human-facing output layer

[project.scripts]
my-tool = "my_tool.cli:main"

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.9"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_tool"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100
```

## Key Rules

- `version = "0.0.0.dev0"` — never hand-edit, CI stamps from the git tag.
- `src/` layout — prevents accidental local imports during development.
- `hatchling` as build backend — fast, no `setup.py`.
- `dependency-groups` for dev deps — uv-native, not `extras`.
- `rich` is the only default runtime dependency — it renders human-facing
  output. A library without a CLI entry point does not need it. See
  `update-and-ux.md` for the human/machine output split.

**Why:** A consistent scaffold means every CLI tool is buildable, testable, and
publishable from day one.
