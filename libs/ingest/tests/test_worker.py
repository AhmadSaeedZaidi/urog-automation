"""Tests for inbox worker parsing logic."""

from ingest.worker import process_inbox, process_csv_payload


class TestProcessCsvPayload:
    """Test the row-by-row CSV parsing and upsert logic."""

    def test_standard_email_field(self, mock_dao_db, sample_csv_records):
        """Row with 'email' key should be upserted."""
        single = [sample_csv_records[0]]  # alice with 'email' key
        process_csv_payload(single)

        mock_dao_db.upsert_person.assert_called_once()
        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["email"] == "alice@example.com"
        assert kw["full_name"] == "Alice Johnson"
        assert kw["phone"] == "+1111111111"
        assert kw["role"] == "student"

    def test_email_address_alias(self, mock_dao_db, sample_csv_records):
        """Row using 'email_address' should also resolve."""
        carol_row = [sample_csv_records[2]]  # carol with 'email_address'
        process_csv_payload(carol_row)

        mock_dao_db.upsert_person.assert_called_once()
        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["email"] == "carol@example.com"

    def test_name_alias(self, mock_dao_db, sample_csv_records):
        """Row using 'name' instead of 'full_name' should work."""
        bob_row = [sample_csv_records[1]]  # bob with 'name'
        process_csv_payload(bob_row)

        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["full_name"] == "Bob Smith"

    def test_first_last_name_concatenation(self, mock_dao_db):
        """first_name + last_name should be joined into full_name."""
        row = [{"email": "dan@test.com", "first_name": "Dan", "last_name": "Lee"}]
        process_csv_payload(row)

        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["full_name"] == "Dan Lee"

    def test_phone_number_alias(self, mock_dao_db, sample_csv_records):
        """'phone_number' should resolve to the phone argument."""
        bob_row = [sample_csv_records[1]]
        process_csv_payload(bob_row)

        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["phone"] == "+2222222222"

    def test_whatsapp_alias(self, mock_dao_db, sample_csv_records):
        """'whatsapp' should also resolve to phone."""
        carol_row = [sample_csv_records[2]]
        process_csv_payload(carol_row)

        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["phone"] == "+3333333333"

    def test_invalid_role_defaults_to_student(self, mock_dao_db):
        """Unknown role text should fall back to 'student'."""
        row = [{"email": "x@test.com", "role": "alien"}]
        process_csv_payload(row)

        kw = mock_dao_db.upsert_person.call_args[1]
        assert kw["role"] == "student"

    def test_valid_roles_preserved(self, mock_dao_db):
        """Valid enum roles should pass through unchanged."""
        for role in ["student", "professor", "admin", "external"]:
            mock_dao_db.reset_mock()
            row = [{"email": f"{role}@test.com", "role": role}]
            process_csv_payload(row)
            kw = mock_dao_db.upsert_person.call_args[1]
            assert kw["role"] == role

    def test_missing_email_skipped(self, mock_dao_db):
        """Rows without any email field should be skipped entirely."""
        row = [{"name": "No Email Person", "major": "CS"}]
        process_csv_payload(row)
        mock_dao_db.upsert_person.assert_not_called()

    def test_extra_data_excludes_strict_keys(self, mock_dao_db):
        """Profile data should not contain the strict/mapped keys."""
        row = [
            {
                "email": "a@test.com",
                "full_name": "A",
                "major": "CS",
                "year": "3",
            }
        ]
        process_csv_payload(row)

        kw = mock_dao_db.upsert_person.call_args[1]
        extra = kw["extra_data"]
        assert "email" not in extra
        assert "full_name" not in extra
        assert "major" in extra
        assert "year" in extra

    def test_multiple_rows_batch(self, mock_dao_db, sample_csv_records):
        """All three sample records should be processed."""
        process_csv_payload(sample_csv_records)
        assert mock_dao_db.upsert_person.call_count == 3


class TestProcessInbox:
    """Test the top-level process_inbox coordinator."""

    def test_empty_inbox(self, mock_dao_db, capsys):
        """Empty inbox should print message and return."""
        mock_dao_db.get_unprocessed_inbox_items.return_value = []
        process_inbox()
        assert "Inbox is empty" in capsys.readouterr().out

    def test_processes_csv_items(self, mock_dao_db):
        """CSV-type inbox items should be dispatched to process_csv_payload."""
        mock_dao_db.get_unprocessed_inbox_items.return_value = [
            {
                "id": "inbox-1",
                "source_name": "test.csv",
                "source_type": "csv",
                "raw_payload": [
                    {"email": "x@test.com", "name": "X"},
                ],
            }
        ]

        process_inbox()

        # Item should be marked processed
        mock_dao_db.mark_inbox_processed.assert_called_once_with("inbox-1")
        # Person should have been upserted
        mock_dao_db.upsert_person.assert_called_once()

    def test_error_marks_item_failed(self, mock_dao_db):
        """If processing raises, the item should be marked with error."""
        mock_dao_db.get_unprocessed_inbox_items.return_value = [
            {
                "id": "inbox-err",
                "source_name": "bad.csv",
                "source_type": "csv",
                "raw_payload": "not-a-list",  # will cause iteration error
            }
        ]

        process_inbox()

        # Should have been called with error string
        args = mock_dao_db.mark_inbox_processed.call_args
        assert args[0][0] == "inbox-err"
        assert args[1]["error"] is not None

    def test_google_form_type_is_handled(self, mock_dao_db):
        """google_form type should not crash, just pass through."""
        mock_dao_db.get_unprocessed_inbox_items.return_value = [
            {
                "id": "inbox-form",
                "source_name": "Signup Form",
                "source_type": "google_form",
                "raw_payload": {"field": "value"},
            }
        ]

        process_inbox()
        mock_dao_db.mark_inbox_processed.assert_called_once_with("inbox-form")
