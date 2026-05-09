"""Transition events emitted by ``Rangeable.transitions``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

E = TypeVar("E")


class TransitionKind(str, Enum):
    """Kind of a boundary event. Inherits from ``str`` so cross-language
    JSON fixtures can compare directly against ``"open"`` / ``"close"``.
    """

    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class TransitionEvent(Generic[E]):
    """A single boundary event in coordinate-sorted order.

    ``coordinate`` is normally an :class:`int`; it is ``None`` for close
    events whose underlying interval ends at the implementation's +∞
    sentinel (RFC §4.7 C4). Comparison treats ``None`` as greater than
    any finite int.
    """

    coordinate: int | None
    kind: TransitionKind
    element: E

    @property
    def is_open(self) -> bool:
        return self.kind == TransitionKind.OPEN

    @property
    def is_close(self) -> bool:
        return self.kind == TransitionKind.CLOSE
