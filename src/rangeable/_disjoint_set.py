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


class RemoveResult(Enum):
    """Outcome of :meth:`DisjointSet.remove`. The owning :class:`Rangeable`
    bumps its version counter only on ``MUTATED`` / ``MUTATED_BECAME_EMPTY``.

    ``MUTATED_BECAME_EMPTY`` additionally signals to the owner that the
    element MUST be eagerly pruned per RFC §4.10 (N1) — the per-element list
    is now empty and the key must be excised from ``intervals``,
    ``insertion_order``, and ``ord``.
    """

    IDEMPOTENT = "idempotent"
    MUTATED = "mutated"
    MUTATED_BECAME_EMPTY = "mutated_became_empty"


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

    def remove(self, lo: int, hi: int) -> RemoveResult:
        """Remove the closed interval ``[lo, hi]`` per RFC §6.6.

        Returns :attr:`RemoveResult.IDEMPOTENT` when no entry overlaps
        (caller MUST NOT bump version per §4.10 N3),
        :attr:`RemoveResult.MUTATED` when entries shrink but the list stays
        non-empty, :attr:`RemoveResult.MUTATED_BECAME_EMPTY` when the last
        interval is removed and the owner MUST eagerly prune the key per
        §4.10 (N1).
        """
        if lo > hi:
            raise InvalidIntervalError(f"lo ({lo}) > hi ({hi})")

        n = len(self._entries)
        # Step 3 of §6.6: bsearch for the leftmost entry with ``iv.hi >= lo``.
        # Equivalent (under the bisect-by-key contract) to
        # ``bisect_left(entries, lo, key=lambda iv: iv.hi + 1)`` — the same
        # predicate used by insert (and thus the same Int.min underflow guard).
        i = bisect.bisect_left(self._entries, lo, key=lambda iv: iv.hi + 1)

        # Step 4: quick-exit when nothing in R(e) overlaps [lo, hi].
        if i == n or self._entries[i].lo > hi:
            return RemoveResult.IDEMPOTENT

        # Step 5: sweep all overlapping entries, build replacements.
        to_replace_start = i
        replacements: list[Interval] = []
        while i < n and self._entries[i].lo <= hi:
            iv = self._entries[i]
            # Left residual only when iv.lo < lo (guards Int.min underflow
            # on ``lo - 1``).
            if iv.lo < lo:
                replacements.append(Interval(iv.lo, lo - 1))
            # Right residual only when hi < iv.hi (guards Int.max overflow
            # on ``hi + 1``).
            if hi < iv.hi:
                replacements.append(Interval(hi + 1, iv.hi))
            i += 1
        to_replace_end = i

        # Step 6: splice. Python's slice-assign is the natural primitive.
        self._entries[to_replace_start:to_replace_end] = replacements

        # Step 7: signal eager-prune to caller when list is now empty.
        if not self._entries:
            return RemoveResult.MUTATED_BECAME_EMPTY
        return RemoveResult.MUTATED

    # ------------------------------------------------------------------ #
    # List-level primitives for set operations (§6.10–§6.13).
    # These operate on Interval lists, not on DisjointSet instances, so
    # the union/intersection/difference/symmetric_difference paths can
    # reuse them without per-call DisjointSet construction overhead.
    # ------------------------------------------------------------------ #


def _append_or_merge(out: list[Interval], iv: Interval) -> None:
    """Two-pointer helper from RFC §6.10.

    Appends ``iv`` to ``out``, collapsing into the last entry when overlap
    or integer-adjacency (``out[-1].hi + 1 >= iv.lo``) is detected.
    """
    if not out or out[-1].hi + 1 < iv.lo:
        out.append(iv)
    else:
        last = out[-1]
        if iv.hi > last.hi:
            out[-1] = Interval(last.lo, iv.hi)


def merge_disjoint_lists(
    list_a: list[Interval], list_b: list[Interval]
) -> list[Interval]:
    """Two-pointer linear merge of two (I1)-canonical lists, RFC §6.10.

    O(|list_a| + |list_b|). Output is (I1)-canonical (sorted, disjoint,
    non-adjacent) thanks to ``_append_or_merge``'s adjacency collapse.
    """
    out: list[Interval] = []
    i, j = 0, 0
    n_a, n_b = len(list_a), len(list_b)
    while i < n_a and j < n_b:
        if list_a[i].lo <= list_b[j].lo:
            _append_or_merge(out, list_a[i])
            i += 1
        else:
            _append_or_merge(out, list_b[j])
            j += 1
    while i < n_a:
        _append_or_merge(out, list_a[i])
        i += 1
    while j < n_b:
        _append_or_merge(out, list_b[j])
        j += 1
    return out


def intersect_disjoint_lists(
    list_a: list[Interval], list_b: list[Interval]
) -> list[Interval]:
    """Two-pointer pairwise intersection, RFC §6.11.

    O(|list_a| + |list_b|). Output is (I1)-canonical without any explicit
    adjacency-collapse step (Lemma 6.11.A): consecutive output entries
    inherit a ≥ 2 integer gap from the inputs.
    """
    out: list[Interval] = []
    i, j = 0, 0
    n_a, n_b = len(list_a), len(list_b)
    while i < n_a and j < n_b:
        a_iv = list_a[i]
        b_iv = list_b[j]
        lo = a_iv.lo if a_iv.lo > b_iv.lo else b_iv.lo
        hi = a_iv.hi if a_iv.hi < b_iv.hi else b_iv.hi
        if lo <= hi:
            out.append(Interval(lo, hi))
        if a_iv.hi <= b_iv.hi:
            i += 1
        else:
            j += 1
    return out


def subtract_disjoint_lists(
    list_a: list[Interval], list_b: list[Interval]
) -> list[Interval]:
    """Two-pointer subtraction ``list_a ∖ list_b``, RFC §6.12.

    O(|list_a| + |list_b|). Output is (I1)-canonical. Underflow / overflow
    safe: ``L_b[j].lo - 1`` only computed when ``L_b[j].lo > current_lo``;
    ``L_b[j].hi + 1`` only when ``L_b[j].hi < current_hi``.
    """
    out: list[Interval] = []
    n_a, n_b = len(list_a), len(list_b)
    if n_a == 0:
        return out
    if n_b == 0:
        return list(list_a)

    i = 0
    j = 0
    current_lo: int | None = None
    current_hi: int | None = None
    while i < n_a:
        if current_lo is None:
            current_lo = list_a[i].lo
            current_hi = list_a[i].hi
        # Skip L_b entries strictly before [current_lo, current_hi].
        while j < n_b and list_b[j].hi < current_lo:
            j += 1
        if j == n_b or list_b[j].lo > current_hi:
            # No more cuts on this entry: commit and advance.
            out.append(Interval(current_lo, current_hi))
            i += 1
            current_lo = None
            current_hi = None
            continue
        # list_b[j] overlaps [current_lo, current_hi]; cut.
        if list_b[j].lo > current_lo:
            out.append(Interval(current_lo, list_b[j].lo - 1))
        if list_b[j].hi < current_hi:
            # Right residual becomes the new current.
            current_lo = list_b[j].hi + 1
            j += 1
        else:
            # list_b[j] swallows the rest of the current entry.
            i += 1
            current_lo = None
            current_hi = None
    return out
