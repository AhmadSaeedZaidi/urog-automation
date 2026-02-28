"""Tests for database connection and initialization."""

import os
import pytest
from unittest.mock import MagicMock, patch, mock_open
from dao.client import UrogDB


class TestConnection:
    """Test database connection management."""

    def test_init_with_connection_string(self):
        """Test initialization with explicit connection string."""
        conn_str = "postgresql://user:pass@localhost/test"
        db = UrogDB(connection_string=conn_str)
        assert db.conn_str == conn_str

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/test"})
    def test_init_with_env_variable(self):
        """Test initialization with environment variable."""
        db = UrogDB()
        assert db.conn_str == "postgresql://user:pass@localhost/test"

    @patch.dict(os.environ, {}, clear=True)
    def test_init_without_connection_string_raises_error(self):
        """Test that missing connection string raises ValueError."""
        with pytest.raises(ValueError, match="DATABASE_URL is not set"):
            UrogDB()

    @patch("dao.client.psycopg2.connect")
    def test_connect_establishes_connection(self, mock_connect):
        """Test that connect() establishes a database connection."""
        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_connect.return_value = mock_conn

        db = UrogDB(connection_string="postgresql://test")
        db.connect()

        assert db.conn == mock_conn
        mock_connect.assert_called_once()

    @patch("dao.client.psycopg2.connect")
    def test_connect_reuses_open_connection(self, mock_connect):
        """Test that connect() reuses an already open connection."""
        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_connect.return_value = mock_conn

        db = UrogDB(connection_string="postgresql://test")
        db.connect()
        db.connect()

        # Should only connect once
        assert mock_connect.call_count == 1

    @patch("dao.client.psycopg2.connect")
    def test_connect_reconnects_closed_connection(self, mock_connect):
        """Test that connect() reconnects if connection is closed."""
        mock_conn = MagicMock()
        mock_conn.closed = True
        mock_connect.return_value = mock_conn

        db = UrogDB(connection_string="postgresql://test")
        db.conn = mock_conn
        db.connect()

        # Should reconnect
        assert mock_connect.call_count == 1

    def test_close_closes_connection(self):
        """Test that close() closes the database connection."""
        db = UrogDB(connection_string="postgresql://test")
        mock_conn = MagicMock()
        db.conn = mock_conn

        db.close()

        mock_conn.close.assert_called_once()

    def test_close_with_no_connection(self):
        """Test that close() handles missing connection gracefully."""
        db = UrogDB(connection_string="postgresql://test")
        db.close()  # Should not raise error

    @patch("dao.client.psycopg2.connect")
    @patch("builtins.open", new_callable=mock_open, read_data="CREATE TABLE test;")
    def test_init_schema_with_default_path(self, mock_file, mock_connect):
        """Test schema initialization with default schema.sql path."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db = UrogDB(connection_string="postgresql://test")
        db.init_schema()

        mock_cursor.execute.assert_called_once_with("CREATE TABLE test;")
        mock_conn.commit.assert_called_once()

    @patch("dao.client.psycopg2.connect")
    @patch("builtins.open", new_callable=mock_open, read_data="CREATE TABLE custom;")
    def test_init_schema_with_custom_path(self, mock_file, mock_connect):
        """Test schema initialization with custom schema path."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db = UrogDB(connection_string="postgresql://test")
        db.init_schema(schema_path="/custom/schema.sql")

        mock_file.assert_called_once_with("/custom/schema.sql", "r")
        mock_cursor.execute.assert_called_once_with("CREATE TABLE custom;")
        mock_conn.commit.assert_called_once()
