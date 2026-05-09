"""Error types for Rangeable."""

from __future__ import annotations


class RangeableError(ValueError):
    """Base class for Rangeable errors. Subclasses ValueError so callers can
    catch generic value-related issues alongside Rangeable-specific ones.
    """


class InvalidIntervalError(RangeableError):
    """Raised when an interval is malformed (start > end), or a transitions
    query range is malformed (lo > hi, or lo is None). RFC §3.7 / §3.2 / §3.5.
    """
