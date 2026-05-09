"""Closed integer interval [lo, hi]."""

from __future__ import annotations

from dataclasses import dataclass

from ._errors import InvalidIntervalError


@dataclass(frozen=True, slots=True)
class Interval:
    """Immutable closed integer interval [lo, hi].

    Both ends are inclusive, matching RFC §4.1. ``lo > hi`` raises
    :class:`InvalidIntervalError` at construction time.
    """

    lo: int
    hi: int

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise InvalidIntervalError(f"lo ({self.lo}) > hi ({self.hi})")

    def __contains__(self, coord: int) -> bool:
        return self.lo <= coord <= self.hi

    def to_tuple(self) -> tuple[int, int]:
        return (self.lo, self.hi)
