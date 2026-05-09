"""Active-element list returned by ``Rangeable[i]``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar

E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Slot(Generic[E]):
    """Wraps the ordered tuple of elements active at a coordinate.

    ``objs`` is sorted by first-insertion order ascending (RFC §4.5).
    The same coordinate within an unmutated container always returns
    an equal ``Slot``.
    """

    objs: tuple[E, ...]

    def __len__(self) -> int:
        return len(self.objs)

    def __iter__(self) -> Iterator[E]:
        return iter(self.objs)

    def __bool__(self) -> bool:
        return bool(self.objs)

    @property
    def empty(self) -> bool:
        return not self.objs
