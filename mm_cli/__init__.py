"""mm-cli: CLI tool for MoneyMoney macOS app."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_PACKAGE_NAME = "moneymoney-cli"


def _resolve_version() -> str:
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject.open("rb") as pyproject_file:
            return tomllib.load(pyproject_file)["project"]["version"]


__version__ = _resolve_version()
