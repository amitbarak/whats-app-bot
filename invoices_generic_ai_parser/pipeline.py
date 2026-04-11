"""
pipeline.py
-----------
Reads up to N invoice files from a folder, sends each to the AI parser,
validates the response with Pydantic, and writes all results to a JSON file.

Usage (standalone):
    python -m invoices_generic_ai_parser.pipeline --folder path/to/invoices --n 10

Usage (from code):
    from invoices_generic_ai_parser.pipeline import InvoiceParsePipeline

    pipeline = InvoiceParsePipeline(folder="invoice_feteching/downloaded_files", n=10)
    results  = pipeline.run()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from openai import OpenAI
from pydantic import ValidationError

from invoices_generic_ai_parser.ai_parser import (
    _IMAGE_SUFFIXES,
    _PDF_SUFFIXES,
    parse_invoice,
)
from invoices_generic_ai_parser.models import InvoiceResult

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_FOLDER = _PROJECT_ROOT / "invoice_feteching" / "downloaded_files"
_DEFAULT_OUTPUT = Path(__file__).parent / "parsed_json"

_SUPPORTED_SUFFIXES = _PDF_SUFFIXES | _IMAGE_SUFFIXES


class InvoiceParsePipeline:
    """
    Orchestrates batch invoice parsing.

    Parameters
    ----------
    folder  : directory containing invoice files (PDFs / images)
    n       : maximum number of invoices to process
    output_dir : where to write the combined JSON result file
    client  : optional pre-built OpenAI client (for DI / testing)
    """

    def __init__(
        self,
        folder: str | Path = _DEFAULT_FOLDER,
        n: int = 10,
        output_dir: str | Path = _DEFAULT_OUTPUT,
        client: Optional[OpenAI] = None,
    ) -> None:
        self.folder = Path(folder)
        self.n = n
        self.output_dir = Path(output_dir)
        self.client = client

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------
    def collect_files(self) -> list[Path]:
        """
        Return up to *n* supported invoice files from *folder*,
        sorted by modification time (newest first).
        """
        files = [
            f for f in self.folder.iterdir()
            if f.is_file() and f.suffix.lower() in _SUPPORTED_SUFFIXES
        ]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files[: self.n]

    # ------------------------------------------------------------------
    # Parsing step
    # ------------------------------------------------------------------
    def parse_files(self, files: list[Path]) -> tuple[list[InvoiceResult], list[dict]]:
        """
        Parse each file with the AI and validate with Pydantic.

        Returns
        -------
        (results, errors)
          results – list of successfully parsed InvoiceResult objects
          errors  – list of dicts describing failures
        """
        results: list[InvoiceResult] = []
        errors: list[dict] = []

        total = len(files)
        for idx, path in enumerate(files, start=1):
            print(f"[{idx}/{total}] Parsing {path.name} …")
            try:
                result = parse_invoice(path, client=self.client)
                results.append(result)
                print(
                    f"         ✓  Asm={result.Asm}  "
                    f"sum={result.sum}  maam={result.maam_amount}"
                )
            except ValidationError as exc:
                print(f"         ✗  Validation error: {exc.error_count()} issue(s)")
                errors.append({"file": path.name, "error": "validation", "detail": str(exc)})
            except Exception as exc:
                print(f"         ✗  {type(exc).__name__}: {exc}")
                errors.append({"file": path.name, "error": type(exc).__name__, "detail": str(exc)})

        return results, errors

    # ------------------------------------------------------------------
    # Write output
    # ------------------------------------------------------------------
    def write_results(self, results: list[InvoiceResult], errors: list[dict]) -> Path:
        """
        Write all parsed results and any errors to a single JSON file.

        Returns the path of the written file.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_file = self.output_dir / "parsed_invoices.json"

        payload = {
            "total_parsed": len(results),
            "total_errors": len(errors),
            "invoices": [r.to_dict() for r in results],
            "errors": errors,
        }

        out_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nSaved {len(results)} invoice(s) → {out_file}")
        return out_file

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    def run(self) -> dict:
        """
        Execute the full pipeline end-to-end.

        Returns
        -------
        dict with keys:
          results  – list[InvoiceResult]
          errors   – list[dict]
          out_file – Path of the written JSON file
        """
        if not self.folder.exists():
            raise FileNotFoundError(f"Invoice folder not found: {self.folder}")

        files = self.collect_files()
        if not files:
            print(f"No supported invoice files found in {self.folder}")
            return {"results": [], "errors": [], "out_file": None}

        print(f"Found {len(files)} file(s) to parse (n={self.n})\n")
        results, errors = self.parse_files(files)
        out_file = self.write_results(results, errors)

        return {"results": results, "errors": errors, "out_file": out_file}


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse N invoices with AI")
    parser.add_argument(
        "--folder",
        default=str(_DEFAULT_FOLDER),
        help="Folder containing invoice files",
    )
    parser.add_argument(
        "--n", type=int, default=10, help="Maximum number of invoices to parse"
    )
    args = parser.parse_args()

    pipeline = InvoiceParsePipeline(folder=args.folder, n=args.n)
    pipeline.run()
