"""Main Rangeable container."""

from __future__ import annotations

from typing import Generic, Hashable, Iterator, TypeVar

from ._boundary_index import BoundaryIndex
from ._disjoint_set import (
    DisjointSet,
    InsertResult,
    RemoveResult,
    intersect_disjoint_lists,
    merge_disjoint_lists,
    subtract_disjoint_lists,
)
from ._errors import InvalidIntervalError
from ._interval import Interval
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

    # ------------------------------------------------------------------ #
    # v2 — Removal API (RFC §6.6–§6.9, §10.B)
    # ------------------------------------------------------------------ #

    def remove(self, element: E, *, start: int, end: int) -> "Rangeable[E]":
        """Remove the closed interval ``[start, end]`` from ``R(element)``.

        RFC §6.6. Idempotent per §4.10 (N3): if ``element`` is absent or
        ``[start, end]`` does not overlap any existing interval, this is a
        no-op and :attr:`version` MUST NOT bump.

        If the removal empties ``R(element)`` it is eagerly pruned per
        §4.10 (N1): the key is dropped from ``intervals``, removed from
        ``insertion_order``, and surviving elements' ``ord`` are densely
        renumbered.

        Raises :class:`InvalidIntervalError` if ``start > end``. Returns
        ``self`` for chaining.
        """
        if start > end:
            raise InvalidIntervalError(f"start ({start}) > end ({end})")

        ds = self._intervals.get(element)
        if ds is None:
            return self  # §6.6 step 2: no R(e) to subtract from.

        result = ds.remove(start, end)
        if result == RemoveResult.IDEMPOTENT:
            return self
        if result == RemoveResult.MUTATED_BECAME_EMPTY:
            self._excise_element(element)
        # Both MUTATED and MUTATED_BECAME_EMPTY paths bump version once.
        self._version += 1
        self._event_index = None
        return self

    def remove_element(self, element: E) -> "Rangeable[E]":
        """Excise ``element`` and its entire ``R(element)``. RFC §6.7.

        Idempotent per §4.10 (N3): no-op (no version bump) when the element
        is absent. Returns ``self`` for chaining.
        """
        if element not in self._intervals:
            return self
        self._excise_element(element)
        self._version += 1
        self._event_index = None
        return self

    def __delitem__(self, key: E) -> None:
        """``del r[e]`` is sugar for :meth:`remove_element`. RFC §6.7.

        Note: ``r[i]`` is the integer-subscript probe returning a
        :class:`Slot`, so ``del r[e]`` only makes sense when ``e`` is an
        element instance, not an index. Mixing the two APIs is a caller
        bug.
        """
        self.remove_element(key)

    def clear(self) -> "Rangeable[E]":
        """Reset to the empty container. RFC §6.8.

        Idempotent per §4.10 (N3): clearing an already-empty container is
        a no-op (no version bump). Returns ``self`` for chaining.
        """
        if not self._intervals:
            return self
        self._intervals = {}
        self._insertion_order = []
        self._ord = {}
        self._version += 1
        self._event_index = None
        return self

    def remove_ranges(self, *, start: int, end: int) -> "Rangeable[E]":
        """Apply ``remove(e, start, end)`` for every ``e`` atomically.

        RFC §6.9. A single :attr:`version` bump for the entire op; eager
        pruning happens for every element whose ``R(e)`` becomes empty.

        Raises :class:`InvalidIntervalError` if ``start > end`` BEFORE any
        mutation. Returns ``self`` for chaining.
        """
        if start > end:
            raise InvalidIntervalError(f"start ({start}) > end ({end})")

        any_change = False
        # Iterate a snapshot — we mutate `self._intervals` in the loop.
        for element in list(self._insertion_order):
            ds = self._intervals[element]
            result = ds.remove(start, end)
            if result == RemoveResult.IDEMPOTENT:
                continue
            any_change = True
            if result == RemoveResult.MUTATED_BECAME_EMPTY:
                # DEFER insertion_order / ord rebuild until the loop ends
                # to avoid O(E^2). Just drop the intervals key here.
                del self._intervals[element]

        if not any_change:
            return self

        # Single-pass dense rebuild of insertion_order + ord (§6.9 step 4).
        survivors = [e for e in self._insertion_order if e in self._intervals]
        self._insertion_order = survivors
        self._ord = {e: i + 1 for i, e in enumerate(survivors)}
        self._version += 1
        self._event_index = None
        return self

    def _excise_element(self, element: E) -> None:
        """Excise ``element`` from intervals + insertion_order + ord with
        a dense ``ord`` renumber over the survivors past its position.

        Caller is responsible for the single ``version`` bump and
        ``event_index`` invalidation that wraps the whole op.
        """
        del self._intervals[element]
        idx = self._insertion_order.index(element)
        del self._insertion_order[idx]
        del self._ord[element]
        # Densely renumber ord for survivors at positions >= idx.
        for i in range(idx, len(self._insertion_order)):
            self._ord[self._insertion_order[i]] -= 1

    # ------------------------------------------------------------------ #
    # v2 — Set Operations API (RFC §6.10–§6.13, §10.C–§10.G)
    # ------------------------------------------------------------------ #

    def union(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """Per-element union with ``other``. RFC §6.10.

        Returns a fresh :class:`Rangeable` with ``version == 0``;
        ``self`` and ``other`` are unchanged. Insertion order: preserve
        ``self``'s order, then tail-append keys in
        ``keys(other) ∖ keys(self)`` in ``other``'s insertion-order order.
        """
        out: Rangeable[E] = Rangeable()
        # Step 1: walk self.insertion_order — every key in self appears.
        for element in self._insertion_order:
            list_self = self._intervals[element]._entries
            other_ds = other._intervals.get(element)
            if other_ds is None:
                merged_entries = list(list_self)
            else:
                merged_entries = merge_disjoint_lists(
                    list_self, other_ds._entries
                )
            out._populate(element, merged_entries)
        # Step 2: tail-append keys in other ∖ self.
        for element in other._insertion_order:
            if element in self._intervals:
                continue
            merged_entries = list(other._intervals[element]._entries)
            out._populate(element, merged_entries)
        return out

    def intersection(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """Per-element intersection with ``other``. RFC §6.11.

        Returns a fresh :class:`Rangeable`. Empty per-element results are
        eagerly pruned (§4.10 N1). Insertion order: ``self``'s order over
        surviving keys with densely renumbered ``ord``.
        """
        out: Rangeable[E] = Rangeable()
        for element in self._insertion_order:
            other_ds = other._intervals.get(element)
            if other_ds is None:
                continue
            intersected = intersect_disjoint_lists(
                self._intervals[element]._entries, other_ds._entries
            )
            if not intersected:
                continue  # eager prune (§4.10 N1)
            out._populate(element, intersected)
        return out

    def difference(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """Per-element ``self ∖ other``. RFC §6.12.

        Returns a fresh :class:`Rangeable`. Empty results pruned (§4.10).
        Insertion order: ``self``'s order over survivors, dense ``ord``.
        """
        out: Rangeable[E] = Rangeable()
        for element in self._insertion_order:
            list_self = self._intervals[element]._entries
            other_ds = other._intervals.get(element)
            if other_ds is None or not other_ds._entries:
                remaining = list(list_self)
            else:
                remaining = subtract_disjoint_lists(
                    list_self, other_ds._entries
                )
            if not remaining:
                continue  # eager prune
            out._populate(element, remaining)
        return out

    def symmetric_difference(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """Per-element ``self △ other``. RFC §6.13.

        Returns a fresh :class:`Rangeable`. Implemented via the algebraic
        identity ``(self ∖ other) ∪ (other ∖ self)`` per element with
        ``merge_disjoint_lists`` to collapse the adjacency case (§6.13
        worked example: ``[(0,5)] △ [(6,10)] == [(0,10)]``).
        """
        out: Rangeable[E] = Rangeable()
        # Step 1: self-primary keys.
        for element in self._insertion_order:
            list_self = self._intervals[element]._entries
            other_ds = other._intervals.get(element)
            if other_ds is None:
                # b is empty; sym = a = list_self.
                out._populate(element, list(list_self))
                continue
            list_other = other_ds._entries
            a = subtract_disjoint_lists(list_self, list_other)
            b = subtract_disjoint_lists(list_other, list_self)
            sym = merge_disjoint_lists(a, b)
            if not sym:
                continue  # eager prune (§4.10 N1)
            out._populate(element, sym)
        # Step 2: other-only keys.
        for element in other._insertion_order:
            if element in self._intervals:
                continue
            sym = list(other._intervals[element]._entries)
            if not sym:
                continue  # defensive; unreachable under (I1.4)
            out._populate(element, sym)
        return out

    # -------------------------- Mutating set ops ---------------------- #

    def update(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """In-place union (``self`` becomes ``self ∪ other``). RFC §6.10.

        Idempotent: if the result is structurally equal to ``self`` the
        version MUST NOT bump (set-naming convention; mirrors §3.2's
        idempotence rule). Returns ``self`` for chaining.
        """
        result = self.union(other)
        self._adopt_if_changed(result)
        return self

    def intersection_update(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """In-place intersection. RFC §6.11.

        No-op if result is structurally equal to ``self``. Returns ``self``.
        """
        result = self.intersection(other)
        self._adopt_if_changed(result)
        return self

    def difference_update(self, other: "Rangeable[E]") -> "Rangeable[E]":
        """In-place ``self := self ∖ other``. RFC §6.12. Returns ``self``."""
        result = self.difference(other)
        self._adopt_if_changed(result)
        return self

    def symmetric_difference_update(
        self, other: "Rangeable[E]"
    ) -> "Rangeable[E]":
        """In-place ``self := self △ other``. RFC §6.13. Returns ``self``."""
        result = self.symmetric_difference(other)
        self._adopt_if_changed(result)
        return self

    # ------------------------------- Operators ------------------------ #

    def __or__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        return self.union(other)

    def __and__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        return self.intersection(other)

    def __sub__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        return self.difference(other)

    def __xor__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        return self.symmetric_difference(other)

    def __ior__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        self.update(other)
        return self

    def __iand__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        self.intersection_update(other)
        return self

    def __isub__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        self.difference_update(other)
        return self

    def __ixor__(self, other: "Rangeable[E]") -> "Rangeable[E]":
        self.symmetric_difference_update(other)
        return self

    # ---------------------- Internal helpers (set ops) ---------------- #

    def _populate(self, element: E, entries: list[Interval]) -> None:
        """Internal-only: append ``element`` with already-(I1)-canonical
        ``entries`` to a freshly-built result container.

        Bypasses :meth:`insert`'s per-call version bump and event-index
        invalidation. ``entries`` MUST be sorted, disjoint, non-adjacent;
        callers (set-op kernels) guarantee this via
        ``merge_disjoint_lists`` / ``intersect_disjoint_lists`` /
        ``subtract_disjoint_lists``.
        """
        ds = DisjointSet()
        ds._entries = list(entries)
        self._intervals[element] = ds
        self._insertion_order.append(element)
        self._ord[element] = len(self._insertion_order)

    def _structurally_equal(self, other: "Rangeable[E]") -> bool:
        """Structural equality test for the no-op-no-bump rule on the
        mutating set ops (§6.10–§6.13 idempotence dual of §3.2).

        Compares ``insertion_order`` (ordered) and per-element interval
        tuples (already canonical under (I1)).
        """
        if self._insertion_order != other._insertion_order:
            return False
        for element in self._insertion_order:
            if (
                self._intervals[element]._entries
                != other._intervals[element]._entries
            ):
                return False
        return True

    def _adopt_if_changed(self, result: "Rangeable[E]") -> None:
        """Adopt ``result``'s state in-place when it differs structurally
        from ``self``. Bumps version exactly once when adoption happens.
        """
        if self._structurally_equal(result):
            return  # idempotent: no version bump per §3.2 dual.
        self._intervals = result._intervals
        self._insertion_order = result._insertion_order
        self._ord = result._ord
        self._version += 1
        self._event_index = None
