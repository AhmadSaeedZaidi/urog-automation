"""Shared pytest fixtures for top-level integration / e2e tests."""

import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_env():
    """Ensure DATABASE_URL is set and GEMINI_API_KEY is absent (MOCK_MODE)."""
    with patch.dict(
        os.environ,
        {"DATABASE_URL": "postgresql://test:test@localhost/test_db"},
        clear=False,
    ):
        # Remove API key so generator always uses mock
        os.environ.pop("GEMINI_API_KEY", None)
        yield
