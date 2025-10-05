"""Error taxonomy enums used by telemetry logging."""
from __future__ import annotations

from enum import Enum


class ErrorType(str, Enum):
    """Standard error taxonomy for Scout telemetry."""

    VALUE_NOT_FOUND = "value_not_found"
    AMBIGUOUS_TIME = "ambiguous_time"
    COMPILE_ERROR = "compile_error"
    ROW_CAP_EXCEEDED = "row_cap_exceeded"
    ZERO_ROWS = "zero_rows"
    HALLUCINATION_GUARD = "hallucination_guard"
    UNKNOWN = "unknown"

    @classmethod
    def has_value(cls, value: str) -> bool:
        """Return True if *value* matches one of the enum members."""

        try:
            cls(value)
        except ValueError:
            return False
        return True
