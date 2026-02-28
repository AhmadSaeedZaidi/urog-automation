import pandas as pd
import os
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
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
    def __init__(self, credentials_file: Optional[str] = None):
        self.credentials_file = credentials_file

    def load(self, spreadsheet_id: str, source_name: Optional[str] = None) -> str:
        """
        To be implemented with google-api-python-client.
        Accepts a spreadsheet_id and assumes 'Sheet1' or iterates sheets.
        """
        print(f"Connecting to Google Sheets ID: {spreadsheet_id}...")

        # Placeholder for API Logic:
        # 1. Auth with self.credentials_file
        # 2. service.spreadsheets().values().get(...)
        # 3. Convert List[List] to DataFrame

        # For now, we raise to indicate it needs the API library setup
        raise NotImplementedError(
            "Google Sheets API integration pending setup of credentials."
        )


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
