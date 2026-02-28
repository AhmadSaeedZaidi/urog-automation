"""
End-to-end integration test that exercises the full lifecycle:

  1. Load a dummy CSV via the ingest pipeline.
  2. Process the inbox into the people table.
  3. Create a template in the DB.
  4. Generate a draft message (MOCK_MODE).
  5. Dispatch the message (stub).
  6. Assert that sent_logs reflects a 'sent' status.

The entire Postgres layer is replaced by a comprehensive mock so no real
database is required.
"""

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
TEST_CSV = os.path.join(FIXTURES_DIR, "test.csv")


def _make_person(email, full_name, phone=None, role="student", profile_data=None):
    """Build a person dict resembling a RealDictRow."""
    return {
        "id": str(uuid.uuid4()),
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "role": role,
        "profile_data": profile_data or {},
    }


def _make_template(
    name="welcome_email",
    platform="email",
    content="Hello {{full_name}}, welcome to {{team}}!",
    required_keys=None,
):
    tmpl_id = str(uuid.uuid4())
    return {
        "id": tmpl_id,
        "name": name,
        "platform": platform,
        "content": content,
        "required_keys": required_keys or ["full_name", "team"],
    }


# ---------------------------------------------------------------------------
# The E2E test
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    """Full lifecycle: CSV → inbox → people → template → draft → dispatch → log."""

    @pytest.fixture
    def mock_db(self):
        """
        Build a mock UrogDB that tracks state across calls so we can
        assert the whole chain.
        """
        db = MagicMock()

        # --- Ingest (Bronze) ---
        inbox_id = str(uuid.uuid4())
        db.ingest_raw.return_value = inbox_id

        # After ingest, get_unprocessed_inbox_items should return the item.
        # We'll set it up so the first call returns items, second returns [].
        inbox_item = {
            "id": inbox_id,
            "source_name": "test.csv",
            "source_type": "csv",
            "raw_payload": [
                {
                    "full_name": "Alice Johnson",
                    "email": "alice@example.com",
                    "phone": "+1111111111",
                    "role": "student",
                    "major": "Computer Science",
                    "year": "3",
                    "team": "Education",
                },
                {
                    "full_name": "Bob Smith",
                    "email": "bob@example.com",
                    "phone": "+2222222222",
                    "role": "student",
                    "major": "Electrical Engineering",
                    "year": "2",
                    "team": "Research",
                },
            ],
        }
        db.get_unprocessed_inbox_items.return_value = [inbox_item]

        # --- Silver layer ---
        db.upsert_person.side_effect = lambda **kw: str(uuid.uuid4())

        # --- People fetch ---
        alice = _make_person(
            "alice@example.com",
            "Alice Johnson",
            "+1111111111",
            profile_data={"team": "Education", "major": "Computer Science"},
        )
        bob = _make_person(
            "bob@example.com",
            "Bob Smith",
            "+2222222222",
            profile_data={"team": "Research", "major": "Electrical Engineering"},
        )
        db.get_people.return_value = [alice, bob]

        # --- Template ---
        template = _make_template()
        db.get_template.return_value = template
        db.create_template.return_value = template["id"]

        return db

    # ---------------------------------------------------------------
    # THE TEST
    # ---------------------------------------------------------------

    def test_full_lifecycle(self, mock_db):
        """End-to-end: ingest → process → draft → dispatch → log."""

        # Patch the db singleton everywhere it's imported
        with (
            patch("ingest.loader.db", mock_db),
            patch("ingest.worker.db", mock_db),
            patch("generator.engine.db", mock_db),
            patch("src.orchestrator.default_db", mock_db),
        ):
            from src.orchestrator import run_pipeline, generate_drafts, dispatch_drafts

            # ---- Step 1 + 2: Ingest CSV + Process Inbox ----
            result = run_pipeline(TEST_CSV, source_name="E2E Test CSV", db=mock_db)

            assert result["status"] == "pipeline_complete"
            assert result["inbox_id"] is not None
            mock_db.ingest_raw.assert_called_once()
            # Verify the inbox was processed
            mock_db.mark_inbox_processed.assert_called()
            # People should have been upserted
            assert mock_db.upsert_person.call_count == 2

            # ---- Step 3: Create a template ----
            tmpl_id = mock_db.create_template(
                name="welcome_email",
                platform="email",
                content="Hello {{full_name}}, welcome to {{team}}!",
                required_keys=["full_name", "team"],
            )
            assert tmpl_id is not None

            # ---- Step 4: Generate drafts ----
            drafts = generate_drafts(
                template_name="welcome_email",
                role="student",
                db=mock_db,
            )

            assert len(drafts) == 2
            for draft in drafts:
                assert draft["status"] == "draft"
                assert draft["content"]  # not empty
                assert "[MOCK GENERATION]" in draft["content"]
                assert draft["template_id"] is not None
                assert draft["recipient_id"] is not None

            # Verify names appear in content (placeholder replacement)
            contents = " ".join(d["content"] for d in drafts)
            assert "Alice Johnson" in contents
            assert "Bob Smith" in contents

            # ---- Step 5: Dispatch (stub) ----
            dispatched = dispatch_drafts(drafts, db=mock_db)

            assert len(dispatched) == 2
            for d in dispatched:
                assert d["status"] == "sent"

            # ---- Step 6: Assert sent_logs ----
            assert mock_db.log_sent_message.call_count == 2

            # Check the actual log calls
            for log_call in mock_db.log_sent_message.call_args_list:
                kwargs = log_call[1]
                assert kwargs["status"] == "sent"
                assert kwargs["platform"] == "email"
                assert kwargs["compiled_msg"]  # not empty
                assert kwargs["error"] is None

    def test_pipeline_with_whatsapp_dispatch(self, mock_db):
        """Verify WhatsApp dispatch works end-to-end."""
        wa_template = _make_template(
            name="wa_reminder",
            platform="whatsapp",
            content="Hi {{full_name}}, reminder from {{team}}.",
            required_keys=["full_name", "team"],
        )
        mock_db.get_template.return_value = wa_template

        with (
            patch("ingest.loader.db", mock_db),
            patch("ingest.worker.db", mock_db),
            patch("generator.engine.db", mock_db),
            patch("src.orchestrator.default_db", mock_db),
        ):
            from src.orchestrator import generate_drafts, dispatch_drafts

            drafts = generate_drafts("wa_reminder", role="student", db=mock_db)
            assert len(drafts) == 2

            dispatched = dispatch_drafts(drafts, db=mock_db)
            for d in dispatched:
                assert d["status"] == "sent"

            # All logs should be whatsapp
            for log_call in mock_db.log_sent_message.call_args_list:
                assert log_call[1]["platform"] == "whatsapp"

    def test_dispatch_handles_missing_phone_for_whatsapp(self, mock_db):
        """If a user has no phone, WhatsApp dispatch should fail gracefully."""
        wa_template = _make_template(
            name="wa_test",
            platform="whatsapp",
            content="Hello {{full_name}}",
            required_keys=["full_name"],
        )
        mock_db.get_template.return_value = wa_template

        # One person with no phone
        no_phone_person = _make_person(
            "nophone@test.com", "No Phone", phone=None, profile_data={}
        )
        mock_db.get_people.return_value = [no_phone_person]

        with (
            patch("generator.engine.db", mock_db),
            patch("src.orchestrator.default_db", mock_db),
        ):
            from src.orchestrator import generate_drafts, dispatch_drafts

            drafts = generate_drafts("wa_test", db=mock_db)
            dispatched = dispatch_drafts(drafts, db=mock_db)

            assert len(dispatched) == 1
            assert dispatched[0]["status"] == "failed"

            # Log should reflect failure
            log_kw = mock_db.log_sent_message.call_args[1]
            assert log_kw["status"] == "failed"
            assert "phone" in log_kw["error"].lower()

    def test_empty_audience_returns_no_drafts(self, mock_db):
        """If no people match the filter, drafts should be empty."""
        mock_db.get_people.return_value = []

        with (
            patch("generator.engine.db", mock_db),
            patch("src.orchestrator.default_db", mock_db),
        ):
            from src.orchestrator import generate_drafts

            drafts = generate_drafts("welcome_email", role="admin", db=mock_db)
            assert drafts == []

    def test_missing_template_skips_generation(self, mock_db):
        """If the template doesn't exist, all users should be skipped."""
        mock_db.get_template.return_value = None

        with (
            patch("generator.engine.db", mock_db),
            patch("src.orchestrator.default_db", mock_db),
        ):
            from src.orchestrator import generate_drafts

            drafts = generate_drafts("nonexistent_template", db=mock_db)
            assert drafts == []
