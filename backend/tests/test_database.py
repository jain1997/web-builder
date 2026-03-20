"""Tests for SQLite database operations."""

import os
import tempfile

import pytest
import pytest_asyncio

# Override DATABASE_PATH before importing the module
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_PATH"] = _tmp.name
os.environ["OPENAI_API_KEY"] = "sk-test-dummy"

from app.core import database as db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Initialize a fresh DB for each test."""
    await db.init_db()
    yield
    await db.close_db()


class TestSessions:
    @pytest.mark.asyncio
    async def test_ensure_session_creates_new(self):
        session = await db.ensure_session("test-session-1")
        assert session["id"] == "test-session-1"
        assert session["project"] == ""

    @pytest.mark.asyncio
    async def test_ensure_session_returns_existing(self):
        await db.ensure_session("test-session-2")
        session = await db.ensure_session("test-session-2")
        assert session["id"] == "test-session-2"

    @pytest.mark.asyncio
    async def test_update_project(self):
        await db.ensure_session("test-session-3")
        await db.update_session_project("test-session-3", "My Project")
        session = await db.ensure_session("test-session-3")
        assert session["project"] == "My Project"


class TestTurns:
    @pytest.mark.asyncio
    async def test_save_turn(self):
        turn_id = await db.save_turn(
            "turn-session-1",
            prompt="build a form",
            intent="create",
            plan="Create a contact form",
            files_touched=["App.tsx"],
            errors=[],
            fix_summary="",
        )
        assert turn_id is not None
        assert turn_id > 0

    @pytest.mark.asyncio
    async def test_save_turn_with_files(self):
        turn_id = await db.save_turn(
            "turn-session-2",
            prompt="build a form",
            intent="create",
            plan="Create a contact form",
            files_touched=["App.tsx"],
            errors=[],
            fix_summary="",
            generated_files={"App.tsx": "export default function App() {}"},
        )
        # Verify snapshot was saved
        code = await db.get_previous_file("turn-session-2", "App.tsx")
        assert code == "export default function App() {}"

    @pytest.mark.asyncio
    async def test_save_turn_skips_images(self):
        await db.save_turn(
            "turn-session-3",
            prompt="build site",
            intent="create",
            plan="Site with image",
            files_touched=["App.tsx", "images/hero.png"],
            errors=[],
            fix_summary="",
            generated_files={
                "App.tsx": "export default function App() {}",
                "images/hero.png": "data:image/png;base64,abc123",
            },
        )
        # Image should NOT be in snapshots
        img = await db.get_previous_file("turn-session-3", "images/hero.png")
        assert img is None
        # Code should be there
        code = await db.get_previous_file("turn-session-3", "App.tsx")
        assert code is not None


class TestQueries:
    @pytest.mark.asyncio
    async def test_planner_context_empty_session(self):
        ctx = await db.get_planner_context("nonexistent-session")
        assert ctx == ""

    @pytest.mark.asyncio
    async def test_planner_context_with_turns(self):
        await db.save_turn(
            "ctx-session",
            prompt="build a todo app",
            intent="create",
            plan="Todo app with list",
            files_touched=["App.tsx", "components/TodoList.tsx"],
            errors=[],
            fix_summary="",
        )
        ctx = await db.get_planner_context("ctx-session")
        assert "SESSION MEMORY" in ctx
        assert "todo app" in ctx.lower()

    @pytest.mark.asyncio
    async def test_file_context_with_errors(self):
        await db.save_turn(
            "err-session",
            prompt="fix header",
            intent="fix",
            plan="Fix header component",
            files_touched=["components/Header.tsx"],
            errors=["TypeError: Cannot read property 'map' of undefined"],
            fix_summary="Added null check for array",
        )
        ctx = await db.get_file_context("err-session", "components/Header.tsx")
        assert "FILE HISTORY" in ctx
        assert "map" in ctx

    @pytest.mark.asyncio
    async def test_file_context_no_errors(self):
        ctx = await db.get_file_context("no-errors-session", "App.tsx")
        assert ctx == ""

    @pytest.mark.asyncio
    async def test_get_previous_file(self):
        await db.save_turn(
            "snap-session",
            prompt="build form",
            intent="create",
            plan="Form",
            files_touched=["App.tsx"],
            errors=[],
            fix_summary="",
            generated_files={"App.tsx": "// version 1"},
        )
        await db.save_turn(
            "snap-session",
            prompt="update form",
            intent="modify",
            plan="Update form",
            files_touched=["App.tsx"],
            errors=[],
            fix_summary="",
            generated_files={"App.tsx": "// version 2"},
        )
        # Should return the latest version
        code = await db.get_previous_file("snap-session", "App.tsx")
        assert code == "// version 2"
