"""Tests for enum values — ensures they stay consistent with the LLM prompts."""

from app.core.enums import Intent, WSMessageType, ModelTier


class TestIntent:
    def test_values(self):
        assert Intent.CREATE == "create"
        assert Intent.MODIFY == "modify"
        assert Intent.FIX == "fix"

    def test_string_comparison(self):
        """Enums should work in string comparisons (StrEnum)."""
        assert Intent.CREATE == "create"
        assert "create" == Intent.CREATE


class TestWSMessageType:
    def test_values(self):
        assert WSMessageType.STATUS == "status"
        assert WSMessageType.RESULT == "result"
        assert WSMessageType.ERROR == "error"


class TestModelTier:
    def test_values(self):
        assert ModelTier.LARGE == "large"
        assert ModelTier.SMALL == "small"
