"""Pytest configuration and shared fixtures."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import os


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for all tests."""
    with patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://test:test@localhost/test_db'
    }, clear=False):
        yield


@pytest.fixture
def mock_db_connection():
    """Create a properly mocked database connection with cursor context manager support."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Make cursor() return a context manager
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = None
    mock_conn.closed = False
    
    return mock_conn, mock_cursor


@pytest.fixture
def sample_person_data():
    """Sample person data for testing."""
    return {
        'email': 'test@example.com',
        'full_name': 'Test User',
        'role': 'student',
        'phone': '+1234567890',
        'extra_data': {
            'major': 'Computer Science',
            'year': 3,
            'gpa': 3.5
        }
    }


@pytest.fixture
def sample_opportunity_data():
    """Sample opportunity data for testing."""
    return {
        'title': 'Research Assistant Position',
        'owner_id': 'prof-uuid-123',
        'description': 'Looking for undergraduate research assistant',
        'type': 'research'
    }


@pytest.fixture
def sample_template_data():
    """Sample template data for testing."""
    return {
        'id': 'template-uuid-123',
        'name': 'welcome_email',
        'platform': 'email',
        'content': 'Hello {{name}}, welcome to {{university}}!',
        'required_keys': ['name', 'university']
    }


@pytest.fixture
def sample_inbox_data():
    """Sample inbox data for testing."""
    return {
        'source_name': 'Student Application Form',
        'source_type': 'google_form',
        'payload': {
            'name': 'John Doe',
            'email': 'john@example.com',
            'major': 'CS',
            'year': '3'
        }
    }
