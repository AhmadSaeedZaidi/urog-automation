"""Tests for automation layer (templates and logging) operations."""

import pytest
from unittest.mock import MagicMock, patch
from dao.client import UrogDB


class TestAutomationLayer:
    """Test automation layer operations."""

    @pytest.fixture
    def db(self):
        """Create a UrogDB instance for testing."""
        db = UrogDB(connection_string="postgresql://test")
        # Set up a mock connection to prevent real DB connection attempts
        mock_conn = MagicMock()
        mock_conn.closed = False
        db.conn = mock_conn
        return db

    @pytest.fixture
    def mock_connection(self, db):
        """Mock database connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.closed = False
        db.conn = mock_conn
        return mock_conn, mock_cursor


class TestTemplateOperations(TestAutomationLayer):
    """Test template-related operations."""

    def test_get_template_found(self, db, mock_connection):
        """Test retrieving an existing template."""
        mock_conn, mock_cursor = mock_connection
        expected_template = {
            "id": "template-uuid-123",
            "name": "welcome_email",
            "platform": "email",
            "content": "Hello {{name}}, welcome to UROG!",
            "required_keys": ["name"],
        }
        mock_cursor.fetchone.return_value = expected_template

        result = db.get_template("welcome_email")

        assert result == expected_template
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "SELECT * FROM templates" in sql
        assert "WHERE name = %s" in sql
        assert params == ("welcome_email",)

    def test_get_template_not_found(self, db, mock_connection):
        """Test retrieving a non-existent template."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = None

        result = db.get_template("nonexistent_template")

        assert result is None

    def test_get_template_whatsapp(self, db, mock_connection):
        """Test retrieving a WhatsApp template."""
        mock_conn, mock_cursor = mock_connection
        template = {
            "id": "wa-template-456",
            "name": "interview_reminder",
            "platform": "whatsapp",
            "content": "Hi {{name}}, your interview is at {{time}}.",
            "required_keys": ["name", "time"],
        }
        mock_cursor.fetchone.return_value = template

        result = db.get_template("interview_reminder")

        assert result == template
        assert result["platform"] == "whatsapp"

    @patch("dao.client.psycopg2.connect")
    def test_get_template_connects_if_needed(self, mock_connect, db):
        """Test that get_template establishes connection if needed."""
        db.conn = None  # Reset connection to test connection establishment
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_connect.return_value = mock_conn

        db.get_template("test_template")

        mock_connect.assert_called_once()


class TestMessageLogging(TestAutomationLayer):
    """Test message logging operations."""

    def test_log_sent_message_success(self, db, mock_connection):
        """Test logging a successfully sent message."""
        mock_conn, mock_cursor = mock_connection

        db.log_sent_message(
            recipient_id="person-uuid-123",
            template_id="template-uuid-456",
            platform="email",
            compiled_msg="Hello John, welcome to UROG!",
            status="sent",
        )

        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "INSERT INTO sent_logs" in sql
        assert params == (
            "person-uuid-123",
            "template-uuid-456",
            "email",
            "sent",
            "Hello John, welcome to UROG!",
            None,
        )
        mock_conn.commit.assert_called_once()

    def test_log_sent_message_failed(self, db, mock_connection):
        """Test logging a failed message with error."""
        mock_conn, mock_cursor = mock_connection

        db.log_sent_message(
            recipient_id="person-uuid-789",
            template_id="template-uuid-111",
            platform="whatsapp",
            compiled_msg="Failed message content",
            status="failed",
            error="Invalid phone number",
        )

        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]

        assert params[3] == "failed"
        assert params[5] == "Invalid phone number"
        mock_conn.commit.assert_called_once()

    def test_log_sent_message_queued(self, db, mock_connection):
        """Test logging a queued message."""
        mock_conn, mock_cursor = mock_connection

        db.log_sent_message(
            recipient_id="person-uuid-555",
            template_id="template-uuid-666",
            platform="email",
            compiled_msg="Queued message",
            status="queued",
        )

        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]

        assert params[3] == "queued"
        assert params[5] is None  # No error for queued messages

    def test_log_sent_message_whatsapp_platform(self, db, mock_connection):
        """Test logging a WhatsApp message."""
        mock_conn, mock_cursor = mock_connection

        db.log_sent_message(
            recipient_id="person-uuid-222",
            template_id="template-uuid-333",
            platform="whatsapp",
            compiled_msg="WhatsApp message content",
            status="sent",
        )

        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]

        assert params[2] == "whatsapp"

    def test_log_sent_message_default_status(self, db, mock_connection):
        """Test logging message with default status."""
        mock_conn, mock_cursor = mock_connection

        db.log_sent_message(
            recipient_id="person-uuid-999",
            template_id="template-uuid-888",
            platform="email",
            compiled_msg="Default status message",
        )

        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]

        # Default status is 'sent'
        assert params[3] == "sent"
        assert params[5] is None  # No error

    @patch("dao.client.psycopg2.connect")
    def test_log_sent_message_connects_if_needed(self, mock_connect, db):
        """Test that log_sent_message establishes connection if needed."""
        db.conn = None  # Reset connection to test connection establishment
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db.log_sent_message(
            recipient_id="person-1",
            template_id="template-1",
            platform="email",
            compiled_msg="Test",
        )

        mock_connect.assert_called_once()

    def test_log_sent_message_with_long_error(self, db, mock_connection):
        """Test logging message with long error message."""
        mock_conn, mock_cursor = mock_connection

        long_error = "Error: " + "x" * 500  # Long error message

        db.log_sent_message(
            recipient_id="person-uuid-777",
            template_id="template-uuid-444",
            platform="email",
            compiled_msg="Message with long error",
            status="failed",
            error=long_error,
        )

        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]

        assert params[5] == long_error
        mock_conn.commit.assert_called_once()
