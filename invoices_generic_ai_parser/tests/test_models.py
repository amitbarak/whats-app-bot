"""
Unit tests for invoices_generic_ai_parser.models
No AI calls — pure Pydantic validation logic.
"""
from datetime import date

import pytest
from pydantic import ValidationError

from invoices_generic_ai_parser.models import InvoiceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def valid_payload(**overrides) -> dict:
    base = {
        "Asm": "12345",
        "sum": 100.0,
        "nicuyPresent": 1.0,
        "dateAsm": "2026-01-01",
        "HaktzaaNum": None,
        "supplierCostumerID": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Construction — happy paths
# ---------------------------------------------------------------------------
class TestInvoiceResultConstruction:
    def test_minimal_valid(self):
        inv = InvoiceResult(**valid_payload())
        assert inv.Asm == "12345"
        assert inv.sum == 100.0

    def test_date_parsed_from_string(self):
        inv = InvoiceResult(**valid_payload(dateAsm="2026-03-15"))
        assert inv.dateAsm == date(2026, 3, 15)

    def test_date_accepted_as_date_object(self):
        inv = InvoiceResult(**valid_payload(dateAsm=date(2026, 3, 15)))
        assert inv.dateAsm == date(2026, 3, 15)

    def test_optional_fields_default_to_none(self):
        inv = InvoiceResult(**valid_payload())
        assert inv.HaktzaaNum is None
        assert inv.supplierCostumerID is None

    def test_optional_fields_accepted(self):
        inv = InvoiceResult(**valid_payload(HaktzaaNum="ABC123", supplierCostumerID="512956376"))
        assert inv.HaktzaaNum == "ABC123"
        assert inv.supplierCostumerID == "512956376"

    def test_nicuy_present_zero(self):
        inv = InvoiceResult(**valid_payload(nicuyPresent=0.0))
        assert inv.nicuyPresent == 0.0

    def test_nicuy_present_half(self):
        inv = InvoiceResult(**valid_payload(nicuyPresent=0.5))
        assert inv.nicuyPresent == 0.5


# ---------------------------------------------------------------------------
# Validation — rejection paths
# ---------------------------------------------------------------------------
class TestInvoiceResultValidation:
    def test_nicuy_above_one_rejected(self):
        with pytest.raises(ValidationError, match="nicuyPresent"):
            InvoiceResult(**valid_payload(nicuyPresent=1.1))

    def test_nicuy_below_zero_rejected(self):
        with pytest.raises(ValidationError, match="nicuyPresent"):
            InvoiceResult(**valid_payload(nicuyPresent=-0.1))

    def test_empty_asm_rejected(self):
        with pytest.raises(ValidationError):
            InvoiceResult(**valid_payload(Asm=""))

    def test_whitespace_asm_rejected(self):
        with pytest.raises(ValidationError):
            InvoiceResult(**valid_payload(Asm="   "))

    def test_sum_zero_rejected(self):
        with pytest.raises(ValidationError):
            InvoiceResult(**valid_payload(sum=0))

    def test_sum_negative_rejected(self):
        with pytest.raises(ValidationError):
            InvoiceResult(**valid_payload(sum=-50.0))

    def test_supplier_id_non_digits_rejected(self):
        with pytest.raises(ValidationError, match="supplierCostumerID"):
            InvoiceResult(**valid_payload(supplierCostumerID="ABC-12345"))


# ---------------------------------------------------------------------------
# Computed properties
# ---------------------------------------------------------------------------
class TestComputedProperties:
    def test_maam_full_rate(self):
        # sum=100, nicuyPresent=1.0 → VAT = 100 * 0.18 * 1.0 = 18
        inv = InvoiceResult(**valid_payload(sum=100.0, nicuyPresent=1.0))
        assert inv.maam_amount == pytest.approx(18.0)

    def test_maam_half_rate(self):
        # sum=100, nicuyPresent=0.5 → VAT = 100 * 0.18 * 0.5 = 9
        inv = InvoiceResult(**valid_payload(sum=100.0, nicuyPresent=0.5))
        assert inv.maam_amount == pytest.approx(9.0)

    def test_maam_zero(self):
        inv = InvoiceResult(**valid_payload(sum=100.0, nicuyPresent=0.0))
        assert inv.maam_amount == 0.0

    def test_sum_before_maam(self):
        # sum=100, nicuyPresent=1.0 → pre-VAT = 100 - 18 = 82
        inv = InvoiceResult(**valid_payload(sum=100.0, nicuyPresent=1.0))
        assert inv.sum_before_maam == pytest.approx(82.0)

    def test_maam_formula_consistency(self):
        """maam_amount + sum_before_maam should always equal sum."""
        for nicuy in [0.0, 0.5, 0.667, 1.0]:
            inv = InvoiceResult(**valid_payload(sum=283.5, nicuyPresent=nicuy))
            assert inv.maam_amount + inv.sum_before_maam == pytest.approx(inv.sum, rel=1e-5)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
class TestSerialization:
    def test_to_dict_keys(self):
        inv = InvoiceResult(**valid_payload())
        d = inv.to_dict()
        assert set(d.keys()) == {
            "Asm", "sum", "nicuyPresent", "dateAsm",
            "HaktzaaNum", "supplierCostumerID",
            "sum_before_maam",
        }

    def test_to_dict_date_is_string(self):
        inv = InvoiceResult(**valid_payload(dateAsm="2026-04-10"))
        assert inv.to_dict()["dateAsm"] == "2026-04-10"

    def test_supplier_id_normalised(self):
        """Hyphens should be stripped from supplierCostumerID."""
        inv = InvoiceResult(**valid_payload(supplierCostumerID="512-956-376"))
        assert inv.supplierCostumerID == "512956376"
