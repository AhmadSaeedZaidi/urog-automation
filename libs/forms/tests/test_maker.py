"""Tests for WorkspaceMaker — all Google API calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest
from forms.maker import WorkspaceMaker


# --------------------------------------------------
# Init & credential tests
# --------------------------------------------------


class TestWorkspaceMakerInit:
    def test_explicit_credentials(self):
        maker = WorkspaceMaker(credentials_file="/path/to/creds.json")
        assert maker.credentials_file == "/path/to/creds.json"

    @patch.dict("os.environ", {"GOOGLE_CREDENTIALS_FILE": "/env/creds.json"})
    def test_env_var_fallback(self):
        maker = WorkspaceMaker()
        assert maker.credentials_file == "/env/creds.json"

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_raises_on_build_sheets(self):
        maker = WorkspaceMaker(credentials_file="/nonexistent/path.json")
        with pytest.raises(EnvironmentError, match="credentials file not found"):
            maker._build_sheets_service()

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_raises_on_build_drive(self):
        maker = WorkspaceMaker(credentials_file="/nonexistent/path.json")
        with pytest.raises(EnvironmentError, match="credentials file not found"):
            maker._build_drive_service()


# --------------------------------------------------
# create_spreadsheet
# --------------------------------------------------


class TestCreateSpreadsheet:
    @pytest.fixture(autouse=True)
    def _patch_service(self, mock_sheets_service):
        """Inject the mock sheets service into every test."""
        self.mock_svc = mock_sheets_service
        self.maker = WorkspaceMaker(credentials_file="/fake/creds.json")
        self.maker._build_sheets_service = MagicMock(return_value=self.mock_svc)

    def test_returns_id_and_url(self):
        result = self.maker.create_spreadsheet("Test Sheet")
        assert result["spreadsheet_id"] == "new-sheet-id-001"
        assert "docs.google.com" in result["url"]

    def test_calls_create_with_title(self):
        self.maker.create_spreadsheet("My Title")
        create_call = self.mock_svc.spreadsheets.return_value.create
        body = create_call.call_args[1]["body"]
        assert body["properties"]["title"] == "My Title"

    def test_no_headers_skips_update(self):
        """If no headers are provided, values().update() should not be called."""
        self.maker.create_spreadsheet("No Headers")
        update_call = self.mock_svc.spreadsheets.return_value.values.return_value.update
        update_call.assert_not_called()

    def test_with_headers_writes_first_row(self):
        """If headers are provided, they should be written to Sheet1!A1."""
        headers = ["Name", "Email", "Major"]
        self.maker.create_spreadsheet("With Headers", sheet_headers=headers)

        update_call = self.mock_svc.spreadsheets.return_value.values.return_value.update
        update_call.assert_called_once()
        kw = update_call.call_args[1]
        assert kw["range"] == "Sheet1!A1"
        assert kw["body"]["values"] == [headers]

    def test_build_service_called_once(self):
        self.maker.create_spreadsheet("One Call")
        self.maker._build_sheets_service.assert_called_once()


# --------------------------------------------------
# create_form (stub)
# --------------------------------------------------


class TestCreateForm:
    def test_returns_stub_result(self):
        maker = WorkspaceMaker(credentials_file="/fake/creds.json")
        result = maker.create_form("Applicant Form")
        assert "form_id" in result
        assert "url" in result
        assert "stub" in result["form_id"]

    def test_url_is_google_forms_link(self):
        maker = WorkspaceMaker(credentials_file="/fake/creds.json")
        result = maker.create_form("Test")
        assert "docs.google.com/forms" in result["url"]


# --------------------------------------------------
# create_opportunity_sheet
# --------------------------------------------------


class TestCreateOpportunitySheet:
    @pytest.fixture(autouse=True)
    def _patch_services(self, mock_sheets_service, mock_drive_service):
        """Inject both mocked services."""
        self.mock_sheets = mock_sheets_service
        self.mock_drive = mock_drive_service
        self.maker = WorkspaceMaker(credentials_file="/fake/creds.json")
        self.maker._build_sheets_service = MagicMock(return_value=self.mock_sheets)
        self.maker._build_drive_service = MagicMock(return_value=self.mock_drive)

    def test_returns_id_and_url(self):
        result = self.maker.create_opportunity_sheet(
            "AI Research", "prof@university.edu"
        )
        assert result["spreadsheet_id"] == "new-sheet-id-001"
        assert "docs.google.com" in result["url"]

    def test_creates_spreadsheet_with_title(self):
        self.maker.create_opportunity_sheet("ML Project", "prof@u.edu")
        create_call = self.mock_sheets.spreadsheets.return_value.create
        body = create_call.call_args[1]["body"]
        assert body["properties"]["title"] == "ML Project"

    def test_shares_with_professor_as_writer(self):
        self.maker.create_opportunity_sheet("Proj", "prof@u.edu")
        perm_create = self.mock_drive.permissions.return_value.create
        perm_create.assert_called_once()
        call_kwargs = perm_create.call_args[1]
        assert call_kwargs["fileId"] == "new-sheet-id-001"
        assert call_kwargs["body"]["role"] == "writer"
        assert call_kwargs["body"]["emailAddress"] == "prof@u.edu"
        assert call_kwargs["sendNotificationEmail"] is True

    def test_with_headers_seeds_first_row(self):
        headers = ["Name", "Email", "Status"]
        self.maker.create_opportunity_sheet("Proj", "prof@u.edu", sheet_headers=headers)
        update_call = (
            self.mock_sheets.spreadsheets.return_value.values.return_value.update
        )
        update_call.assert_called_once()
        kw = update_call.call_args[1]
        assert kw["body"]["values"] == [headers]

    def test_drive_service_built_once(self):
        self.maker.create_opportunity_sheet("X", "prof@u.edu")
        self.maker._build_drive_service.assert_called_once()
