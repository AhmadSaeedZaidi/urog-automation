"""Integration tests and singleton instance tests."""

import pytest
from unittest.mock import MagicMock, patch
from dao.client import UrogDB, db


class TestSingletonInstance:
    """Test the singleton db instance."""

    def test_singleton_instance_exists(self):
        """Test that singleton db instance is created."""
        assert db is not None
        assert isinstance(db, UrogDB)

    def test_singleton_instance_has_connection_string(self):
        """Test that singleton has connection string configured."""
        # Should either have conn_str from env or raise ValueError
        assert hasattr(db, "conn_str")


class TestIntegrationScenarios:
    """Test realistic usage scenarios."""

    @pytest.fixture
    def db_instance(self):
        """Create a fresh UrogDB instance for testing."""
        db = UrogDB(connection_string="postgresql://test")
        # Set up a mock connection to prevent real DB connection attempts
        mock_conn = MagicMock()
        mock_conn.closed = False
        db.conn = mock_conn
        return db

    @pytest.fixture
    def mock_full_connection(self, db_instance):
        """Mock a complete database connection setup."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.closed = False
        db_instance.conn = mock_conn
        return db_instance, mock_conn, mock_cursor

    def test_ingest_and_process_workflow(self, mock_full_connection):
        """Test complete workflow: ingest -> fetch -> process."""
        db_instance, mock_conn, mock_cursor = mock_full_connection

        # Mock ingest
        mock_cursor.fetchone.return_value = {"id": "inbox-1"}
        inbox_id = db_instance.ingest_raw(
            "Student Application",
            "google_form",
            {"name": "Alice", "email": "alice@test.com"},
        )

        assert inbox_id == "inbox-1"

        # Mock fetch unprocessed
        mock_cursor.fetchall.return_value = [
            {"id": "inbox-1", "source_name": "Student Application"}
        ]
        items = db_instance.get_unprocessed_inbox_items()

        assert len(items) == 1

        # Mock mark as processed
        db_instance.mark_inbox_processed("inbox-1")

        # Verify commits were made (ingest_raw + mark_inbox_processed)
        assert mock_conn.commit.call_count >= 2

    def test_person_creation_and_opportunity_workflow(self, mock_full_connection):
        """Test workflow: create professor -> create opportunity."""
        db_instance, mock_conn, mock_cursor = mock_full_connection

        # Create professor
        mock_cursor.fetchone.return_value = {"id": "prof-uuid-1"}
        prof_id = db_instance.upsert_person(
            email="prof@university.edu", full_name="Dr. Smith", role="professor"
        )

        assert prof_id == "prof-uuid-1"

        # Create opportunity owned by professor
        mock_cursor.fetchone.return_value = {"id": "opp-uuid-1"}
        opp_id = db_instance.create_opportunity(
            title="Research Assistant",
            owner_id=prof_id,
            description="AI research position",
        )

        assert opp_id == "opp-uuid-1"
        assert mock_conn.commit.call_count == 2

    def test_template_and_logging_workflow(self, mock_full_connection):
        """Test workflow: get template -> log message."""
        db_instance, mock_conn, mock_cursor = mock_full_connection

        # Get template
        template = {
            "id": "template-1",
            "name": "acceptance_email",
            "content": "Congratulations {{name}}!",
        }
        mock_cursor.fetchone.return_value = template

        fetched_template = db_instance.get_template("acceptance_email")
        assert fetched_template == template

        # Compile message (would be done by application)
        compiled = "Congratulations Alice!"

        # Log sent message
        mock_cursor.fetchone.return_value = None  # No return needed
        db_instance.log_sent_message(
            recipient_id="person-1",
            template_id=template["id"],
            platform="email",
            compiled_msg=compiled,
            status="sent",
        )

        assert mock_conn.commit.call_count >= 1

    def test_error_handling_in_workflow(self, mock_full_connection):
        """Test error handling in processing workflow."""
        db_instance, mock_conn, mock_cursor = mock_full_connection

        # Ingest data
        mock_cursor.fetchone.return_value = {"id": "inbox-error-1"}
        inbox_id = db_instance.ingest_raw("Bad Data", "form", {"incomplete": True})

        # Try to process and fail
        error_msg = "Missing required field: email"
        db_instance.mark_inbox_processed(inbox_id, error=error_msg)

        # Verify error was logged
        call_args = mock_cursor.execute.call_args
        assert error_msg in call_args[0][1]

    def test_multiple_people_upserts(self, mock_full_connection):
        """Test upserting multiple people in sequence."""
        db_instance, mock_conn, mock_cursor = mock_full_connection

        people = [
            ("alice@test.com", "Alice Johnson"),
            ("bob@test.com", "Bob Smith"),
            ("carol@test.com", "Carol Williams"),
        ]

        created_ids = []
        for email, name in people:
            mock_cursor.fetchone.return_value = {"id": f"person-{len(created_ids)}"}
            person_id = db_instance.upsert_person(email=email, full_name=name)
            created_ids.append(person_id)

        assert len(created_ids) == 3
        assert mock_conn.commit.call_count == 3

    @patch("dao.client.psycopg2.connect")
    def test_full_connection_lifecycle(self, mock_connect):
        """Test complete connection lifecycle: connect -> use -> close."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.closed = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"id": "test-id"}
        mock_connect.return_value = mock_conn

        db_instance = UrogDB(connection_string="postgresql://test")

        # Connect
        db_instance.connect()
        assert db_instance.conn == mock_conn

        # Use connection
        db_instance.upsert_person(email="test@example.com")
        assert mock_cursor.execute.called

        # Close
        db_instance.close()
        mock_conn.close.assert_called_once()

    def test_inbox_processing_with_batch(self, mock_full_connection):
        """Test processing multiple inbox items."""
        db_instance, mock_conn, mock_cursor = mock_full_connection

        # Fetch batch of unprocessed items
        mock_cursor.fetchall.return_value = [
            {"id": "inbox-1", "raw_payload": {"email": "a@test.com"}},
            {"id": "inbox-2", "raw_payload": {"email": "b@test.com"}},
            {"id": "inbox-3", "raw_payload": {"email": "c@test.com"}},
        ]

        items = db_instance.get_unprocessed_inbox_items(limit=10)
        assert len(items) == 3

        # Process each
        for item in items:
            db_instance.mark_inbox_processed(item["id"])

        # Should have committed for each mark
        assert mock_conn.commit.call_count >= 3
