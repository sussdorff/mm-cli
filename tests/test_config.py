"""Tests for mm_cli.config module."""

from pathlib import Path

from mm_cli.config import Config, _format_toml_string_list, load_config, write_config


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self) -> None:
        """Test Config defaults to empty values."""
        cfg = Config()
        assert cfg.transfer_category == ""
        assert cfg.excluded_groups == []

    def test_custom_values(self) -> None:
        """Test Config with custom values."""
        cfg = Config(transfer_category="Umbuchungen", excluded_groups=["Aufgelöst"])
        assert cfg.transfer_category == "Umbuchungen"
        assert cfg.excluded_groups == ["Aufgelöst"]


class TestLoadConfig:
    """Tests for load_config()."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """When config file doesn't exist, return default Config."""
        cfg = load_config(path=tmp_path / "nonexistent.toml")
        assert cfg.transfer_category == ""
        assert cfg.excluded_groups == []

    def test_valid_config(self, tmp_path: Path) -> None:
        """Load a valid config file with both fields."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'transfer_category = "Umbuchungen"\nexcluded_groups = ["Aufgelöst", "Archiv"]\n',
            encoding="utf-8",
        )

        cfg = load_config(path=config_file)
        assert cfg.transfer_category == "Umbuchungen"
        assert cfg.excluded_groups == ["Aufgelöst", "Archiv"]

    def test_partial_config_transfer_only(self, tmp_path: Path) -> None:
        """Config with only transfer_category, no excluded_groups."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'transfer_category = "Umbuchungen"\n',
            encoding="utf-8",
        )

        cfg = load_config(path=config_file)
        assert cfg.transfer_category == "Umbuchungen"
        assert cfg.excluded_groups == []

    def test_partial_config_groups_only(self, tmp_path: Path) -> None:
        """Config with only excluded_groups, no transfer_category."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'excluded_groups = ["Aufgelöst"]\n',
            encoding="utf-8",
        )

        cfg = load_config(path=config_file)
        assert cfg.transfer_category == ""
        assert cfg.excluded_groups == ["Aufgelöst"]

    def test_empty_config_file(self, tmp_path: Path) -> None:
        """Empty config file returns defaults."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("", encoding="utf-8")

        cfg = load_config(path=config_file)
        assert cfg.transfer_category == ""
        assert cfg.excluded_groups == []

    def test_malformed_toml(self, tmp_path: Path) -> None:
        """Malformed TOML file returns defaults (no crash)."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml [[[", encoding="utf-8")

        cfg = load_config(path=config_file)
        assert cfg.transfer_category == ""
        assert cfg.excluded_groups == []

    def test_empty_string_values(self, tmp_path: Path) -> None:
        """Config with empty string values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'transfer_category = ""\nexcluded_groups = []\n',
            encoding="utf-8",
        )

        cfg = load_config(path=config_file)
        assert cfg.transfer_category == ""
        assert cfg.excluded_groups == []


class TestWriteConfig:
    """Tests for write_config()."""

    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        """Writing a config and reading it back produces the same values."""
        config_file = tmp_path / "mm-cli" / "config.toml"
        original = Config(
            transfer_category="Umbuchungen",
            excluded_groups=["Aufgelöst", "Archiv"],
        )

        write_config(original, path=config_file)
        loaded = load_config(path=config_file)

        assert loaded.transfer_category == original.transfer_category
        assert loaded.excluded_groups == original.excluded_groups

    def test_write_creates_directories(self, tmp_path: Path) -> None:
        """write_config creates parent directories if needed."""
        config_file = tmp_path / "deep" / "nested" / "config.toml"
        write_config(Config(), path=config_file)
        assert config_file.exists()

    def test_write_empty_config(self, tmp_path: Path) -> None:
        """Writing default (empty) config creates a valid file."""
        config_file = tmp_path / "config.toml"
        write_config(Config(), path=config_file)

        loaded = load_config(path=config_file)
        assert loaded.transfer_category == ""
        assert loaded.excluded_groups == []

    def test_write_returns_path(self, tmp_path: Path) -> None:
        """write_config returns the path where config was written."""
        config_file = tmp_path / "config.toml"
        result = write_config(Config(), path=config_file)
        assert result == config_file


class TestFormatTomlStringList:
    """Tests for _format_toml_string_list()."""

    def test_empty_list(self) -> None:
        assert _format_toml_string_list("key", []) == "key = []"

    def test_single_item(self) -> None:
        assert _format_toml_string_list("key", ["foo"]) == 'key = ["foo"]'

    def test_multiple_items(self) -> None:
        result = _format_toml_string_list("groups", ["A", "B", "C"])
        assert result == 'groups = ["A", "B", "C"]'
