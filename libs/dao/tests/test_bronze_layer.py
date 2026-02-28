"""Tests for bronze layer (data_inbox) operations."""

import pytest
from unittest.mock import MagicMock, patch
from psycopg2.extras import Json
from dao.client import UrogDB


class TestBronzeLayer:
    """Test bronze layer inbox operations."""

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

    def test_ingest_raw_inserts_data(self, db, mock_connection):
        """Test inserting raw data into inbox."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {"id": "test-uuid-123"}

        payload = {"name": "John Doe", "email": "john@example.com"}
        result = db.ingest_raw("Test Form", "google_form", payload)

        assert result == "test-uuid-123"
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

        # Verify SQL contains correct parameters
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO data_inbox" in call_args[0][0]
        assert call_args[0][1][0] == "Test Form"
        assert call_args[0][1][1] == "google_form"
        assert isinstance(call_args[0][1][2], Json)

    def test_ingest_raw_with_list_payload(self, db, mock_connection):
        """Test inserting list payload into inbox."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {"id": "test-uuid-456"}

        payload = [{"name": "Alice"}, {"name": "Bob"}]
        result = db.ingest_raw("CSV Import", "csv", payload)

        assert result == "test-uuid-456"
        mock_conn.commit.assert_called_once()

    def test_get_unprocessed_inbox_items_default_limit(self, db, mock_connection):
        """Test fetching unprocessed items with default limit."""
        mock_conn, mock_cursor = mock_connection
        expected_items = [
            {"id": "1", "source_name": "Form A", "processed_at": None},
            {"id": "2", "source_name": "Form B", "processed_at": None},
        ]
        mock_cursor.fetchall.return_value = expected_items

        result = db.get_unprocessed_inbox_items()

        assert result == expected_items
        call_args = mock_cursor.execute.call_args
        assert "WHERE processed_at IS NULL" in call_args[0][0]
        assert call_args[0][1] == (50,)  # Default limit

    def test_get_unprocessed_inbox_items_custom_limit(self, db, mock_connection):
        """Test fetching unprocessed items with custom limit."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []

        db.get_unprocessed_inbox_items(limit=10)

        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (10,)

    def test_get_unprocessed_inbox_items_orders_by_created_at(
        self, db, mock_connection
    ):
        """Test that results are ordered by creation time."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []

        db.get_unprocessed_inbox_items()

        call_args = mock_cursor.execute.call_args
        assert "ORDER BY created_at ASC" in call_args[0][0]

    def test_mark_inbox_processed_success(self, db, mock_connection):
        """Test marking inbox item as successfully processed."""
        mock_conn, mock_cursor = mock_connection

        db.mark_inbox_processed("test-uuid-123")

        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "processed_at = NOW()" in sql
        assert params == (None, "test-uuid-123")
        mock_conn.commit.assert_called_once()

    def test_mark_inbox_processed_with_error(self, db, mock_connection):
        """Test marking inbox item as failed with error message."""
        mock_conn, mock_cursor = mock_connection

        error_msg = "Invalid email format"
        db.mark_inbox_processed("test-uuid-456", error=error_msg)

        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "processed_at = NULL" in sql
        assert params == (error_msg, "test-uuid-456")
        mock_conn.commit.assert_called_once()

    @patch("dao.client.psycopg2.connect")
    def test_ingest_raw_connects_if_needed(self, mock_connect, db):
        """Test that ingest_raw establishes connection if needed."""
        db.conn = None  # Reset connection to test connection establishment
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"id": "inbox-uuid-123"}
        mock_connect.return_value = mock_conn

        db.ingest_raw("Test Source", "test_type", {"key": "value"})

        mock_connect.assert_called_once()
