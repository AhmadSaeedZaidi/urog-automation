"""Pytest configuration and shared fixtures for forms tests."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_sheets_service():
    """A fully mocked Sheets API v4 service."""
    svc = MagicMock()

    # spreadsheets().create()
    created = {
        "spreadsheetId": "new-sheet-id-001",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-sheet-id-001/edit",
    }
    svc.spreadsheets.return_value.create.return_value.execute.return_value = created

    # spreadsheets().values().update()
    svc.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {}

    return svc


@pytest.fixture
def mock_drive_service():
    """A fully mocked Drive API v3 service."""
    svc = MagicMock()
    return svc
