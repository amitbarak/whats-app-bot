"""
invoice_pipeline.py
-------------------
InvoicePipeline combines DbReader and FileFetcher into a single high-level
interface.  All configuration is read from <project_root>/config.yaml.

Usage (standalone):
    python -m invoice_feteching.invoice_pipeline

Usage (from code):
    from invoice_feteching.invoice_pipeline import InvoicePipeline

    pipeline = InvoicePipeline()
    results  = pipeline.run()
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from invoice_feteching.db_reader import (
    UndefinedAttachment,
    build_engine,
    fetch_latest_attachments,
    load_config,
)
from invoice_feteching.file_fetcher import FileFetcher

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"


class InvoicePipeline:
    """
    Orchestrates the full invoice-fetching pipeline:

      1. Load config.yaml
      2. Connect to MSSQL via SQLAlchemy
      3. Query the top-N latest attachments (DbReader)
      4. Download them from Azure Blob Storage (FileFetcher)

    Parameters
    ----------
    config_path : path to the project-level config.yaml
                  (defaults to <project_root>/config.yaml)
    """

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        self.config_path = config_path
        self.cfg = load_config(config_path)

        # -- resolve settings from config ----------------------------------
        fetching_cfg = self.cfg.get("invoice_fetching", {})
        self.top_n: int = fetching_cfg.get("top_n", 100)

        download_folder = Path(fetching_cfg.get("download_folder", "invoice_feteching/downloaded_files"))
        if not download_folder.is_absolute():
            download_folder = _PROJECT_ROOT / download_folder
        self.download_folder = download_folder

        base_url: str = self.cfg["blob_storage"]["base_url"]

        # -- build collaborators -------------------------------------------
        self.engine = build_engine(self.cfg)
        self.file_fetcher = FileFetcher(
            base_url=base_url,
            download_folder=self.download_folder,
        )

    # ------------------------------------------------------------------
    # Query step (exposed separately for flexibility)
    # ------------------------------------------------------------------
    def fetch_records(self, exclude_deleted: bool = True) -> list[UndefinedAttachment]:
        """Query the database and return the top-N attachment records."""
        print(f"Querying top {self.top_n} latest attachments from the database...")
        with Session(self.engine) as session:
            records = fetch_latest_attachments(
                session,
                top_n=self.top_n,
                exclude_deleted=exclude_deleted,
            )
        print(f"Found {len(records)} record(s).")
        return records

    # ------------------------------------------------------------------
    # Download step (exposed separately for flexibility)
    # ------------------------------------------------------------------
    def download_files(self, records: list[UndefinedAttachment]) -> dict:
        """Download the given attachment records to the local folder."""
        return self.file_fetcher.download(records)

    # ------------------------------------------------------------------
    # Combined pipeline
    # ------------------------------------------------------------------
    def run(self, exclude_deleted: bool = True) -> dict:
        """
        Execute the full pipeline end-to-end.

        Returns the download results dict:
            {"success": [...], "failed": [...]}
        """
        records = self.fetch_records(exclude_deleted=exclude_deleted)
        return self.download_files(records)


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    InvoicePipeline().run()
