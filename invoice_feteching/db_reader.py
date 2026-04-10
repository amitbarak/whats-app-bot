"""
db_reader.py
------------
Responsible for:
  - Defining the SQLAlchemy ORM model for srokbkUndefinedAttachments
  - Building the MSSQL engine (credentials loaded from .env via DB_USERNAME / DB_PASSWORD)
  - Querying the top-N latest attachments
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

# Load .env so DB_USERNAME / DB_PASSWORD are available
load_dotenv(_PROJECT_ROOT / ".env")


def load_config(config_path: Path = _CONFIG_PATH) -> dict:
    """Load and return the project-level YAML config."""
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class Base(DeclarativeBase):
    pass


class UndefinedAttachment(Base):
    __tablename__ = "srokbkUndefinedAttachments"

    ID = Column(Integer, primary_key=True, autoincrement=True)
    CustomerID = Column(String(255))
    CustomerName = Column(String(255))
    Email = Column(String(255), nullable=False)
    ImageData = Column(Text)
    ImagePath = Column(Text)
    IsSaved = Column(Integer)
    UploadDate = Column(Date)
    filename = Column(Text)
    fileType = Column(String(255))
    SenderEmail = Column(Text)
    Year = Column(String(255))
    originalFilename = Column(String(255))
    IsDelete = Column(Integer)
    IsDone = Column(Integer)
    EmailBody = Column(Text)
    EmailSubject = Column(Text)
    comment = Column(Text)
    label = Column(String(255))
    IsLogo = Column(Integer)
    FileSize = Column(String(255))
    HtmlString = Column(Text)
    Links = Column(Text)
    TypingTime = Column(DateTime)
    freetext = Column("freetext", Text)
    Postpone = Column(Integer)
    PostponeDate = Column(Date)
    IsDuplicate = Column(Integer)

    def __repr__(self) -> str:
        return (
            f"<UndefinedAttachment id={self.ID} "
            f"filename={self.filename!r} date={self.UploadDate}>"
        )


def build_engine(cfg: dict) -> Engine:
    """
    Build a SQLAlchemy engine from the *database* section of config.yaml.
    Credentials (username, password) are read from environment variables:
      DB_USERNAME, DB_PASSWORD  (typically set via .env)

    Expected config keys: server, port, database, driver
    """
    db = cfg["database"]

    username = os.environ.get("DB_USERNAME")
    password = os.environ.get("DB_PASSWORD")

    if not username or not password:
        raise EnvironmentError(
            "DB_USERNAME and DB_PASSWORD must be set in the environment "
            "(add them to your .env file)."
        )

    driver_encoded = urllib.parse.quote_plus(db["driver"])
    connection_string = (
        f"mssql+pyodbc://{urllib.parse.quote_plus(username)}"
        f":{urllib.parse.quote_plus(password)}"
        f"@{db['server']}:{db['port']}/{db['database']}"
        f"?driver={driver_encoded}"
    )
    return create_engine(connection_string, fast_executemany=True)


def fetch_latest_attachments(
    session: Session,
    top_n: int = 100,
    exclude_deleted: bool = True,
) -> list[UndefinedAttachment]:
    """
    Return the *top_n* most-recent rows ordered by UploadDate DESC.

    Parameters
    ----------
    session         : active SQLAlchemy session
    top_n           : number of rows to fetch (default 100)
    exclude_deleted : when True, rows with IsDelete=1 are skipped
    """
    stmt = select(UndefinedAttachment).where(
        UndefinedAttachment.filename.isnot(None)
    )
    if exclude_deleted:
        stmt = stmt.where(
            (UndefinedAttachment.IsDelete == 0)
            | (UndefinedAttachment.IsDelete.is_(None))
        )
    stmt = stmt.order_by(UndefinedAttachment.UploadDate.desc()).limit(top_n)
    return list(session.scalars(stmt))
