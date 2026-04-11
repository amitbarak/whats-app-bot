"""
models.py
---------
Pydantic model for a parsed invoice result.

Schema fields:
  Asm               – invoice ID / number (מספר חשבונית)
  sum               – total transaction amount INCLUDING VAT (כולל מע"מ)
  nicuyPresent      – VAT partiality factor (0–1).
                      e.g. 1.0 = full 18% VAT applies
                           0.5 = half VAT applies → effective rate = 9%
                      VAT amount formula: sum × 0.18 × nicuyPresent
  dateAsm           – invoice date (תאריך חשבונית)
  HaktzaaNum        – allocation / withholding-tax reference number (מספר הקצאה)
  supplierCostumerID– supplier or customer tax ID (מזהה ספק / לקוח)
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Israeli standard VAT rate (18 %)
STANDARD_VAT_RATE: float = 0.18


class InvoiceResult(BaseModel):
    """Validated representation of a single parsed invoice."""

    Asm: str = Field(
        description="Invoice / document number (מספר חשבונית / אסמכתא)"
    )
    sum: float = Field(
        gt=0,
        description="Total transaction amount INCLUDING VAT in shekels (כולל מע\"מ)",
    )
    nicuyPresent: float = Field(
        description=(
            "VAT deductibility factor (0–1). "
            "1.0 = full VAT (18 %), 0.5 = half VAT (9 %), 0 = no VAT. "
            "Effective VAT amount = sum × 0.18 × nicuyPresent"
        )
    )
    dateAsm: date = Field(description="Invoice date (תאריך חשבונית)")
    HaktzaaNum: Optional[str] = Field(
        default=None,
        description="Allocation / withholding-tax certificate number (מספר הקצאה)",
    )
    supplierCostumerID: Optional[str] = Field(
        default=None,
        description="9-digit supplier or customer tax ID (ע\"מ / ח\"פ / ת.ז.)",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("nicuyPresent")
    @classmethod
    def nicuy_must_be_fraction(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"nicuyPresent must be between 0 and 1, got {v}"
            )
        return v

    @field_validator("Asm")
    @classmethod
    def asm_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Asm (invoice number) must not be empty")
        return v.strip()

    @field_validator("supplierCostumerID")
    @classmethod
    def supplier_id_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = v.replace("-", "").replace(" ", "")
        if not digits.isdigit():
            raise ValueError(
                f"supplierCostumerID must contain only digits, got '{v}'"
            )
        return digits  # normalise: return only digits

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------
    @property
    def maam_amount(self) -> float:
        """Actual VAT amount in shekels: sum × 0.18 × nicuyPresent."""
        return round(self.sum * STANDARD_VAT_RATE * self.nicuyPresent, 2)

    @property
    def sum_before_maam(self) -> float:
        """Pre-VAT amount: sum − maam_amount."""
        return round(self.sum - self.maam_amount, 2)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict including computed fields."""
        return {
            "Asm": self.Asm,
            "sum": self.sum,
            "nicuyPresent": self.nicuyPresent,
            "dateAsm": self.dateAsm.isoformat(),
            "HaktzaaNum": self.HaktzaaNum,
            "supplierCostumerID": self.supplierCostumerID,
            "sum_before_maam": self.sum_before_maam,
        }
