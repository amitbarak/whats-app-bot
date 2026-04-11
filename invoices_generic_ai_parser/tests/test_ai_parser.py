"""
Tests for invoices_generic_ai_parser.ai_parser

Two categories:
  1. Unit tests  — mock the OpenAI client, no real API calls
  2. Integration tests — real AI calls, marked with @pytest.mark.integration
     Run with:  pytest -m integration
     Skip with: pytest -m "not integration"
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoices_generic_ai_parser.ai_parser import parse_invoice, DEFAULT_MAX_RETRIES
from invoices_generic_ai_parser.models import InvoiceResult

# ---------------------------------------------------------------------------
# Path to real invoices used by integration tests
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REAL_INVOICES = _PROJECT_ROOT / "real life invoices"
_REAL_PDFS = sorted(_REAL_INVOICES.glob("*.pdf")) if _REAL_INVOICES.exists() else []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_openai_response(payload: dict) -> MagicMock:
    """Create a fake OpenAI chat completion response."""
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


VALID_AI_RESPONSE = {
    "Asm": "66314",
    "sum": 140.0,
    "nicuyPresent": 1.0,
    "dateAsm": "2026-01-19",
    "HaktzaaNum": None,
    "supplierCostumerID": "512956376",
}


# ---------------------------------------------------------------------------
# Unit tests — mocked AI
# ---------------------------------------------------------------------------
class TestParseInvoiceUnit:
    def test_pdf_returns_invoice_result(self, tmp_path):
        """A valid AI response produces a validated InvoiceResult."""
        # Create a dummy PDF (pdfplumber will fail — mock that too)
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            VALID_AI_RESPONSE
        )

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="Invoice text here"):
            result = parse_invoice(pdf, client=mock_client)

        assert isinstance(result, InvoiceResult)
        assert result.Asm == "66314"

    def test_result_values_match_ai_response(self, tmp_path):
        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            VALID_AI_RESPONSE
        )
        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            result = parse_invoice(pdf, client=mock_client)

        assert result.sum == 140.0
        assert result.nicuyPresent == 1.0
        assert result.supplierCostumerID == "512956376"

    def test_empty_pdf_raises_value_error(self, tmp_path):
        pdf = tmp_path / "empty.pdf"
        pdf.write_bytes(b"fake")
        mock_client = MagicMock()

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value=""):
            with pytest.raises(ValueError, match="No extractable text"):
                parse_invoice(pdf, client=mock_client)

    def test_unsupported_file_type_raises(self, tmp_path):
        txt = tmp_path / "invoice.txt"
        txt.write_text("text")
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_invoice(txt)

    def test_invalid_json_from_ai_raises_value_error(self, tmp_path):
        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")
        mock_client = MagicMock()
        bad_resp = MagicMock()
        bad_resp.choices = [MagicMock()]
        bad_resp.choices[0].message.content = "not json at all"
        mock_client.chat.completions.create.return_value = bad_resp

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            with pytest.raises(ValueError, match="invalid JSON"):
                parse_invoice(pdf, client=mock_client)

    def test_invalid_pydantic_response_raises_validation_error(self, tmp_path):
        from pydantic import ValidationError

        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")
        mock_client = MagicMock()
        # nicuyPresent=5 violates the 0–1 constraint — all retries return bad data
        bad_payload = {**VALID_AI_RESPONSE, "nicuyPresent": 5.0}
        mock_client.chat.completions.create.return_value = make_openai_response(bad_payload)

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            with pytest.raises(ValidationError):
                parse_invoice(pdf, client=mock_client, max_retries=0)

    def test_image_file_uses_base64_path(self, tmp_path):
        """PNG files should go through the vision code path (base64 encoding)."""
        png = tmp_path / "invoice.png"
        png.write_bytes(b"\x89PNG fake")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            VALID_AI_RESPONSE
        )

        result = parse_invoice(png, client=mock_client)

        # Check the call used image_url content, not plain text
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0]["type"] == "image_url"
        assert isinstance(result, InvoiceResult)


# ---------------------------------------------------------------------------
# Retry logic tests — mocked AI
# ---------------------------------------------------------------------------
class TestRetryLogic:
    """Verify that parse_invoice retries on ValidationError and self-corrects."""

    def test_default_max_retries_is_2(self):
        assert DEFAULT_MAX_RETRIES == 2

    def test_succeeds_on_second_attempt(self, tmp_path):
        """First call returns bad schema; second returns valid → should succeed."""
        from pydantic import ValidationError

        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")

        bad_payload  = {**VALID_AI_RESPONSE, "nicuyPresent": 99.0}   # invalid
        good_payload = VALID_AI_RESPONSE                               # valid

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            make_openai_response(bad_payload),
            make_openai_response(good_payload),
        ]

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            result = parse_invoice(pdf, client=mock_client, max_retries=1)

        assert isinstance(result, InvoiceResult)
        assert mock_client.chat.completions.create.call_count == 2

    def test_succeeds_on_third_attempt(self, tmp_path):
        """Two bad responses then one good → succeeds within 2 retries."""
        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")

        bad_payload  = {**VALID_AI_RESPONSE, "nicuyPresent": 99.0}
        good_payload = VALID_AI_RESPONSE

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            make_openai_response(bad_payload),
            make_openai_response(bad_payload),
            make_openai_response(good_payload),
        ]

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            result = parse_invoice(pdf, client=mock_client, max_retries=2)

        assert isinstance(result, InvoiceResult)
        assert mock_client.chat.completions.create.call_count == 3

    def test_raises_after_all_retries_exhausted(self, tmp_path):
        """All attempts return invalid schema → ValidationError raised."""
        from pydantic import ValidationError

        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")

        bad_payload = {**VALID_AI_RESPONSE, "nicuyPresent": 99.0}
        mock_client = MagicMock()
        # Return bad payload every time
        mock_client.chat.completions.create.return_value = make_openai_response(bad_payload)

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            with pytest.raises(ValidationError):
                parse_invoice(pdf, client=mock_client, max_retries=2)

        # 1 initial + 2 retries = 3 total calls
        assert mock_client.chat.completions.create.call_count == 3

    def test_total_calls_equals_one_plus_retries(self, tmp_path):
        """Confirm call count = 1 + max_retries on total failure."""
        from pydantic import ValidationError

        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")

        bad_payload = {**VALID_AI_RESPONSE, "nicuyPresent": 99.0}
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = make_openai_response(bad_payload)

        for retries in [0, 1, 2, 3]:
            mock_client.reset_mock()
            with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                       return_value="text"):
                with pytest.raises(ValidationError):
                    parse_invoice(pdf, client=mock_client, max_retries=retries)
            assert mock_client.chat.completions.create.call_count == 1 + retries

    def test_retry_appends_error_feedback_to_messages(self, tmp_path):
        """On retry, the conversation should include the bad response + error message."""
        from pydantic import ValidationError

        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")

        bad_payload  = {**VALID_AI_RESPONSE, "nicuyPresent": 99.0}
        good_payload = VALID_AI_RESPONSE

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            make_openai_response(bad_payload),
            make_openai_response(good_payload),
        ]

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            parse_invoice(pdf, client=mock_client, max_retries=1)

        # The second call should have more messages (original + assistant bad reply + correction request)
        second_call_messages = mock_client.chat.completions.create.call_args_list[1][1]["messages"]
        roles = [m["role"] for m in second_call_messages]
        assert "assistant" in roles  # bad response echoed back
        assert roles.count("user") >= 2  # original + correction request

    def test_no_retry_on_unsupported_file(self, tmp_path):
        """Unsupported file type raises immediately — no AI call, no retry."""
        txt = tmp_path / "doc.txt"
        txt.write_text("text")
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="Unsupported"):
            parse_invoice(txt, client=mock_client, max_retries=2)

        mock_client.chat.completions.create.assert_not_called()

    def test_no_retry_on_json_decode_error(self, tmp_path):
        """Bad JSON from AI raises immediately — no retry (can't recover schema)."""
        pdf = tmp_path / "inv.pdf"
        pdf.write_bytes(b"fake")

        mock_client = MagicMock()
        bad_resp = MagicMock()
        bad_resp.choices = [MagicMock()]
        bad_resp.choices[0].message.content = "not json {"
        mock_client.chat.completions.create.return_value = bad_resp

        with patch("invoices_generic_ai_parser.ai_parser._extract_text_from_pdf",
                   return_value="text"):
            with pytest.raises(ValueError, match="invalid JSON"):
                parse_invoice(pdf, client=mock_client, max_retries=2)

        # Only one call — JSON errors are not retried
        mock_client.chat.completions.create.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests — real OpenAI calls
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestParseInvoiceIntegration:
    """
    These tests make REAL calls to the OpenAI API.
    They require OPENAI_API_KEY to be set in .env.
    Run with:  pytest -m integration
    """

    @pytest.mark.skipif(not _REAL_PDFS, reason="No real PDF invoices found")
    @pytest.mark.parametrize("pdf_path", _REAL_PDFS[:10])  # max N=10
    def test_real_pdf_parses_successfully(self, pdf_path):
        """Each real PDF should parse and validate without errors."""
        result = parse_invoice(pdf_path)

        assert isinstance(result, InvoiceResult)
        assert result.Asm  # not empty
        assert result.sum > 0
        assert 0.0 <= result.nicuyPresent <= 1.0
        assert result.dateAsm is not None

    @pytest.mark.skipif(not _REAL_PDFS, reason="No real PDF invoices found")
    def test_real_pdf_computed_fields_consistent(self):
        """maam + pre_vat should equal sum on real invoice."""
        result = parse_invoice(_REAL_PDFS[0])
        assert result.maam_amount + result.sum_before_maam == pytest.approx(result.sum, rel=1e-4)

    @pytest.mark.skipif(not _REAL_PDFS, reason="No real PDF invoices found")
    def test_real_pdf_to_dict_is_serialisable(self):
        """to_dict() output should round-trip through JSON cleanly."""
        result = parse_invoice(_REAL_PDFS[0])
        d = result.to_dict()
        serialised = json.dumps(d)
        assert len(serialised) > 0
