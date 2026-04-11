"""
run_invoices.py
---------------
Main entry point:
  1. Downloads the 100 latest invoices from the MSSQL database to a local folder
     (via invoice_feteching.InvoicePipeline)
  2. Parses every downloaded file with the AI and validates with Pydantic
     (via invoices_generic_ai_parser.InvoiceParsePipeline)
  3. Writes all parsed results to:
        invoices_generic_ai_parser/parsed_json/parsed_invoices.json

Usage:
    python run_invoices.py
    python run_invoices.py --n 50        # override number of invoices
"""

from __future__ import annotations

import argparse
from pathlib import Path

from invoice_feteching.invoice_pipeline import InvoicePipeline
from invoices_generic_ai_parser.pipeline import InvoiceParsePipeline

_PROJECT_ROOT = Path(__file__).resolve().parent
_DOWNLOAD_FOLDER = _PROJECT_ROOT / "invoice_feteching" / "downloaded_files"
_OUTPUT_DIR = _PROJECT_ROOT / "invoices_generic_ai_parser" / "parsed_json"

N = 20


def main(n: int = N) -> None:
    # ── Step 1: Download invoices from the database ──────────────────────
    print("=" * 60)
    print(f"STEP 1 — Downloading {n} invoices from the database")
    print("=" * 60)

    fetch_pipeline = InvoicePipeline(config_path=_PROJECT_ROOT / "config.yaml")
    fetch_pipeline.top_n = n
    fetch_pipeline.download_folder = _DOWNLOAD_FOLDER
    fetch_pipeline.file_fetcher.download_folder = _DOWNLOAD_FOLDER
    fetch_pipeline.run()

    # ── Step 2: Parse downloaded invoices with AI ─────────────────────────
    print()
    print("=" * 60)
    print(f"STEP 2 — Parsing {n} invoices with AI")
    print("=" * 60)

    parse_pipeline = InvoiceParsePipeline(
        folder=_DOWNLOAD_FOLDER,
        n=n,
        output_dir=_OUTPUT_DIR,
    )
    outcome = parse_pipeline.run()

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("DONE")
    print(f"  Parsed successfully : {len(outcome['results'])}")
    print(f"  Errors              : {len(outcome['errors'])}")
    if outcome["out_file"]:
        print(f"  Results saved to    : {outcome['out_file']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and parse N invoices")
    parser.add_argument("--n", type=int, default=N, help="Number of invoices (default 100)")
    args = parser.parse_args()
    main(n=args.n)
