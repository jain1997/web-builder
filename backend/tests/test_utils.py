"""Tests for agent utilities — extract_json and retry_on_error."""

import pytest
from app.agents.utils import extract_json, retry_on_error


class TestExtractJSON:
    """Tests for the extract_json helper."""

    def test_clean_json(self):
        result = extract_json('{"intent": "create", "files": []}')
        assert result["intent"] == "create"
        assert result["files"] == []

    def test_json_with_markdown_fences(self):
        text = '```json\n{"intent": "modify", "plan": "update header"}\n```'
        result = extract_json(text)
        assert result["intent"] == "modify"
        assert result["plan"] == "update header"

    def test_json_with_surrounding_text(self):
        text = 'Here is the plan:\n{"intent": "fix", "files": []}\nThat should work.'
        result = extract_json(text)
        assert result["intent"] == "fix"

    def test_nested_json(self):
        text = '{"files": [{"path": "App.tsx", "description": "main"}]}'
        result = extract_json(text)
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "App.tsx"

    def test_json_with_code_content(self):
        """JSON containing code strings with braces should parse correctly."""
        text = '{"code": "function App() { return <div>Hello</div>; }"}'
        result = extract_json(text)
        assert "function App()" in result["code"]

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("This has no JSON at all.")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_json_with_trailing_garbage(self):
        text = '{"intent": "create"}extra stuff here'
        result = extract_json(text)
        assert result["intent"] == "create"

    def test_multiline_json(self):
        text = """{
            "intent": "create",
            "plan": "build a form",
            "files": [
                {"path": "App.tsx", "description": "main app"}
            ]
        }"""
        result = extract_json(text)
        assert result["intent"] == "create"
        assert len(result["files"]) == 1


class TestRetryOnError:
    """Tests for the retry_on_error decorator."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        call_count = 0

        @retry_on_error(retries=2)
        async def succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeeds()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_succeed(self):
        call_count = 0

        @retry_on_error(retries=2)
        async def fails_then_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("fail")
            return "ok"

        result = await fails_then_succeeds()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self):
        @retry_on_error(retries=1)
        async def always_fails():
            raise ValueError("permanent failure")

        with pytest.raises(ValueError, match="permanent failure"):
            await always_fails()
