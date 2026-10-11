"""Settings from the environment and from ``.env`` in the working directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from german_archives_mcp.config import ConfigError, load_config

VARIABLES = (
    "GERMAN_ARCHIVES_CACHE_DIR",
    "GERMAN_ARCHIVES_TIMEOUT",
    "GERMAN_ARCHIVES_MIN_INTERVAL",
    "GERMAN_ARCHIVES_CONTACT",
    "GERMAN_ARCHIVES_DOWNLOAD_DIR",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_nothing_is_required():
    cfg = load_config()
    assert cfg.timeout == 30.0 and cfg.min_interval == 2.0 and cfg.contact == ""
    assert cfg.cache_dir == Path.home() / ".cache" / "german-archives-mcp"
    assert cfg.download_dir is None


def test_every_setting_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("GERMAN_ARCHIVES_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("GERMAN_ARCHIVES_TIMEOUT", "15")
    monkeypatch.setenv("GERMAN_ARCHIVES_MIN_INTERVAL", "2.5")
    monkeypatch.setenv("GERMAN_ARCHIVES_CONTACT", "me@example.org")
    cfg = load_config()
    assert cfg.cache_dir == tmp_path / "c"
    assert (cfg.timeout, cfg.min_interval, cfg.contact) == (15.0, 2.5, "me@example.org")


@pytest.mark.parametrize("raw", ["thirty", "0", "-5", "nan", "inf"])
def test_an_unusable_timeout_names_the_variable(monkeypatch, raw):
    monkeypatch.setenv("GERMAN_ARCHIVES_TIMEOUT", raw)
    with pytest.raises(ConfigError, match="GERMAN_ARCHIVES_TIMEOUT"):
        load_config()


def test_the_interval_has_a_floor(monkeypatch):
    monkeypatch.setenv("GERMAN_ARCHIVES_MIN_INTERVAL", "1.5")
    with pytest.raises(ConfigError, match="at least 2.0"):
        load_config()


@pytest.mark.parametrize("raw", ["me@example.org\r\nX-Evil: 1", "me (home)"])
def test_a_contact_that_could_break_the_header_is_refused(monkeypatch, raw):
    monkeypatch.setenv("GERMAN_ARCHIVES_CONTACT", raw)
    with pytest.raises(ConfigError, match="GERMAN_ARCHIVES_CONTACT"):
        load_config()


def test_dot_env_in_the_working_directory_is_read(tmp_path):
    (tmp_path / ".env").write_text("GERMAN_ARCHIVES_TIMEOUT=7\n")
    assert load_config().timeout == 7.0


def test_the_environment_wins_over_dot_env(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("GERMAN_ARCHIVES_TIMEOUT=7\n")
    monkeypatch.setenv("GERMAN_ARCHIVES_TIMEOUT", "9")
    assert load_config().timeout == 9.0


def test_the_download_folder_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("GERMAN_ARCHIVES_DOWNLOAD_DIR", str(tmp_path))
    assert load_config().download_dir == tmp_path


@pytest.mark.parametrize("make", ["missing", "a file", "relative"])
def test_an_unusable_download_folder_names_the_variable(monkeypatch, tmp_path, make):
    raw = {
        "missing": str(tmp_path / "missing"),
        "a file": str(tmp_path / "file.txt"),
        "relative": "downloads",
    }[make]
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "downloads").mkdir()
    monkeypatch.setenv("GERMAN_ARCHIVES_DOWNLOAD_DIR", raw)
    with pytest.raises(ConfigError, match="GERMAN_ARCHIVES_DOWNLOAD_DIR"):
        load_config()


async def test_a_bad_setting_surfaces_on_the_first_tool_call(monkeypatch):
    """Configuration loads lazily, so a bad value is a result, not a crash at import."""
    import json

    from german_archives_mcp import server

    monkeypatch.setattr(server.runtime, "http", None)
    monkeypatch.setattr(server.runtime, "config", None)
    monkeypatch.setenv("GERMAN_ARCHIVES_TIMEOUT", "soon")
    result = await server.mcp.call_tool("cache_status", {})
    out = json.loads(result.content[0].text)
    assert out["error"] == "not_configured" and "GERMAN_ARCHIVES_TIMEOUT" in out["message"]
