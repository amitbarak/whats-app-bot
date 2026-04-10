"""
file_fetcher.py
---------------
Responsible for:
  - Building blob-storage URLs from a base URL + filename
  - Downloading files from Azure Blob Storage into a local folder
  - Clearing the destination folder before each batch download
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

from invoice_feteching.db_reader import UndefinedAttachment


class FileFetcher:
    """
    Downloads attachment files from Azure Blob Storage.

    Parameters
    ----------
    base_url        : root of the blob container
                      e.g. "https://ronen.blob.core.windows.net/srokbk"
    download_folder : local Path where files will be saved
    timeout         : per-request HTTP timeout in seconds
    """

    def __init__(
        self,
        base_url: str,
        download_folder: Path,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.download_folder = Path(download_folder)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # URL construction
    # ------------------------------------------------------------------
    def build_url(self, filename: str) -> str:
        """Return the full blob URL for a given filename."""
        return f"{self.base_url}/{filename}"

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------
    def _prepare_folder(self) -> None:
        """Create the download folder (if needed) and empty it."""
        self.download_folder.mkdir(parents=True, exist_ok=True)
        for existing in self.download_folder.iterdir():
            if existing.is_file():
                existing.unlink()

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def _resolve_local_name(self, attachment: UndefinedAttachment) -> str:
        """
        Choose a human-readable local filename.
        Prefers originalFilename; falls back to the blob filename basename.
        """
        return attachment.originalFilename or os.path.basename(
            attachment.filename  # type: ignore[arg-type]
        )

    def _unique_path(self, name: str, row_id: int) -> Path:
        """Return a destination Path that doesn't clash with existing files."""
        dest = self.download_folder / name
        if dest.exists():
            stem, suffix = os.path.splitext(name)
            dest = self.download_folder / f"{stem}_{row_id}{suffix}"
        return dest

    def download(self, attachments: list[UndefinedAttachment]) -> dict:
        """
        Download every attachment in *attachments* into *download_folder*.

        The folder is emptied first so it always contains exactly the
        latest batch.

        Returns
        -------
        dict with keys "success" and "failed" (lists of filenames)
        """
        self._prepare_folder()

        total = len(attachments)
        print(f"Downloading {total} file(s) → {self.download_folder}")

        results: dict[str, list[str]] = {"success": [], "failed": []}

        for idx, attachment in enumerate(attachments, start=1):
            filename: str = attachment.filename  # type: ignore[assignment]
            url = self.build_url(filename)
            local_name = self._resolve_local_name(attachment)
            dest_path = self._unique_path(local_name, attachment.ID)  # type: ignore[arg-type]

            try:
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                dest_path.write_bytes(response.content)
                print(f"  [{idx}/{total}] ✓  {local_name}")
                results["success"].append(local_name)
            except requests.HTTPError as exc:
                print(
                    f"  [{idx}/{total}] ✗  HTTP {exc.response.status_code}  {url}"
                )
                results["failed"].append(local_name)
            except requests.RequestException as exc:
                print(f"  [{idx}/{total}] ✗  {url}  →  {exc}")
                results["failed"].append(local_name)

        print(
            f"\nDone. {len(results['success'])} downloaded, "
            f"{len(results['failed'])} failed."
        )
        return results
