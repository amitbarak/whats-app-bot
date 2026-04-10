import json
import os
from pathlib import Path

import pdfplumber
from openai import OpenAI

from get_config import OPENAI_API_KEY

_SKILL_PATH = Path(__file__).parent / "invoice_skill.md"
_DEFAULT_OUTPUT_DIR = Path(__file__).parent / "parsed_json"


def _extract_text_from_pdf(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


def _load_skill() -> str:
    return _SKILL_PATH.read_text(encoding="utf-8")


def parse_invoice_to_json(pdf_path: str, output_dir: str | None = None) -> dict:
    text = _extract_text_from_pdf(pdf_path)
    if not text:
        raise ValueError(f"No extractable text found in {pdf_path}")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _load_skill()},
            {"role": "user", "content": text},
        ],
    )

    data = json.loads(response.choices[0].message.content)

    out_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{Path(pdf_path).stem}.json"
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data
