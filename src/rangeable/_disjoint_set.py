"""Sorted, disjoint, non-adjacent merged-interval list for one element."""

from __future__ import annotations

import bisect
from enum import Enum
from typing import Iterator

from ._errors import InvalidIntervalError
from ._interval import Interval


class InsertResult(Enum):
    """Outcome of :meth:`DisjointSet.insert`. The owning :class:`Rangeable`
    bumps its version counter only on ``MUTATED``; ``IDEMPOTENT`` means the
    insert was absorbed and the canonical state is unchanged (RFC Test #21,
    Lemma 6.5.B).
    """

    MUTATED = "mutated"
    IDEMPOTENT = "idempotent"


class DisjointSet:
    """Maintains the RFC §5.1 (I1) invariant for one element:

    * sorted by ``lo`` strictly ascending
    * any two adjacent entries ``(lo1, hi1), (lo2, hi2)`` satisfy
      ``hi1 + 1 < lo2`` (no overlap, no integer adjacency)
    * ``lo <= hi`` for every entry

    Mirrors the Ruby reference implementation line-for-line, including
    the §6.1 cleaner-variant containment fast-path.
    """

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: list[Interval] = []

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[Interval]:
        return iter(self._entries)

    @property
    def empty(self) -> bool:
        return not self._entries

    def to_pairs(self) -> list[tuple[int, int]]:
        """Snapshot the merged intervals as ``[(lo, hi), ...]``."""
        return [(iv.lo, iv.hi) for iv in self._entries]

    def insert(self, lo: int, hi: int) -> InsertResult:
        """Insert ``[lo, hi]`` into the set, performing union-with-merge per
        RFC §6.1.

        Returns :attr:`InsertResult.MUTATED` if the canonical state changed
        (caller should bump version), :attr:`InsertResult.IDEMPOTENT` if the
        insert was absorbed by an existing entry (caller MUST NOT bump
        version, per Test #21 and Lemma 6.5.B).
        """
        if lo > hi:
            raise InvalidIntervalError(f"lo ({lo}) > hi ({hi})")

        # Step 4 of §6.1: bsearch for the leftmost touch candidate.
        # Predicate: ``iv.hi + 1 >= lo``. We use ``iv.hi + 1`` (not
        # ``lo - 1``) to avoid Integer underflow at ``lo == Int.min``
        # boundaries (§4.7 C5). Python ints are unbounded but we mirror
        # the Ruby form for cross-language byte parity.
        i0 = bisect.bisect_left(
            self._entries, lo, key=lambda iv: iv.hi + 1
        )

        # Step 5: collect contiguous touch entries while
        # ``entries[i].lo <= hi + 1``.
        to_merge_end = i0
        n = len(self._entries)
        while to_merge_end < n and self._entries[to_merge_end].lo <= hi + 1:
            to_merge_end += 1
        merge_count = to_merge_end - i0

        # Step 6: containment idempotent fast-path. If we touch exactly one
        # existing entry that fully covers [lo, hi], this insert is a no-op.
        # MUST NOT mutate, MUST NOT bump version.
        if merge_count == 1:
            existing = self._entries[i0]
            if existing.lo <= lo and hi <= existing.hi:
                return InsertResult.IDEMPOTENT

        # Step 7: real mutation path. Compute merged bounds, splice in.
        new_lo = lo
        new_hi = hi
        if merge_count > 0:
            first = self._entries[i0]
            last = self._entries[to_merge_end - 1]
            if first.lo < new_lo:
                new_lo = first.lo
            if last.hi > new_hi:
                new_hi = last.hi
        merged = Interval(new_lo, new_hi)
        self._entries[i0:to_merge_end] = [merged]
        return InsertResult.MUTATED
