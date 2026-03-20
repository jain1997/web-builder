"""Shared enums — eliminates magic strings across the codebase."""

from enum import StrEnum


class Intent(StrEnum):
    CREATE = "create"
    MODIFY = "modify"
    FIX = "fix"


class WSMessageType(StrEnum):
    STATUS = "status"
    RESULT = "result"
    ERROR = "error"


class ModelTier(StrEnum):
    LARGE = "large"   # Brief tasks: planning
    SMALL = "small"   # Exhaustive tasks: code gen, validation
