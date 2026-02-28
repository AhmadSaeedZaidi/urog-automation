"""Pytest configuration and shared fixtures for generator tests."""

import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_env_no_api_key():
    """Ensure GEMINI_API_KEY is absent so MOCK_MODE is always active."""
    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        yield


@pytest.fixture(autouse=True)
def mock_dao_db():
    """Mock the DAO db singleton used by the engine."""
    mock_db = MagicMock()
    with patch("generator.engine.db", mock_db):
        yield mock_db


@pytest.fixture
def sample_template():
    """A typical email template record as returned by the DB."""
    return {
        "id": "tmpl-uuid-001",
        "name": "welcome_email",
        "platform": "email",
        "content": "Hello {{full_name}}, welcome to {{team}}!",
        "required_keys": ["full_name", "team"],
    }


@pytest.fixture
def sample_user():
    """A typical user data dict."""
    return {
        "email": "alice@example.com",
        "full_name": "Alice Johnson",
        "profile_data": {"team": "Education", "year": "3"},
    }


@pytest.fixture
def sample_user_missing_keys():
    """User data missing a required key (team)."""
    return {
        "email": "bob@example.com",
        "full_name": "Bob Smith",
        "profile_data": {},
    }


@pytest.fixture
def template_no_required_keys():
    """Template with no required_keys."""
    return {
        "id": "tmpl-uuid-002",
        "name": "general_announcement",
        "platform": "email",
        "content": "Dear member, here is an update.",
        "required_keys": None,
    }
