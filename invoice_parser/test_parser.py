import glob
import json
from pathlib import Path

from invoice_parser.pdf_invoice_parser import parse_invoice_to_json

INVOICES_DIR = Path(__file__).parent.parent / "real life invoices"


def main():
    pdfs = sorted(glob.glob(str(INVOICES_DIR / "*.pdf")))
    if not pdfs:
        print(f"No PDFs found in {INVOICES_DIR}")
        return

    for pdf_path in pdfs:
        print(f"\n{'='*50}")
        print(f"Parsing: {Path(pdf_path).name}")
        try:
            result = parse_invoice_to_json(pdf_path)
            out_file = Path(__file__).parent / "parsed_json" / f"{Path(pdf_path).stem}.json"
            print(f"  invoice_number  : {result.get('invoice_number')}")
            print(f"  date            : {result.get('year')}-{result.get('month'):02d}-{result.get('day'):02d}")
            print(f"  sum_before_maam : {result.get('sum_before_maam')} ₪")
            print(f"  sum_maam        : {result.get('sum_maam')} ₪")
            print(f"  supplier_id     : {result.get('supplier_customer_id')}")
            print(f"  type            : {result.get('data_base_raw_type')}")
            print(f"  saved to        : {out_file}")
        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
