"""
ai_parser.py
------------
Responsible for:
  - Extracting text from PDF files (via pdfplumber)
  - Encoding image files to base64 for vision models
  - Calling the OpenAI API with the skill prompt
  - Validating and returning the response as an InvoiceResult Pydantic model
  - Retrying up to MAX_RETRIES times when the AI response fails schema validation,
    feeding the validation errors back to the AI so it can self-correct
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pdfplumber
from openai import OpenAI
from pydantic import ValidationError

from get_config import OPENAI_API_KEY
from invoices_generic_ai_parser.models import InvoiceResult

_SKILL_PATH = Path(__file__).parent / "skill.md"

# File types supported
_PDF_SUFFIXES = {".pdf"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Default number of retries on schema validation failure
DEFAULT_MAX_RETRIES: int = 2


def _load_skill() -> str:
    return _SKILL_PATH.read_text(encoding="utf-8")


def _extract_text_from_pdf(path: Path) -> str:
    """Extract all text from a PDF using pdfplumber."""
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


def _encode_image(path: Path) -> str:
    """Return a base64-encoded string of the image file."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _image_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")


def _build_retry_message(raw_json: str, error: ValidationError) -> dict:
    """
    Build an assistant + user message pair that feeds the validation errors
    back to the model so it can correct its own response.
    """
    error_summary = "; ".join(
        f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
        for e in error.errors()
    )
    return {
        "role": "user",
        "content": (
            f"Your previous response failed schema validation.\n"
            f"Invalid response was:\n{raw_json}\n\n"
            f"Validation errors:\n{error_summary}\n\n"
            "Please fix these errors and return a corrected JSON object."
        ),
    }


def parse_invoice(
    file_path: str | Path,
    client: OpenAI | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> InvoiceResult:
    """
    Parse a single invoice file (PDF or image) using the OpenAI API.
    Retries up to *max_retries* times if the response fails Pydantic validation,
    feeding the errors back to the model each time so it can self-correct.

    Parameters
    ----------
    file_path   : path to the invoice file
    client      : optional pre-built OpenAI client (useful for testing / DI)
    max_retries : number of additional attempts after the first failure (default 2)

    Returns
    -------
    InvoiceResult — validated Pydantic model

    Raises
    ------
    ValueError       – if the file type is unsupported or no text can be extracted
    ValidationError  – if all attempts exhaust without a valid response
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    skill = _load_skill()

    if client is None:
        client = OpenAI(api_key=OPENAI_API_KEY)

    # ── Build initial messages ──────────────────────────────────────────
    if suffix in _PDF_SUFFIXES:
        text = _extract_text_from_pdf(path)
        if not text:
            raise ValueError(f"No extractable text found in PDF: {path.name}")
        messages = [
            {"role": "system", "content": skill},
            {"role": "user", "content": text},
        ]

    elif suffix in _IMAGE_SUFFIXES:
        b64 = _encode_image(path)
        mime = _image_mime(path)
        messages = [
            {"role": "system", "content": skill},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    }
                ],
            },
        ]

    else:
        raise ValueError(
            f"Unsupported file type '{suffix}'. "
            f"Supported: {_PDF_SUFFIXES | _IMAGE_SUFFIXES}"
        )

    # ── Call OpenAI with retry loop ─────────────────────────────────────
    last_validation_error: ValidationError | None = None
    raw_json: str = ""

    for attempt in range(1 + max_retries):  # 1 initial + N retries
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=messages,
        )

        raw_json = response.choices[0].message.content

        # ── Parse & validate with Pydantic ──────────────────────────────
        try:
            data = json.loads(raw_json)
            return InvoiceResult(**data)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AI returned invalid JSON for {path.name}: {exc}"
            ) from exc

        except ValidationError as exc:
            last_validation_error = exc
            retry_num = attempt + 1
            remaining = max_retries - attempt

            if remaining > 0:
                print(
                    f"  ↻ Schema validation failed for {path.name} "
                    f"(attempt {retry_num}/{1 + max_retries}) — "
                    f"retrying ({remaining} left) …"
                )
                # Append the bad response + correction request to the conversation
                messages.append({"role": "assistant", "content": raw_json})
                messages.append(_build_retry_message(raw_json, exc))
            else:
                print(
                    f"  ✗ Schema validation failed for {path.name} after "
                    f"{1 + max_retries} attempt(s) — giving up."
                )

    # All attempts exhausted — surface the last validation error
    raise last_validation_error  # type: ignore[misc]
