import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd
from dao import db


class BaseLoader(ABC):
    """
    Abstract Base Class for all data loaders.
    Enforces a standard 'load' method and provides shared utilities.
    """

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize headers:
        - Lowercase, Strip spaces, Replace spaces with underscores
        - Fill NaNs with empty strings (JSON requirement)
        """
        # Ensure we are working with strings for columns
        df.columns = (
            df.columns.astype(str).str.lower().str.strip().str.replace(" ", "_")
        )
        df = df.fillna("")
        return df

    def _push_to_inbox(
        self, records: List[Dict[str, Any]], source_name: str, source_type: str
    ) -> str:
        """
        Helper: Pushes the processed list of dicts to the DAO Bronze Layer.
        """
        if not records:
            print(f"Warning: No records found in {source_name}")
            return None

        print(
            f"Uploading {len(records)} records from '{source_name}' ({source_type}) to Data Inbox..."
        )

        inbox_id = db.ingest_raw(
            source_name=source_name, source_type=source_type, payload=records
        )

        print(f"Success! Inbox ID: {inbox_id}")
        return inbox_id

    @abstractmethod
    def load(self, source: Any, source_name: Optional[str] = None) -> str:
        """
        Implementation must return the inbox_id (UUID string).
        """
        pass


# ==========================================
# Concrete Loaders
# ==========================================


class CsvLoader(BaseLoader):
    def load(self, file_path: str, source_name: Optional[str] = None) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        print(f"Reading CSV {file_path}...")
        df = pd.read_csv(file_path)

        df = self.clean_dataframe(df)
        records = df.to_dict(orient="records")

        if not source_name:
            source_name = os.path.basename(file_path)

        return self._push_to_inbox(records, source_name, "csv")


class ExcelLoader(BaseLoader):
    def load(self, file_path: str, source_name: Optional[str] = None) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Note: Requires 'openpyxl' installed
        print(f"Reading Excel {file_path}...")
        df = pd.read_excel(file_path)

        df = self.clean_dataframe(df)
        records = df.to_dict(orient="records")

        if not source_name:
            source_name = os.path.basename(file_path)

        return self._push_to_inbox(records, source_name, "excel")


class GoogleSheetsLoader(BaseLoader):
    """
    Read data from a Google Spreadsheet and push it to the DAO inbox.

    Authentication uses a **service-account** JSON key file pointed to by
    ``credentials_file`` (or the ``GOOGLE_CREDENTIALS_FILE`` env-var).
    """

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    def __init__(self, credentials_file: Optional[str] = None):
        self.credentials_file = (
            credentials_file
            or os.getenv("GOOGLE_CREDENTIALS_FILE")
            or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "..",
                "..",
                "..",
                "google_credentials.json",
            )
        )
        # Resolve to an absolute, canonical path
        self.credentials_file = os.path.realpath(self.credentials_file)

    # ------------------------------------------------------------------
    # Internal helpers (each can be independently mocked in tests)
    # ------------------------------------------------------------------

    def _build_service(self):
        """Authenticate and return a Sheets API v4 service object."""
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not self.credentials_file or not os.path.isfile(self.credentials_file):
            raise EnvironmentError(
                f"Google credentials file not found: {self.credentials_file!r}. "
                "Set GOOGLE_CREDENTIALS_FILE or place google_credentials.json "
                "at the project root."
            )

        creds = Credentials.from_service_account_file(
            self.credentials_file, scopes=self.SCOPES
        )
        return build("sheets", "v4", credentials=creds)

    def _fetch_rows(self, service, spreadsheet_id: str, range_name: str = "Sheet1"):
        """Fetch all rows from *range_name* and return as list-of-lists."""
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        return result.get("values", [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, spreadsheet_id: str, source_name: Optional[str] = None) -> str:
        """
        Read *Sheet1* of the given Google Spreadsheet, convert to a
        cleaned DataFrame, and push to the DAO inbox.
        """
        print(f"Connecting to Google Sheets ID: {spreadsheet_id}...")

        service = self._build_service()
        rows = self._fetch_rows(service, spreadsheet_id)

        if not rows or len(rows) < 2:
            print(f"Warning: No data rows found in sheet {spreadsheet_id}")
            return None

        # First row = headers, rest = data
        headers = rows[0]
        data = rows[1:]
        df = pd.DataFrame(data, columns=headers)
        df = self.clean_dataframe(df)
        records = df.to_dict(orient="records")

        if not source_name:
            source_name = f"gsheet-{spreadsheet_id}"

        return self._push_to_inbox(records, source_name, "gsheets")


# ==========================================
# Factory & Legacy Support
# ==========================================


class LoaderFactory:
    @staticmethod
    def get_loader(source_type: str) -> BaseLoader:
        loaders = {
            "csv": CsvLoader(),
            "excel": ExcelLoader(),
            "gsheets": GoogleSheetsLoader(),
        }
        loader = loaders.get(source_type)
        if not loader:
            raise ValueError(f"No loader found for type: {source_type}")
        return loader


# Backward compatibility wrapper
def ingest_csv(file_path, source_name=None):
    return CsvLoader().load(file_path, source_name)
