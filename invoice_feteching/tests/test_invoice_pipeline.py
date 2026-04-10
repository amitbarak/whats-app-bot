"""
Tests for invoice_feteching.invoice_pipeline
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from invoice_feteching.invoice_pipeline import InvoicePipeline


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
    "invoice_fetching": {"download_folder": "downloads", "top_n": 5},
}


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(SAMPLE_CONFIG), encoding="utf-8")
    return cfg_file


@pytest.fixture()
def db_env(monkeypatch):
    monkeypatch.setenv("DB_USERNAME", "test_user")
    monkeypatch.setenv("DB_PASSWORD", "test_pass")


def make_pipeline(tmp_config, db_env, tmp_path):
    """Return an InvoicePipeline with a mocked engine."""
    with patch("invoice_feteching.invoice_pipeline.build_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        pipeline = InvoicePipeline(config_path=tmp_config)
    # Override download folder to tmp_path
    pipeline.download_folder = tmp_path / "downloads"
    pipeline.file_fetcher.download_folder = pipeline.download_folder
    return pipeline


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
class TestInvoicePipelineInit:
    def test_creates_instance(self, tmp_config, db_env):
        with patch("invoice_feteching.invoice_pipeline.build_engine"):
            pipeline = InvoicePipeline(config_path=tmp_config)
        assert pipeline is not None

    def test_top_n_loaded_from_config(self, tmp_config, db_env):
        with patch("invoice_feteching.invoice_pipeline.build_engine"):
            pipeline = InvoicePipeline(config_path=tmp_config)
        assert pipeline.top_n == 5

    def test_base_url_passed_to_file_fetcher(self, tmp_config, db_env):
        with patch("invoice_feteching.invoice_pipeline.build_engine"):
            pipeline = InvoicePipeline(config_path=tmp_config)
        assert "example.blob.core.windows.net" in pipeline.file_fetcher.base_url


# ---------------------------------------------------------------------------
# fetch_records
# ---------------------------------------------------------------------------
class TestFetchRecords:
    def test_returns_list(self, tmp_config, db_env, tmp_path):
        pipeline = make_pipeline(tmp_config, db_env, tmp_path)

        with patch("invoice_feteching.invoice_pipeline.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            with patch(
                "invoice_feteching.invoice_pipeline.fetch_latest_attachments",
                return_value=[MagicMock(), MagicMock()],
            ):
                records = pipeline.fetch_records()

        assert isinstance(records, list)
        assert len(records) == 2

    def test_passes_top_n_to_query(self, tmp_config, db_env, tmp_path):
        pipeline = make_pipeline(tmp_config, db_env, tmp_path)

        with patch("invoice_feteching.invoice_pipeline.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            with patch(
                "invoice_feteching.invoice_pipeline.fetch_latest_attachments",
                return_value=[],
            ) as mock_fetch:
                pipeline.fetch_records()

        mock_fetch.assert_called_once_with(
            mock_session, top_n=5, exclude_deleted=True
        )


# ---------------------------------------------------------------------------
# download_files
# ---------------------------------------------------------------------------
class TestDownloadFiles:
    def test_delegates_to_file_fetcher(self, tmp_config, db_env, tmp_path):
        pipeline = make_pipeline(tmp_config, db_env, tmp_path)
        records = [MagicMock()]

        pipeline.file_fetcher.download = MagicMock(
            return_value={"success": ["f.pdf"], "failed": []}
        )
        result = pipeline.download_files(records)

        pipeline.file_fetcher.download.assert_called_once_with(records)
        assert result["success"] == ["f.pdf"]


# ---------------------------------------------------------------------------
# run (full pipeline)
# ---------------------------------------------------------------------------
class TestRun:
    def test_run_calls_fetch_and_download(self, tmp_config, db_env, tmp_path):
        pipeline = make_pipeline(tmp_config, db_env, tmp_path)
        mock_records = [MagicMock()]

        pipeline.fetch_records = MagicMock(return_value=mock_records)
        pipeline.download_files = MagicMock(
            return_value={"success": ["a.pdf"], "failed": []}
        )

        result = pipeline.run()

        pipeline.fetch_records.assert_called_once_with(exclude_deleted=True)
        pipeline.download_files.assert_called_once_with(mock_records)
        assert result["success"] == ["a.pdf"]

    def test_run_returns_results_dict(self, tmp_config, db_env, tmp_path):
        pipeline = make_pipeline(tmp_config, db_env, tmp_path)
        pipeline.fetch_records = MagicMock(return_value=[])
        pipeline.download_files = MagicMock(
            return_value={"success": [], "failed": []}
        )

        result = pipeline.run()
        assert "success" in result
        assert "failed" in result
