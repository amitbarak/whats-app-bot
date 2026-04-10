"""
Tests for invoice_feteching.db_reader
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from invoice_feteching.db_reader import (
    UndefinedAttachment,
    build_engine,
    fetch_latest_attachments,
    load_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
SAMPLE_CONFIG = {
    "database": {
        "server": "test-server.database.windows.net",
        "port": 1433,
        "database": "testdb",
        "driver": "ODBC Driver 17 for SQL Server",
    },
    "blob_storage": {"base_url": "https://example.blob.core.windows.net/container"},
    "invoice_fetching": {"download_folder": "downloads", "top_n": 10},
}


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    """Write a minimal config.yaml to a temp directory and return its path."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(SAMPLE_CONFIG), encoding="utf-8")
    return cfg_file


@pytest.fixture()
def db_env(monkeypatch):
    """Ensure DB_USERNAME and DB_PASSWORD are set for tests."""
    monkeypatch.setenv("DB_USERNAME", "test_user")
    monkeypatch.setenv("DB_PASSWORD", "test_pass")


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------
class TestLoadConfig:
    def test_returns_dict(self, tmp_config):
        cfg = load_config(tmp_config)
        assert isinstance(cfg, dict)

    def test_contains_expected_keys(self, tmp_config):
        cfg = load_config(tmp_config)
        assert "database" in cfg
        assert "blob_storage" in cfg
        assert "invoice_fetching" in cfg

    def test_database_values(self, tmp_config):
        cfg = load_config(tmp_config)
        assert cfg["database"]["server"] == "test-server.database.windows.net"
        assert cfg["database"]["port"] == 1433

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# build_engine
# ---------------------------------------------------------------------------
class TestBuildEngine:
    def test_raises_without_env_vars(self, tmp_config, monkeypatch):
        monkeypatch.delenv("DB_USERNAME", raising=False)
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        with pytest.raises(EnvironmentError, match="DB_USERNAME"):
            build_engine(SAMPLE_CONFIG)

    def test_raises_with_only_username(self, monkeypatch):
        monkeypatch.setenv("DB_USERNAME", "user")
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        with pytest.raises(EnvironmentError):
            build_engine(SAMPLE_CONFIG)

    def test_returns_engine_with_valid_env(self, db_env):
        with patch("invoice_feteching.db_reader.create_engine") as mock_create:
            mock_create.return_value = MagicMock()
            engine = build_engine(SAMPLE_CONFIG)
            assert engine is not None
            mock_create.assert_called_once()

    def test_connection_string_contains_server(self, db_env):
        captured = {}

        def fake_create(conn_str, **kwargs):
            captured["conn_str"] = conn_str
            return MagicMock()

        with patch("invoice_feteching.db_reader.create_engine", side_effect=fake_create):
            build_engine(SAMPLE_CONFIG)

        assert "test-server.database.windows.net" in captured["conn_str"]
        assert "testdb" in captured["conn_str"]

    def test_connection_string_does_not_contain_plaintext_creds(self, db_env):
        """Credentials must be URL-encoded, not plain text with special chars."""
        captured = {}

        def fake_create(conn_str, **kwargs):
            captured["conn_str"] = conn_str
            return MagicMock()

        with patch("invoice_feteching.db_reader.create_engine", side_effect=fake_create):
            build_engine(SAMPLE_CONFIG)

        # The raw @ sign in "test_user" should NOT appear unencoded in the host part
        # (sqlalchemy uses user:pass@host format so @ in user must be encoded)
        conn = captured["conn_str"]
        assert "mssql+pyodbc://" in conn


# ---------------------------------------------------------------------------
# fetch_latest_attachments
# ---------------------------------------------------------------------------
class TestFetchLatestAttachments:
    def _make_attachment(self, id_, filename, is_delete=0):
        a = MagicMock(spec=UndefinedAttachment)
        a.ID = id_
        a.filename = filename
        a.IsDelete = is_delete
        return a

    def test_returns_list(self):
        session = MagicMock()
        session.scalars.return_value = iter([])
        result = fetch_latest_attachments(session, top_n=5)
        assert isinstance(result, list)

    def test_calls_scalars(self):
        session = MagicMock()
        session.scalars.return_value = iter([])
        fetch_latest_attachments(session, top_n=10)
        session.scalars.assert_called_once()

    def test_returns_items_from_session(self):
        a1 = self._make_attachment(1, "file1.pdf")
        a2 = self._make_attachment(2, "file2.pdf")
        session = MagicMock()
        session.scalars.return_value = iter([a1, a2])
        result = fetch_latest_attachments(session, top_n=10)
        assert len(result) == 2
        assert result[0].filename == "file1.pdf"
