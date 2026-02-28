"""Pytest configuration and shared fixtures for ingest tests."""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_dao_db():
    """Mock the DAO db singleton so no real database is ever hit."""
    mock_db = MagicMock()
    mock_db.ingest_raw.return_value = "inbox-uuid-001"
    mock_db.get_unprocessed_inbox_items.return_value = []
    mock_db.upsert_person.return_value = "person-uuid-001"

    with patch("ingest.loader.db", mock_db), patch("ingest.worker.db", mock_db):
        yield mock_db


@pytest.fixture
def sample_csv_records():
    """Sample records as they would appear after CSV parsing."""
    return [
        {
            "email": "alice@example.com",
            "full_name": "Alice Johnson",
            "phone": "+1111111111",
            "role": "student",
            "major": "Computer Science",
            "year": "3",
        },
        {
            "email": "bob@example.com",
            "name": "Bob Smith",
            "phone_number": "+2222222222",
            "team": "Education",
        },
        {
            "first_name": "Carol",
            "last_name": "Williams",
            "email_address": "carol@example.com",
            "whatsapp": "+3333333333",
            "role": "external",
        },
    ]


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame mimicking raw CSV input with messy headers."""
    return pd.DataFrame(
        {
            "  Full Name ": ["Alice Johnson", "Bob Smith"],
            "EMAIL": ["alice@example.com", "bob@example.com"],
            " Phone Number": ["+1111111111", None],
            "Major": ["CS", "EE"],
        }
    )


@pytest.fixture
def sample_dataframe_with_nans():
    """DataFrame with NaN values to test cleaning."""
    return pd.DataFrame(
        {
            "Name": ["Alice", None, "Carol"],
            "Email": ["alice@test.com", "bob@test.com", None],
            "GPA": [3.5, None, 3.8],
        }
    )
