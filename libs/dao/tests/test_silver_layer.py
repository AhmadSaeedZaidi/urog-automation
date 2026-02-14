"""Tests for silver layer (people and opportunities) operations."""
import pytest
from unittest.mock import MagicMock, patch
from dao.client import UrogDB


class TestSilverLayer:
    """Test silver layer normalized data operations."""

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


class TestPeopleOperations(TestSilverLayer):
    """Test people-related operations."""

    def test_upsert_person_creates_new_person(self, db, mock_connection):
        """Test creating a new person."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'person-uuid-123'}
        
        result = db.upsert_person(
            email="john@example.com",
            full_name="John Doe",
            role="student",
            phone="+1234567890",
            extra_data={"major": "CS", "year": 3}
        )
        
        assert result == 'person-uuid-123'
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        assert "INSERT INTO people" in sql
        assert "ON CONFLICT (email)" in sql
        assert params[0] == "john@example.com"
        assert params[1] == "John Doe"
        assert params[2] == "student"
        assert params[3] == "+1234567890"
        mock_conn.commit.assert_called_once()

    def test_upsert_person_minimal_data(self, db, mock_connection):
        """Test creating person with minimal required data."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'person-uuid-456'}
        
        result = db.upsert_person(email="minimal@example.com")
        
        assert result == 'person-uuid-456'
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        
        assert params[0] == "minimal@example.com"
        assert params[1] is None  # full_name
        assert params[2] == "student"  # default role
        assert params[3] is None  # phone

    def test_upsert_person_professor_role(self, db, mock_connection):
        """Test creating a person with professor role."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'prof-uuid-789'}
        
        result = db.upsert_person(
            email="prof@example.com",
            full_name="Dr. Smith",
            role="professor"
        )
        
        assert result == 'prof-uuid-789'
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        assert params[2] == "professor"

    def test_upsert_person_with_extra_data(self, db, mock_connection):
        """Test upserting person with profile extra data."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'person-uuid-extra'}
        
        extra = {
            "major": "Computer Science",
            "gpa": 3.8,
            "team": "Education",
            "tshirt_size": "M"
        }
        result = db.upsert_person(
            email="student@example.com",
            extra_data=extra
        )
        
        assert result == 'person-uuid-extra'
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        
        # Verify merge logic in SQL
        assert "profile_data = people.profile_data || EXCLUDED.profile_data" in sql

    def test_upsert_person_updates_existing(self, db, mock_connection):
        """Test that upsert updates existing person on conflict."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'existing-uuid'}
        
        db.upsert_person(
            email="existing@example.com",
            full_name="Updated Name",
            phone="+9876543210"
        )
        
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        
        # Verify update logic
        assert "DO UPDATE SET" in sql
        assert "full_name = COALESCE(EXCLUDED.full_name, people.full_name)" in sql
        assert "updated_at = NOW()" in sql

    @patch('dao.client.psycopg2.connect')
    def test_upsert_person_connects_if_needed(self, mock_connect, db):
        """Test that upsert_person establishes connection if needed."""
        db.conn = None  # Reset connection to test connection establishment
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 'uuid-1'}
        mock_connect.return_value = mock_conn
        
        db.upsert_person(email="test@example.com")
        
        mock_connect.assert_called_once()


class TestOpportunityOperations(TestSilverLayer):
    """Test opportunity-related operations."""

    def test_create_opportunity_with_all_fields(self, db, mock_connection):
        """Test creating an opportunity with all fields."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'opp-uuid-123'}
        
        result = db.create_opportunity(
            title="AI Research Project",
            owner_id="prof-uuid-456",
            description="Machine learning research opportunity",
            type="research"
        )
        
        assert result == 'opp-uuid-123'
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        assert "INSERT INTO opportunities" in sql
        assert params == (
            "AI Research Project",
            "prof-uuid-456",
            "Machine learning research opportunity",
            "research"
        )
        mock_conn.commit.assert_called_once()

    def test_create_opportunity_minimal_fields(self, db, mock_connection):
        """Test creating opportunity with minimal required fields."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'opp-uuid-789'}
        
        result = db.create_opportunity(
            title="Internship Opportunity",
            owner_id="prof-uuid-123"
        )
        
        assert result == 'opp-uuid-789'
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        
        assert params[0] == "Internship Opportunity"
        assert params[1] == "prof-uuid-123"
        assert params[2] is None  # description
        assert params[3] == "research"  # default type

    def test_create_opportunity_internship_type(self, db, mock_connection):
        """Test creating an internship opportunity."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'intern-uuid'}
        
        result = db.create_opportunity(
            title="Summer Internship",
            owner_id="company-uuid",
            type="internship"
        )
        
        assert result == 'intern-uuid'
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        assert params[3] == "internship"

    def test_create_opportunity_event_type(self, db, mock_connection):
        """Test creating an event opportunity."""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'id': 'event-uuid'}
        
        result = db.create_opportunity(
            title="Workshop: Data Science",
            owner_id="organizer-uuid",
            description="Hands-on data science workshop",
            type="event"
        )
        
        assert result == 'event-uuid'
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        assert params[3] == "event"

    @patch('dao.client.psycopg2.connect')
    def test_create_opportunity_connects_if_needed(self, mock_connect, db):
        """Test that create_opportunity establishes connection if needed."""
        db.conn = None  # Reset connection to test connection establishment
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 'uuid-1'}
        mock_connect.return_value = mock_conn
        
        db.create_opportunity(title="Test Opp", owner_id="owner-1")
        
        mock_connect.assert_called_once()
