"""Lazy boundary-event index per RFC §5.2 / §6.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar

from ._transition import TransitionEvent, TransitionKind

E = TypeVar("E", bound=Hashable)


@dataclass(frozen=True, slots=True)
class _RawEvent(Generic[E]):
    """Internal event carrying the ord tiebreaker. Public API exposes
    :class:`TransitionEvent` (without ord)."""

    coordinate: int | None
    kind: TransitionKind
    element: E
    ord: int


@dataclass(frozen=True, slots=True)
class Segment(Generic[E]):
    """One maximal run of integers over which the active set is constant."""

    lo: int
    hi: int
    active: tuple[E, ...]


def _compare_coord(a: int | None, b: int | None) -> int:
    """Total order over coordinates: ``None`` (== +∞) is greater than any
    finite int. Returns -1 / 0 / +1.
    """
    if a is None and b is None:
        return 0
    if a is None:
        return 1
    if b is None:
        return -1
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _coord_le(coord: int | None, upper: int | None) -> bool:
    return _compare_coord(coord, upper) <= 0


def _coord_ge(coord: int | None, threshold: int | None) -> bool:
    return _compare_coord(coord, threshold) >= 0


class BoundaryIndex(Generic[E]):
    """Built from a snapshot of the per-element interval map plus the
    insertion-order map ``ord``. Carries:

    * ``events``   — sorted tuple of :class:`TransitionEvent` under §4.5
      ordering (without the internal ``ord`` field).
    * ``segments`` — sorted, disjoint tuple of :class:`Segment` covering
      every coordinate at which the active set is non-empty. Active sets
      are sorted by ``ord(e)`` ascending.
    * ``version``  — snapshot of :class:`Rangeable` version at build time.

    The owner :class:`Rangeable` invalidates the index by setting its
    reference to ``None`` on any mutation; reads compare versions to
    decide whether to rebuild (T3 mutex pattern, §11).
    """

    __slots__ = ("events", "segments", "version", "_raw_events")

    def __init__(
        self,
        events: tuple[TransitionEvent[E], ...],
        segments: tuple[Segment[E], ...],
        version: int,
        raw_events: tuple[_RawEvent[E], ...],
    ) -> None:
        self.events = events
        self.segments = segments
        self.version = version
        self._raw_events = raw_events

    def segment_at(self, coord: int) -> Segment[E] | None:
        """Find the segment containing ``coord``, or ``None`` if none.
        O(log |segments|). ``coord`` must be a finite int.
        """
        segs = self.segments
        lo, hi = 0, len(segs)
        while lo < hi:
            mid = (lo + hi) // 2
            if segs[mid].hi >= coord:
                hi = mid
            else:
                lo = mid + 1
        if lo >= len(segs):
            return None
        seg = segs[lo]
        return seg if seg.lo <= coord else None

    def events_in_range(
        self, lo: int, upper_coord: int | None
    ) -> list[TransitionEvent[E]]:
        """Returns events whose coordinate falls in ``[lo, upper_coord]``.
        ``upper_coord`` may be ``None`` to mean +∞.
        """
        events = self.events
        n = len(events)
        # Binary search for first index i where events[i].coordinate >= lo.
        l, r = 0, n
        while l < r:
            m = (l + r) // 2
            if _coord_ge(events[m].coordinate, lo):
                r = m
            else:
                l = m + 1
        result: list[TransitionEvent[E]] = []
        i = l
        while i < n and _coord_le(events[i].coordinate, upper_coord):
            result.append(events[i])
            i += 1
        return result

    @classmethod
    def build(
        cls,
        intervals: dict,  # element -> DisjointSet
        ord_map: dict,  # element -> int
        snapshot_version: int,
        int_max_sentinel: int | None = None,
    ) -> "BoundaryIndex[E]":
        """Build a fresh index. ``int_max_sentinel`` (default ``None``) lets
        the caller opt into "treat ``hi == sentinel`` as +∞" semantics for
        cross-language fixture parity with bounded-int languages.
        """
        raw: list[_RawEvent] = []
        for element, ds in intervals.items():
            element_ord = ord_map[element]
            for iv in ds:
                raw.append(
                    _RawEvent(iv.lo, TransitionKind.OPEN, element, element_ord)
                )
                if int_max_sentinel is not None and iv.hi == int_max_sentinel:
                    close_coord: int | None = None
                else:
                    close_coord = iv.hi + 1
                raw.append(
                    _RawEvent(close_coord, TransitionKind.CLOSE, element, element_ord)
                )

        # Sort: coord ascending (None > finite); same-coord opens before
        # closes; same-coord-and-kind opens by ord asc, closes by ord desc.
        def sort_key(ev: _RawEvent) -> tuple:
            # First component: (1, 0) for None (treat as greater than any
            # finite); (0, coord) for finite. Tuple comparison handles it.
            if ev.coordinate is None:
                coord_key: tuple = (1, 0)
            else:
                coord_key = (0, ev.coordinate)
            kind_key = 0 if ev.kind == TransitionKind.OPEN else 1
            ord_tiebreak = ev.ord if ev.kind == TransitionKind.OPEN else -ev.ord
            return (coord_key, kind_key, ord_tiebreak)

        raw.sort(key=sort_key)

        public_events = tuple(
            TransitionEvent(ev.coordinate, ev.kind, ev.element) for ev in raw
        )
        segments = cls._materialise_segments(raw)
        return cls(public_events, segments, snapshot_version, tuple(raw))

    @staticmethod
    def _materialise_segments(events: list[_RawEvent]) -> tuple[Segment, ...]:
        """Sweep events linearly, materialising a Segment for every maximal
        run of integers over which the active set is constant. Per RFC §6.3
        we do not emit a segment whose active set is empty.
        """
        segments: list[Segment] = []
        active_by_ord: dict[int, object] = {}
        prev_coord: int | None = None
        i = 0
        n = len(events)
        while i < n:
            coord = events[i].coordinate

            # Emit segment for [prev_coord, coord-1] before processing
            # events at this coord, if the active set is non-empty.
            if prev_coord is not None and active_by_ord and coord is not None:
                seg_hi = coord - 1
                snapshot = tuple(
                    active_by_ord[o] for o in sorted(active_by_ord.keys())
                )
                segments.append(Segment(prev_coord, seg_hi, snapshot))

            # Apply every event at this coord.
            while i < n and events[i].coordinate == coord:
                ev_i = events[i]
                if ev_i.kind == TransitionKind.OPEN:
                    active_by_ord[ev_i.ord] = ev_i.element
                else:
                    active_by_ord.pop(ev_i.ord, None)
                i += 1

            prev_coord = coord

        return tuple(segments)
