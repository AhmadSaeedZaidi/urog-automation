"""Tests for the ContentEngine: validate_data and generate_message."""

from unittest.mock import patch
from generator.engine import ContentEngine


# --------------------------------------------------
# ContentEngine instantiation
# --------------------------------------------------


class TestContentEngineInit:
    """Test engine initialization and MOCK_MODE activation."""

    def test_mock_mode_active_without_api_key(self):
        """Engine should enter MOCK_MODE when GEMINI_API_KEY is absent."""
        engine = ContentEngine()
        assert engine.mock_mode is True

    @patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key-123"})
    @patch("generator.engine.genai.Client")
    def test_real_mode_with_api_key(self, mock_client_cls):
        """Engine should NOT be in mock mode when an API key is set."""
        engine = ContentEngine()
        assert engine.mock_mode is False
        mock_client_cls.assert_called_once_with(api_key="fake-key-123")

    @patch.dict("os.environ", {"GEMINI_API_KEY": "bad-key"})
    @patch("generator.engine.genai.Client")
    def test_falls_back_to_mock_on_api_error(self, mock_client_cls):
        """If genai.Client raises, engine should fallback to MOCK_MODE."""
        mock_client_cls.side_effect = Exception("Invalid API key")
        engine = ContentEngine()
        assert engine.mock_mode is True


# --------------------------------------------------
# validate_data
# --------------------------------------------------


class TestValidateData:
    """Test the validate_data method."""

    def setup_method(self):
        self.engine = ContentEngine()

    def test_valid_data_returns_true(self, sample_user):
        """All required keys present -> (True, [])."""
        is_valid, missing = self.engine.validate_data(
            ["full_name", "team"], sample_user
        )
        assert is_valid is True
        assert missing == []

    def test_missing_key_returns_false(self, sample_user_missing_keys):
        """Missing 'team' key -> (False, ['team'])."""
        is_valid, missing = self.engine.validate_data(
            ["full_name", "team"], sample_user_missing_keys
        )
        assert is_valid is False
        assert "team" in missing

    def test_no_required_keys_always_valid(self, sample_user):
        """None required_keys -> always valid."""
        is_valid, missing = self.engine.validate_data(None, sample_user)
        assert is_valid is True
        assert missing == []

    def test_empty_required_keys_always_valid(self, sample_user):
        """Empty list required_keys -> always valid."""
        is_valid, missing = self.engine.validate_data([], sample_user)
        assert is_valid is True

    def test_profile_data_string_parsed(self):
        """If profile_data is a JSON string, it should be parsed."""
        user = {
            "email": "x@test.com",
            "profile_data": '{"team": "Research"}',
        }
        is_valid, missing = self.engine.validate_data(["team"], user)
        assert is_valid is True

    def test_profile_data_bad_json_string(self):
        """Invalid JSON string for profile_data should not crash."""
        user = {
            "email": "x@test.com",
            "profile_data": "not-json",
        }
        # 'team' is not in user nor in the bad profile_data
        is_valid, missing = self.engine.validate_data(["team"], user)
        assert is_valid is False
        assert "team" in missing


# --------------------------------------------------
# generate_message  (MOCK MODE only)
# --------------------------------------------------


class TestGenerateMessageMock:
    """Test generate_message in MOCK_MODE (no real API calls)."""

    def setup_method(self):
        self.engine = ContentEngine()
        assert self.engine.mock_mode is True  # safety check

    def test_template_not_found(self, mock_dao_db, sample_user):
        """Missing template should return an error status."""
        mock_dao_db.get_template.return_value = None

        result = self.engine.generate_message("nonexistent", sample_user)

        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_missing_required_data(
        self, mock_dao_db, sample_template, sample_user_missing_keys
    ):
        """Missing required keys should return failed status."""
        mock_dao_db.get_template.return_value = sample_template

        result = self.engine.generate_message("welcome_email", sample_user_missing_keys)

        assert result["status"] == "failed"
        assert "Missing required data" in result["error"]

    def test_successful_mock_generation(
        self, mock_dao_db, sample_template, sample_user
    ):
        """Successful mock generation should return content with placeholders filled."""
        mock_dao_db.get_template.return_value = sample_template

        result = self.engine.generate_message("welcome_email", sample_user)

        assert result["status"] == "success"
        assert "template_id" in result
        assert result["template_id"] == "tmpl-uuid-001"
        # Content should be wrapped in MOCK markers
        assert "[MOCK GENERATION]" in result["content"]
        assert "[END MOCK]" in result["content"]

    def test_mock_fills_placeholders(self, mock_dao_db, sample_template, sample_user):
        """Mock mode should replace {{key}} placeholders with user data."""
        mock_dao_db.get_template.return_value = sample_template

        result = self.engine.generate_message("welcome_email", sample_user)

        assert "Alice Johnson" in result["content"]
        assert "Education" in result["content"]
        # Original placeholders should be gone
        assert "{{full_name}}" not in result["content"]
        assert "{{team}}" not in result["content"]

    def test_no_required_keys_template(
        self, mock_dao_db, template_no_required_keys, sample_user
    ):
        """Template with no required_keys should still generate successfully."""
        mock_dao_db.get_template.return_value = template_no_required_keys

        result = self.engine.generate_message("general_announcement", sample_user)

        assert result["status"] == "success"

    def test_context_override_does_not_crash(
        self, mock_dao_db, sample_template, sample_user
    ):
        """Passing context_override should not crash MOCK mode."""
        mock_dao_db.get_template.return_value = sample_template

        result = self.engine.generate_message(
            "welcome_email", sample_user, context_override="Be extra friendly"
        )

        assert result["status"] == "success"
