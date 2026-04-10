"""
Tests for invoice_feteching.file_fetcher
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from invoice_feteching.file_fetcher import FileFetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_attachment(id_=1, filename="93_file.pdf", original="invoice.pdf", is_delete=0):
    a = MagicMock()
    a.ID = id_
    a.filename = filename
    a.originalFilename = original
    a.IsDelete = is_delete
    return a


@pytest.fixture()
def fetcher(tmp_path: Path) -> FileFetcher:
    return FileFetcher(
        base_url="https://ronen.blob.core.windows.net/srokbk",
        download_folder=tmp_path / "downloads",
    )


# ---------------------------------------------------------------------------
# build_url
# ---------------------------------------------------------------------------
class TestBuildUrl:
    def test_simple_filename(self, fetcher):
        url = fetcher.build_url("93_63910747921889.pdf")
        assert url == "https://ronen.blob.core.windows.net/srokbk/93_63910747921889.pdf"

    def test_trailing_slash_on_base_stripped(self, tmp_path):
        f = FileFetcher("https://example.com/container/", tmp_path)
        assert f.build_url("file.pdf") == "https://example.com/container/file.pdf"

    def test_subfolder_filename(self, fetcher):
        url = fetcher.build_url("2024/january/invoice.pdf")
        assert "2024/january/invoice.pdf" in url


# ---------------------------------------------------------------------------
# download — success path
# ---------------------------------------------------------------------------
class TestDownloadSuccess:
    def test_creates_download_folder(self, fetcher, tmp_path):
        att = make_attachment()
        mock_resp = MagicMock()
        mock_resp.content = b"PDF content"
        mock_resp.raise_for_status = MagicMock()

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            fetcher.download([att])

        assert fetcher.download_folder.exists()

    def test_file_written_with_original_name(self, fetcher):
        att = make_attachment(filename="93_file.pdf", original="my_invoice.pdf")
        mock_resp = MagicMock()
        mock_resp.content = b"PDF content"
        mock_resp.raise_for_status = MagicMock()

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            fetcher.download([att])

        assert (fetcher.download_folder / "my_invoice.pdf").exists()

    def test_fallback_to_filename_basename_when_no_original(self, fetcher):
        att = make_attachment(filename="93_file.pdf", original=None)
        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.raise_for_status = MagicMock()

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            fetcher.download([att])

        assert (fetcher.download_folder / "93_file.pdf").exists()

    def test_returns_success_entry(self, fetcher):
        att = make_attachment()
        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.raise_for_status = MagicMock()

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            results = fetcher.download([att])

        assert len(results["success"]) == 1
        assert results["failed"] == []

    def test_folder_emptied_before_download(self, fetcher):
        """Old files in the folder should be removed before new downloads."""
        fetcher.download_folder.mkdir(parents=True)
        old_file = fetcher.download_folder / "old_file.txt"
        old_file.write_text("old")

        att = make_attachment()
        mock_resp = MagicMock()
        mock_resp.content = b"new"
        mock_resp.raise_for_status = MagicMock()

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            fetcher.download([att])

        assert not old_file.exists()

    def test_duplicate_names_get_id_suffix(self, fetcher):
        """Two attachments with the same originalFilename should not overwrite each other."""
        att1 = make_attachment(id_=1, filename="a.pdf", original="invoice.pdf")
        att2 = make_attachment(id_=2, filename="b.pdf", original="invoice.pdf")

        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.raise_for_status = MagicMock()

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            results = fetcher.download([att1, att2])

        files = list(fetcher.download_folder.iterdir())
        assert len(files) == 2
        assert len(results["success"]) == 2


# ---------------------------------------------------------------------------
# download — failure paths
# ---------------------------------------------------------------------------
class TestDownloadFailures:
    def test_http_error_goes_to_failed(self, fetcher):
        att = make_attachment()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=404)
        )

        with patch("invoice_feteching.file_fetcher.requests.get", return_value=mock_resp):
            results = fetcher.download([att])

        assert len(results["failed"]) == 1
        assert results["success"] == []

    def test_connection_error_goes_to_failed(self, fetcher):
        att = make_attachment()

        with patch(
            "invoice_feteching.file_fetcher.requests.get",
            side_effect=requests.ConnectionError("timeout"),
        ):
            results = fetcher.download([att])

        assert len(results["failed"]) == 1

    def test_mixed_success_and_failure(self, fetcher):
        good = make_attachment(id_=1, filename="good.pdf", original="good.pdf")
        bad = make_attachment(id_=2, filename="bad.pdf", original="bad.pdf")

        good_resp = MagicMock()
        good_resp.content = b"ok"
        good_resp.raise_for_status = MagicMock()

        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=500)
        )

        def side_effect(url, **kwargs):
            return good_resp if "good" in url else bad_resp

        with patch("invoice_feteching.file_fetcher.requests.get", side_effect=side_effect):
            results = fetcher.download([good, bad])

        assert len(results["success"]) == 1
        assert len(results["failed"]) == 1
