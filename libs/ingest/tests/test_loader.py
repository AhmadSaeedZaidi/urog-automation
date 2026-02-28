"""Tests for BaseLoader data cleaning and CsvLoader/ExcelLoader logic."""

import pytest
import pandas as pd
from ingest.loader import CsvLoader, ExcelLoader, LoaderFactory


# --------------------------------------------------
# BaseLoader cleaning tests (using CsvLoader as concrete impl)
# --------------------------------------------------


class TestBaseLoaderCleaning:
    """Test the shared clean_dataframe method."""

    def setup_method(self):
        self.loader = CsvLoader()

    def test_headers_lowercased(self, sample_dataframe):
        """Column names should be lowercased."""
        cleaned = self.loader.clean_dataframe(sample_dataframe)
        for col in cleaned.columns:
            assert col == col.lower()

    def test_headers_stripped(self, sample_dataframe):
        """Leading/trailing spaces should be removed from headers."""
        cleaned = self.loader.clean_dataframe(sample_dataframe)
        for col in cleaned.columns:
            assert col == col.strip()

    def test_spaces_replaced_with_underscores(self, sample_dataframe):
        """Spaces in headers should become underscores."""
        cleaned = self.loader.clean_dataframe(sample_dataframe)
        for col in cleaned.columns:
            assert " " not in col

    def test_nans_filled_with_empty_string(self, sample_dataframe_with_nans):
        """NaN values should become empty strings for JSON safety."""
        cleaned = self.loader.clean_dataframe(sample_dataframe_with_nans)
        assert cleaned.isna().sum().sum() == 0
        # Check a specific NaN was replaced
        assert cleaned.iloc[1]["name"] == ""

    def test_clean_preserves_valid_data(self, sample_dataframe):
        """Valid data values should not be altered."""
        cleaned = self.loader.clean_dataframe(sample_dataframe)
        assert cleaned.iloc[0]["email"] == "alice@example.com"

    def test_clean_returns_dataframe(self, sample_dataframe):
        """clean_dataframe should return a DataFrame."""
        result = self.loader.clean_dataframe(sample_dataframe)
        assert isinstance(result, pd.DataFrame)


class TestBaseLoaderPushToInbox:
    """Test the _push_to_inbox helper."""

    def setup_method(self):
        self.loader = CsvLoader()

    def test_push_to_inbox_calls_ingest_raw(self, mock_dao_db):
        """Should call db.ingest_raw with correct args."""
        records = [{"email": "a@test.com"}]
        result = self.loader._push_to_inbox(records, "test_source", "csv")

        mock_dao_db.ingest_raw.assert_called_once_with(
            source_name="test_source", source_type="csv", payload=records
        )
        assert result == "inbox-uuid-001"

    def test_push_to_inbox_empty_records_returns_none(self, mock_dao_db):
        """Empty record list should return None without calling DB."""
        result = self.loader._push_to_inbox([], "empty_source", "csv")
        assert result is None
        mock_dao_db.ingest_raw.assert_not_called()


# --------------------------------------------------
# CsvLoader tests
# --------------------------------------------------


class TestCsvLoader:
    """Test CsvLoader.load()."""

    def test_load_reads_and_ingests_csv(self, tmp_path, mock_dao_db):
        """Full CSV load: read file -> clean -> push to inbox."""
        csv_file = tmp_path / "students.csv"
        csv_file.write_text("Name,Email,Major\nAlice,alice@test.com,CS\n")

        loader = CsvLoader()
        result = loader.load(str(csv_file))

        assert result == "inbox-uuid-001"
        mock_dao_db.ingest_raw.assert_called_once()

        # Verify the payload was cleaned (lowercase headers)
        call_args = mock_dao_db.ingest_raw.call_args
        payload = call_args[1]["payload"]
        assert payload[0]["name"] == "Alice"
        assert payload[0]["email"] == "alice@test.com"
        assert "Name" not in payload[0]  # original header should not exist

    def test_load_uses_filename_as_source_name(self, tmp_path, mock_dao_db):
        """Default source_name should be the file basename."""
        csv_file = tmp_path / "my_data.csv"
        csv_file.write_text("Email\na@b.com\n")

        CsvLoader().load(str(csv_file))
        call_args = mock_dao_db.ingest_raw.call_args
        assert call_args[1]["source_name"] == "my_data.csv"

    def test_load_custom_source_name(self, tmp_path, mock_dao_db):
        """Explicit source_name should override the default."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("Email\na@b.com\n")

        CsvLoader().load(str(csv_file), source_name="Custom Import")
        call_args = mock_dao_db.ingest_raw.call_args
        assert call_args[1]["source_name"] == "Custom Import"

    def test_load_file_not_found_raises(self):
        """Missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            CsvLoader().load("/nonexistent/path.csv")

    def test_load_handles_nan_values(self, tmp_path, mock_dao_db):
        """NaN cells in CSV should become empty strings in payload."""
        csv_file = tmp_path / "gaps.csv"
        csv_file.write_text("Name,Email,GPA\nAlice,a@b.com,\n")

        CsvLoader().load(str(csv_file))
        payload = mock_dao_db.ingest_raw.call_args[1]["payload"]
        assert payload[0]["gpa"] == ""


# --------------------------------------------------
# ExcelLoader tests
# --------------------------------------------------


class TestExcelLoader:
    """Test ExcelLoader.load()."""

    def test_load_file_not_found_raises(self):
        """Missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            ExcelLoader().load("/nonexistent/file.xlsx")

    def test_load_reads_excel(self, tmp_path, mock_dao_db):
        """ExcelLoader should read .xlsx and push to inbox."""
        xlsx_file = tmp_path / "data.xlsx"
        df = pd.DataFrame({"Name": ["Alice"], "Email": ["alice@test.com"]})
        df.to_excel(str(xlsx_file), index=False)

        result = ExcelLoader().load(str(xlsx_file))
        assert result == "inbox-uuid-001"
        mock_dao_db.ingest_raw.assert_called_once()


# --------------------------------------------------
# LoaderFactory tests
# --------------------------------------------------


class TestLoaderFactory:
    """Test the factory that returns loaders by type."""

    def test_get_csv_loader(self):
        loader = LoaderFactory.get_loader("csv")
        assert isinstance(loader, CsvLoader)

    def test_get_excel_loader(self):
        loader = LoaderFactory.get_loader("excel")
        assert isinstance(loader, ExcelLoader)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="No loader found"):
            LoaderFactory.get_loader("unknown_format")
