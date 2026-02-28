"""Tests for file-upload, gsheets-ingest, and opportunity-creation API endpoints."""

import io
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


# ── POST /api/admin/upload-file ─────────────────────────────────────────────


class TestUploadFile:
    """Exercise the file-upload endpoint with mocked loader."""

    @patch("main.LoaderFactory")
    def test_upload_csv_success(self, mock_factory):
        mock_loader = MagicMock()
        mock_loader.load.return_value = "inbox-id-1"
        mock_factory.get_loader.return_value = mock_loader

        csv_data = _csv_bytes("name,email\nAlice,alice@test.com\n")
        resp = client.post(
            "/api/admin/upload-file",
            files={"file": ("people.csv", io.BytesIO(csv_data), "text/csv")},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["inbox_id"] == "inbox-id-1"
        assert body["filename"] == "people.csv"
        assert body["loader_type"] == "csv"

    @patch("main.LoaderFactory")
    def test_upload_xlsx_success(self, mock_factory):
        mock_loader = MagicMock()
        mock_loader.load.return_value = "inbox-id-2"
        mock_factory.get_loader.return_value = mock_loader

        resp = client.post(
            "/api/admin/upload-file",
            files={
                "file": (
                    "data.xlsx",
                    io.BytesIO(b"fake-xlsx"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["loader_type"] == "excel"
        assert body["filename"] == "data.xlsx"

    def test_upload_unsupported_type(self):
        resp = client.post(
            "/api/admin/upload-file",
            files={"file": ("readme.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    @patch("main.LoaderFactory")
    def test_upload_custom_source_name(self, mock_factory):
        mock_loader = MagicMock()
        mock_loader.load.return_value = "inbox-id-3"
        mock_factory.get_loader.return_value = mock_loader

        csv_data = _csv_bytes("col1\nval1\n")
        resp = client.post(
            "/api/admin/upload-file",
            files={"file": ("raw.csv", io.BytesIO(csv_data), "text/csv")},
            params={"source_name": "my-custom-source"},
        )

        assert resp.status_code == 201
        mock_loader.load.assert_called_once()
        call_kwargs = mock_loader.load.call_args
        assert call_kwargs[1]["source_name"] == "my-custom-source"

    @patch("main.LoaderFactory")
    def test_upload_loader_error_returns_500(self, mock_factory):
        mock_loader = MagicMock()
        mock_loader.load.side_effect = RuntimeError("parse failure")
        mock_factory.get_loader.return_value = mock_loader

        csv_data = _csv_bytes("bad\n")
        resp = client.post(
            "/api/admin/upload-file",
            files={"file": ("broken.csv", io.BytesIO(csv_data), "text/csv")},
        )

        assert resp.status_code == 500
        assert "parse failure" in resp.json()["detail"]


# ── POST /api/admin/ingest-gsheets ──────────────────────────────────────────


class TestIngestGSheets:
    """Exercise the Google Sheets ingestion endpoint."""

    @patch("main.GoogleSheetsLoader")
    def test_ingest_success(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader.load.return_value = "inbox-gsheet-1"
        mock_loader_cls.return_value = mock_loader

        resp = client.post(
            "/api/admin/ingest-gsheets",
            json={"spreadsheet_id": "abc123"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["inbox_id"] == "inbox-gsheet-1"
        assert body["spreadsheet_id"] == "abc123"

    @patch("main.GoogleSheetsLoader")
    def test_ingest_custom_source_name(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader.load.return_value = "inbox-gsheet-2"
        mock_loader_cls.return_value = mock_loader

        resp = client.post(
            "/api/admin/ingest-gsheets",
            json={"spreadsheet_id": "xyz", "source_name": "My Sheet"},
        )

        assert resp.status_code == 201
        mock_loader.load.assert_called_once_with("xyz", source_name="My Sheet")

    @patch("main.GoogleSheetsLoader")
    def test_ingest_empty_sheet_returns_400(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader.load.return_value = None
        mock_loader_cls.return_value = mock_loader

        resp = client.post(
            "/api/admin/ingest-gsheets",
            json={"spreadsheet_id": "empty-sheet"},
        )

        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    @patch("main.GoogleSheetsLoader")
    def test_ingest_missing_credentials_returns_503(self, mock_loader_cls):
        mock_loader_cls.return_value.load.side_effect = EnvironmentError(
            "credentials file not found"
        )

        resp = client.post(
            "/api/admin/ingest-gsheets",
            json={"spreadsheet_id": "no-creds"},
        )

        assert resp.status_code == 503
        assert "credentials" in resp.json()["detail"].lower()

    def test_ingest_missing_spreadsheet_id_returns_422(self):
        resp = client.post("/api/admin/ingest-gsheets", json={})
        assert resp.status_code == 422


# ── POST /api/admin/create-opportunity ──────────────────────────────────────


class TestCreateOpportunity:
    """Exercise the opportunity-creation endpoint (professor lookup + Sheet + DB)."""

    @patch("main.db")
    @patch("main.WorkspaceMaker")
    def test_create_opportunity_success(self, mock_maker_cls, mock_db):
        mock_db.get_person_by_email.return_value = {
            "id": "prof-uuid",
            "email": "prof@uni.edu",
        }
        mock_maker = MagicMock()
        mock_maker.create_opportunity_sheet.return_value = {
            "spreadsheet_id": "sheet-abc",
            "url": "https://docs.google.com/spreadsheets/d/sheet-abc",
        }
        mock_maker_cls.return_value = mock_maker
        mock_db.create_opportunity.return_value = "opp-uuid-1"

        resp = client.post(
            "/api/admin/create-opportunity",
            json={
                "title": "AI Research",
                "professor_email": "prof@uni.edu",
                "description": "Deep learning study",
                "type": "research",
                "sheet_headers": ["Name", "Email", "GPA"],
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["opportunity_id"] == "opp-uuid-1"
        assert body["title"] == "AI Research"
        assert body["spreadsheet_id"] == "sheet-abc"
        assert "docs.google.com" in body["spreadsheet_url"]

        # Verify sheet was created and shared with professor
        mock_maker.create_opportunity_sheet.assert_called_once_with(
            title="UROG — AI Research",
            professor_email="prof@uni.edu",
            sheet_headers=["Name", "Email", "GPA"],
        )

        # Verify DB call uses resolved owner_id and form_config
        mock_db.create_opportunity.assert_called_once()
        call_kwargs = mock_db.create_opportunity.call_args[1]
        assert call_kwargs["owner_id"] == "prof-uuid"
        assert call_kwargs["form_config"]["spreadsheet_id"] == "sheet-abc"

    @patch("main.db")
    @patch("main.WorkspaceMaker")
    def test_create_opportunity_default_headers(self, mock_maker_cls, mock_db):
        mock_db.get_person_by_email.return_value = {
            "id": "prof-uuid",
            "email": "prof@uni.edu",
        }
        mock_maker = MagicMock()
        mock_maker.create_opportunity_sheet.return_value = {
            "spreadsheet_id": "sheet-def",
            "url": "https://docs.google.com/spreadsheets/d/sheet-def",
        }
        mock_maker_cls.return_value = mock_maker
        mock_db.create_opportunity.return_value = "opp-uuid-2"

        resp = client.post(
            "/api/admin/create-opportunity",
            json={"title": "Summer Internship", "professor_email": "prof@uni.edu"},
        )

        assert resp.status_code == 201
        call_args = mock_maker.create_opportunity_sheet.call_args
        assert call_args[1]["sheet_headers"] == ["Name", "Email", "Status"]

    @patch("main.db")
    def test_professor_not_found_returns_404(self, mock_db):
        mock_db.get_person_by_email.return_value = None

        resp = client.post(
            "/api/admin/create-opportunity",
            json={"title": "No Prof", "professor_email": "ghost@uni.edu"},
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @patch("main.db")
    @patch("main.WorkspaceMaker")
    def test_sheet_failure_returns_502(self, mock_maker_cls, mock_db):
        mock_db.get_person_by_email.return_value = {
            "id": "prof-uuid",
            "email": "prof@uni.edu",
        }
        mock_maker = MagicMock()
        mock_maker.create_opportunity_sheet.side_effect = RuntimeError(
            "API quota exceeded"
        )
        mock_maker_cls.return_value = mock_maker

        resp = client.post(
            "/api/admin/create-opportunity",
            json={"title": "Failing Project", "professor_email": "prof@uni.edu"},
        )

        assert resp.status_code == 502
        assert "Failed to create Google Sheet" in resp.json()["detail"]

    @patch("main.db")
    @patch("main.WorkspaceMaker")
    def test_db_failure_returns_500(self, mock_maker_cls, mock_db):
        mock_db.get_person_by_email.return_value = {
            "id": "prof-uuid",
            "email": "prof@uni.edu",
        }
        mock_maker = MagicMock()
        mock_maker.create_opportunity_sheet.return_value = {
            "spreadsheet_id": "sheet-xyz",
            "url": "https://docs.google.com/spreadsheets/d/sheet-xyz",
        }
        mock_maker_cls.return_value = mock_maker
        mock_db.create_opportunity.side_effect = RuntimeError("connection refused")

        resp = client.post(
            "/api/admin/create-opportunity",
            json={"title": "DB Fail", "professor_email": "prof@uni.edu"},
        )

        assert resp.status_code == 500
        assert "DB error" in resp.json()["detail"]

    def test_missing_title_returns_422(self):
        resp = client.post(
            "/api/admin/create-opportunity",
            json={"professor_email": "prof@uni.edu"},
        )
        assert resp.status_code == 422

    def test_missing_professor_email_returns_422(self):
        resp = client.post(
            "/api/admin/create-opportunity",
            json={"title": "No Email"},
        )
        assert resp.status_code == 422
