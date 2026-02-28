"""Tests for GoogleSheetsLoader — all Google API calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest
from ingest.loader import GoogleSheetsLoader


# --------------------------------------------------
# Helper: build a mock Sheets service
# --------------------------------------------------


def _mock_sheets_service(rows):
    """Return a mock service where spreadsheets().values().get().execute()
    yields ``{"values": rows}``."""
    mock_service = MagicMock()
    mock_execute = MagicMock(return_value={"values": rows})
    mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute = mock_execute
    return mock_service


# --------------------------------------------------
# Tests
# --------------------------------------------------


class TestGoogleSheetsLoaderInit:
    """Test constructor and credential handling."""

    def test_uses_explicit_credentials_file(self):
        loader = GoogleSheetsLoader(credentials_file="/path/to/creds.json")
        assert loader.credentials_file == "/path/to/creds.json"

    @patch.dict("os.environ", {"GOOGLE_CREDENTIALS_FILE": "/env/creds.json"})
    def test_falls_back_to_env_var(self):
        loader = GoogleSheetsLoader()
        assert loader.credentials_file == "/env/creds.json"

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_raises_on_build(self):
        loader = GoogleSheetsLoader(credentials_file="/nonexistent/path.json")
        with pytest.raises(EnvironmentError, match="credentials file not found"):
            loader._build_service()


class TestGoogleSheetsLoaderLoad:
    """Test load() with a fully mocked Google API service."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_dao_db):
        """Store the mock db so individual tests can inspect it."""
        self.mock_db = mock_dao_db

    def _make_loader_with_service(self, rows):
        """Build a GoogleSheetsLoader whose _build_service returns a mock."""
        loader = GoogleSheetsLoader(credentials_file="/fake/creds.json")
        svc = _mock_sheets_service(rows)
        loader._build_service = MagicMock(return_value=svc)
        return loader

    # ------- happy path -------

    def test_load_fetches_and_ingests(self):
        """Rows from the sheet should be pushed to the inbox."""
        rows = [
            ["Name", "Email", "Major"],
            ["Alice", "alice@test.com", "CS"],
            ["Bob", "bob@test.com", "EE"],
        ]
        loader = self._make_loader_with_service(rows)
        result = loader.load("spreadsheet-id-123")

        assert result == "inbox-uuid-001"
        self.mock_db.ingest_raw.assert_called_once()
        payload = self.mock_db.ingest_raw.call_args[1]["payload"]
        assert len(payload) == 2
        # Headers should be cleaned (lowercased)
        assert payload[0]["name"] == "Alice"
        assert payload[0]["email"] == "alice@test.com"

    def test_load_cleans_headers(self):
        """Messy headers should still be normalised."""
        rows = [
            ["  Full Name ", " EMAIL ADDRESS"],
            ["Alice", "alice@test.com"],
        ]
        loader = self._make_loader_with_service(rows)
        loader.load("spreadsheet-id-456")

        payload = self.mock_db.ingest_raw.call_args[1]["payload"]
        assert "full_name" in payload[0]
        assert "email_address" in payload[0]

    def test_load_uses_default_source_name(self):
        """Default source_name should include the spreadsheet id."""
        rows = [["A"], ["1"]]
        loader = self._make_loader_with_service(rows)
        loader.load("my-sheet-id")

        source = self.mock_db.ingest_raw.call_args[1]["source_name"]
        assert "my-sheet-id" in source

    def test_load_custom_source_name(self):
        rows = [["A"], ["1"]]
        loader = self._make_loader_with_service(rows)
        loader.load("id-1", source_name="Custom Name")

        source = self.mock_db.ingest_raw.call_args[1]["source_name"]
        assert source == "Custom Name"

    # ------- edge cases -------

    def test_load_empty_sheet_returns_none(self):
        """An empty sheet (no rows at all) should return None."""
        loader = self._make_loader_with_service([])
        result = loader.load("empty-id")
        assert result is None
        self.mock_db.ingest_raw.assert_not_called()

    def test_load_header_only_returns_none(self):
        """A sheet with only a header row (no data) should return None."""
        loader = self._make_loader_with_service([["A", "B"]])
        result = loader.load("header-only-id")
        assert result is None
        self.mock_db.ingest_raw.assert_not_called()

    def test_load_source_type_is_gsheets(self):
        """The source_type pushed to inbox should be 'gsheets'."""
        rows = [["X"], ["1"]]
        loader = self._make_loader_with_service(rows)
        loader.load("id-x")

        stype = self.mock_db.ingest_raw.call_args[1]["source_type"]
        assert stype == "gsheets"


class TestBuildService:
    """Test _build_service in isolation (mocking google libs)."""

    @patch("ingest.loader.GoogleSheetsLoader._build_service")
    def test_build_service_called_during_load(self, mock_build):
        """load() must call _build_service exactly once."""
        mock_svc = _mock_sheets_service([["H"], ["D"]])
        mock_build.return_value = mock_svc

        loader = GoogleSheetsLoader(credentials_file="/fake/creds.json")
        loader._build_service = mock_build
        loader.load("any-id")

        mock_build.assert_called_once()
