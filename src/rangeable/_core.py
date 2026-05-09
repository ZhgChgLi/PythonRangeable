"""Main Rangeable container."""

from __future__ import annotations

from typing import Generic, Hashable, Iterator, TypeVar

from ._boundary_index import BoundaryIndex
from ._disjoint_set import DisjointSet, InsertResult
from ._errors import InvalidIntervalError
from ._slot import Slot
from ._transition import TransitionEvent

E = TypeVar("E", bound=Hashable)

_EMPTY_OBJS: tuple = ()


class Rangeable(Generic[E]):
    """Generic, integer-coordinate, closed-interval set container.

    Pairs hashable elements with their merged disjoint integer ranges
    and supports three query families:

    * by-element via :meth:`get_range`
    * by-position via ``r[i]`` / :meth:`active_at`
    * by-range via :meth:`transitions`

    See `RFC §3 <https://github.com/ZhgChgLi/RangeableRFC>`_ for the
    full normative API surface.
    """

    __slots__ = (
        "_intervals",
        "_insertion_order",
        "_ord",
        "_version",
        "_event_index",
    )

    def __init__(self) -> None:
        self._intervals: dict[E, DisjointSet] = {}
        self._insertion_order: list[E] = []
        self._ord: dict[E, int] = {}
        self._version: int = 0
        self._event_index: BoundaryIndex[E] | None = None

    @classmethod
    def empty(cls) -> "Rangeable[E]":
        """Sugar matching the RFC §3.1 ``Rangeable.empty()`` alias."""
        return cls()

    @property
    def version(self) -> int:
        return self._version

    def insert(self, element: E, *, start: int, end: int) -> "Rangeable[E]":
        """Insert ``element`` covering the closed interval ``[start, end]``.

        Idempotent per RFC §3.2: re-inserting a sub-range that is already
        fully contained leaves the container unchanged and does NOT bump
        :attr:`version`.

        Raises :class:`InvalidIntervalError` if ``start > end``.

        Returns ``self`` for chaining.
        """
        if start > end:
            raise InvalidIntervalError(f"start ({start}) > end ({end})")

        ds = self._intervals.get(element)
        if ds is None:
            ds = DisjointSet()
            self._intervals[element] = ds
            self._insertion_order.append(element)
            self._ord[element] = len(self._insertion_order)

        result = ds.insert(start, end)
        if result == InsertResult.MUTATED:
            self._version += 1
            self._event_index = None
        return self

    def __getitem__(self, i: int) -> Slot[E]:
        """Active-element list at ``i``. RFC §3.3.

        O(log |segments| + r) once the index is built. Returns an empty
        :class:`Slot` for coordinates outside every segment.
        """
        self._ensure_event_index_fresh()
        assert self._event_index is not None
        seg = self._event_index.segment_at(i)
        if seg is None:
            return Slot(_EMPTY_OBJS)
        return Slot(seg.active)

    def active_at(self, *, index: int) -> Slot[E]:
        """Same as ``self[index]``, named to match RFC §3.3."""
        return self[index]

    def get_range(self, element: E) -> list[tuple[int, int]]:
        """Merged ranges for ``element`` as ``[(lo, hi), ...]``. RFC §3.4.

        Returns an empty list when the element has never been inserted.
        """
        ds = self._intervals.get(element)
        if ds is None:
            return []
        return ds.to_pairs()

    def transitions(self, *, lo: int, hi: int | None) -> list[TransitionEvent[E]]:
        """Open / close events within the inclusive coordinate range
        ``[lo, hi]``. RFC §3.5.

        ``hi=None`` means +∞ (include all events through the upper bound).

        Raises :class:`InvalidIntervalError` if ``lo > hi`` or ``lo`` is
        ``None``.
        """
        if lo is None:
            raise InvalidIntervalError("transitions: lo must not be None")
        if hi is not None and lo > hi:
            raise InvalidIntervalError(f"lo ({lo}) > hi ({hi})")

        self._ensure_event_index_fresh()
        assert self._event_index is not None
        upper = None if hi is None else hi + 1
        return self._event_index.events_in_range(lo, upper)

    def __len__(self) -> int:
        """Number of distinct equivalence-class elements ever inserted."""
        return len(self._insertion_order)

    @property
    def count(self) -> int:
        return len(self._insertion_order)

    @property
    def empty(self) -> bool:
        return not self._insertion_order

    def __bool__(self) -> bool:
        return bool(self._insertion_order)

    def __iter__(self) -> Iterator[tuple[E, list[tuple[int, int]]]]:
        """Yield ``(element, ranges)`` pairs in insertion-order ascending."""
        for element in self._insertion_order:
            yield element, self._intervals[element].to_pairs()

    def copy(self) -> "Rangeable[E]":
        """Deep copy. Mutation on the copy MUST NOT affect this instance,
        and vice versa.
        """
        dup = Rangeable[E]()
        for element in self._insertion_order:
            dup._replant(element, self._intervals[element], self._ord[element])
        dup._version = self._version
        return dup

    def __copy__(self) -> "Rangeable[E]":
        return self.copy()

    def __deepcopy__(self, memo: dict) -> "Rangeable[E]":
        return self.copy()

    def _ensure_event_index_fresh(self) -> None:
        if self._event_index is not None and self._event_index.version == self._version:
            return
        v_start = self._version
        rebuilt = BoundaryIndex.build(self._intervals, self._ord, v_start)
        if self._version == v_start:
            self._event_index = rebuilt

    def _replant(self, element: E, source_set: DisjointSet, source_ord: int) -> None:
        new_set = DisjointSet()
        for iv in source_set:
            new_set.insert(iv.lo, iv.hi)
        self._intervals[element] = new_set
        self._insertion_order.append(element)
        self._ord[element] = source_ord
