"""
Tests for invoices_generic_ai_parser.pipeline

Two categories:
  1. Unit tests  — mock parse_invoice, no real API calls
  2. Integration tests — real AI calls on up to N=10 real invoices
     Run with:  pytest -m integration
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoices_generic_ai_parser.models import InvoiceResult
from invoices_generic_ai_parser.pipeline import InvoiceParsePipeline

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REAL_INVOICES = _PROJECT_ROOT / "real life invoices"
_DOWNLOADED = _PROJECT_ROOT / "invoice_feteching" / "downloaded_files"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_result(**kwargs) -> InvoiceResult:
    defaults = {
        "Asm": "1001",
        "sum": 200.0,
        "nicuyPresent": 1.0,
        "dateAsm": "2026-01-01",
        "HaktzaaNum": None,
        "supplierCostumerID": "512956376",
    }
    defaults.update(kwargs)
    return InvoiceResult(**defaults)


def seed_pdf_files(folder: Path, count: int) -> list[Path]:
    """Write *count* minimal fake PDF files into *folder*."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        p = folder / f"invoice_{i:03d}.pdf"
        p.write_bytes(b"%PDF-1.4 fake")
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
class TestCollectFiles:
    def test_returns_at_most_n_files(self, tmp_path):
        seed_pdf_files(tmp_path, 15)
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)
        files = pipeline.collect_files()
        assert len(files) <= 10

    def test_returns_all_files_when_fewer_than_n(self, tmp_path):
        seed_pdf_files(tmp_path, 3)
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)
        files = pipeline.collect_files()
        assert len(files) == 3

    def test_skips_unsupported_file_types(self, tmp_path):
        seed_pdf_files(tmp_path, 2)
        (tmp_path / "readme.txt").write_text("ignore me")
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)
        files = pipeline.collect_files()
        assert all(f.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"} for f in files)
        assert len(files) == 2

    def test_empty_folder_returns_empty_list(self, tmp_path):
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)
        assert pipeline.collect_files() == []


class TestParseFiles:
    def test_successful_parses_go_to_results(self, tmp_path):
        files = seed_pdf_files(tmp_path, 3)
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)
        result = make_result()

        with patch("invoices_generic_ai_parser.pipeline.parse_invoice", return_value=result):
            results, errors = pipeline.parse_files(files)

        assert len(results) == 3
        assert errors == []

    def test_failed_parse_goes_to_errors(self, tmp_path):
        files = seed_pdf_files(tmp_path, 2)
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)
        good = make_result()

        def side_effect(path, client=None):
            if "000" in path.name:
                raise ValueError("bad invoice")
            return good

        with patch("invoices_generic_ai_parser.pipeline.parse_invoice", side_effect=side_effect):
            results, errors = pipeline.parse_files(files)

        assert len(errors) == 1
        assert len(results) == 1

    def test_validation_error_goes_to_errors(self, tmp_path):
        from pydantic import ValidationError

        files = seed_pdf_files(tmp_path, 1)
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10)

        # Raise a real ValidationError
        def bad_parse(path, client=None):
            InvoiceResult(
                Asm="x", sum=100, nicuyPresent=99,  # invalid
                dateAsm="2026-01-01"
            )

        with patch("invoices_generic_ai_parser.pipeline.parse_invoice", side_effect=bad_parse):
            results, errors = pipeline.parse_files(files)

        assert len(errors) == 1
        assert errors[0]["error"] == "validation"


class TestWriteResults:
    def test_json_file_created(self, tmp_path):
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10, output_dir=tmp_path / "out")
        r = make_result()
        out = pipeline.write_results([r], [])
        assert out.exists()

    def test_json_contains_invoices_key(self, tmp_path):
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10, output_dir=tmp_path / "out")
        r = make_result()
        out = pipeline.write_results([r], [])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "invoices" in data
        assert data["total_parsed"] == 1

    def test_json_contains_errors_key(self, tmp_path):
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10, output_dir=tmp_path / "out")
        errors = [{"file": "bad.pdf", "error": "ValueError", "detail": "oops"}]
        out = pipeline.write_results([], errors)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["total_errors"] == 1
        assert data["errors"][0]["file"] == "bad.pdf"

    def test_invoice_dict_has_expected_fields(self, tmp_path):
        pipeline = InvoiceParsePipeline(folder=tmp_path, n=10, output_dir=tmp_path / "out")
        r = make_result(Asm="9999", sum=283.0, nicuyPresent=0.5)
        out = pipeline.write_results([r], [])
        data = json.loads(out.read_text(encoding="utf-8"))
        inv = data["invoices"][0]
        assert inv["Asm"] == "9999"
        assert inv["sum"] == 283.0
        assert "maam_amount" not in inv
        assert "sum_before_maam" in inv


class TestRunMethod:
    def test_run_missing_folder_raises(self, tmp_path):
        pipeline = InvoiceParsePipeline(folder=tmp_path / "nonexistent", n=10)
        with pytest.raises(FileNotFoundError):
            pipeline.run()

    def test_run_empty_folder_returns_empty_results(self, tmp_path):
        pipeline = InvoiceParsePipeline(
            folder=tmp_path, n=10, output_dir=tmp_path / "out"
        )
        outcome = pipeline.run()
        assert outcome["results"] == []
        assert outcome["errors"] == []

    def test_run_end_to_end_mocked(self, tmp_path):
        seed_pdf_files(tmp_path, 5)
        pipeline = InvoiceParsePipeline(
            folder=tmp_path, n=10, output_dir=tmp_path / "out"
        )
        mock_result = make_result()

        with patch("invoices_generic_ai_parser.pipeline.parse_invoice",
                   return_value=mock_result):
            outcome = pipeline.run()

        assert len(outcome["results"]) == 5
        assert outcome["errors"] == []
        assert outcome["out_file"].exists()


# ---------------------------------------------------------------------------
# Integration tests — real AI calls, max N=10
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestPipelineIntegration:
    """
    Makes REAL OpenAI API calls on actual invoice files.
    Requires OPENAI_API_KEY in .env.
    Run with:  pytest -m integration
    """

    @pytest.mark.skipif(
        not (_REAL_INVOICES.exists() and any(_REAL_INVOICES.glob("*.pdf"))),
        reason="No real PDF invoices found in 'real life invoices' folder",
    )
    def test_pipeline_on_real_invoices(self, tmp_path):
        pipeline = InvoiceParsePipeline(
            folder=_REAL_INVOICES,
            n=10,
            output_dir=tmp_path / "out",
        )
        outcome = pipeline.run()

        results = outcome["results"]
        assert len(results) > 0, "Expected at least 1 successfully parsed invoice"

        for r in results:
            assert isinstance(r, InvoiceResult)
            assert r.Asm
            assert r.sum > 0
            assert 0.0 <= r.nicuyPresent <= 1.0

    @pytest.mark.skipif(
        not (_DOWNLOADED.exists() and any(_DOWNLOADED.iterdir())),
        reason="downloaded_files folder is empty",
    )
    def test_pipeline_on_downloaded_files(self, tmp_path):
        pipeline = InvoiceParsePipeline(
            folder=_DOWNLOADED,
            n=10,
            output_dir=tmp_path / "out",
        )
        outcome = pipeline.run()
        # At least check we didn't crash; results may vary by file type
        assert isinstance(outcome["results"], list)
        assert isinstance(outcome["errors"], list)
