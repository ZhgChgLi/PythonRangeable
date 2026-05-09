"""RFC §10 — 23 normative contract tests.

Mirrors `RubyRangeable/test/rangeable_test.rb` and the Swift
`RangeableContractTests`. Test #20 (random property) is in
`test_property.py`. Test #23.A (Int.max sentinel) is partially exercised
via direct ``BoundaryIndex.build(int_max_sentinel=...)`` because Python
ints are unbounded and the public ``Rangeable`` does not opt in.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rangeable import (
    InvalidIntervalError,
    Rangeable,
    TransitionKind,
)
from rangeable._boundary_index import BoundaryIndex
from rangeable._disjoint_set import DisjointSet


@dataclass(frozen=True, slots=True)
class Strong:
    pass


@dataclass(frozen=True, slots=True)
class Italic:
    pass


@dataclass(frozen=True, slots=True)
class Code:
    pass


@dataclass(frozen=True, slots=True)
class Link:
    url: str


# ------------------------------------------------------------------------- #
# Test #1 — Empty container
# ------------------------------------------------------------------------- #
def test_01_empty():
    r: Rangeable = Rangeable()
    assert r[0].objs == ()
    assert r.get_range(Strong()) == []
    assert len(r) == 0
    assert r.empty
    assert not bool(r)


# ------------------------------------------------------------------------- #
# Test #2 — Single insert
# ------------------------------------------------------------------------- #
def test_02_single_insert():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    assert r[2].objs == (Strong(),)
    assert r[5].objs == (Strong(),)
    assert r[6].objs == ()
    assert r[1].objs == ()


# ------------------------------------------------------------------------- #
# Test #3 — Inclusive end
# ------------------------------------------------------------------------- #
def test_03_inclusive_end():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=3, end=8)
    assert r[8].objs == (Strong(),)
    assert r[9].objs == ()


# ------------------------------------------------------------------------- #
# Test #4 — Single-point
# ------------------------------------------------------------------------- #
def test_04_single_point():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=4, end=4)
    assert r[3].objs == ()
    assert r[4].objs == (Strong(),)
    assert r[5].objs == ()


# ------------------------------------------------------------------------- #
# Test #5 — Same-element overlap merge
# ------------------------------------------------------------------------- #
def test_05_same_element_overlap_merge():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    r.insert(Strong(), start=3, end=7)
    assert r.get_range(Strong()) == [(2, 7)]


# ------------------------------------------------------------------------- #
# Test #6 — Same-element adjacency merge
# ------------------------------------------------------------------------- #
def test_06_same_element_adjacency_merge():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=4)
    r.insert(Strong(), start=5, end=7)
    assert r.get_range(Strong()) == [(2, 7)]


# ------------------------------------------------------------------------- #
# Test #7 — Same-element non-adjacent disjoint
# ------------------------------------------------------------------------- #
def test_07_same_element_non_adjacent_disjoint():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=4)
    r.insert(Strong(), start=6, end=7)
    assert r.get_range(Strong()) == [(2, 4), (6, 7)]


# ------------------------------------------------------------------------- #
# Test #8 — Same-element nested
# ------------------------------------------------------------------------- #
def test_08_same_element_nested():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=10)
    r.insert(Strong(), start=4, end=6)
    assert r.get_range(Strong()) == [(2, 10)]


# ------------------------------------------------------------------------- #
# Test #9 — Idempotent insert
# ------------------------------------------------------------------------- #
def test_09_idempotent_insert():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    v1 = r.version
    r.insert(Strong(), start=2, end=5)
    v2 = r.version
    assert r.get_range(Strong()) == [(2, 5)]
    assert v1 == v2


# ------------------------------------------------------------------------- #
# Test #10 — Different elements coexist
# ------------------------------------------------------------------------- #
def test_10_different_elements_coexist():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    r.insert(Italic(), start=3, end=7)
    assert r[3].objs == (Strong(), Italic())
    assert r[6].objs == (Italic(),)
    assert r.get_range(Strong()) == [(2, 5)]
    assert r.get_range(Italic()) == [(3, 7)]


# ------------------------------------------------------------------------- #
# Test #11 — Equal-by-equality elements merge
# ------------------------------------------------------------------------- #
def test_11_equal_by_equality_merge():
    r: Rangeable = Rangeable()
    r.insert(Link("a"), start=2, end=5)
    r.insert(Link("a"), start=4, end=8)
    r.insert(Link("b"), start=6, end=9)
    assert r.get_range(Link("a")) == [(2, 8)]
    assert r.get_range(Link("b")) == [(6, 9)]


# ------------------------------------------------------------------------- #
# Test #12 — First-insert order at point
# ------------------------------------------------------------------------- #
def test_12_first_insert_order_at_point():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=1, end=10)
    r.insert(Italic(), start=1, end=10)
    r.insert(Code(), start=1, end=10)
    assert r[5].objs == (Strong(), Italic(), Code())


# ------------------------------------------------------------------------- #
# Test #13 — Order preserved through merge
# ------------------------------------------------------------------------- #
def test_13_order_preserved_through_merge():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=1, end=5)
    r.insert(Italic(), start=3, end=7)
    r.insert(Strong(), start=4, end=8)
    assert r[6].objs == (Strong(), Italic())


# ------------------------------------------------------------------------- #
# Test #14 — Transitions over a range
# ------------------------------------------------------------------------- #
def test_14_transitions_over_range():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    r.insert(Italic(), start=3, end=7)
    events = r.transitions(lo=0, hi=10)
    assert [(e.coordinate, e.kind, e.element) for e in events] == [
        (2, TransitionKind.OPEN, Strong()),
        (3, TransitionKind.OPEN, Italic()),
        (6, TransitionKind.CLOSE, Strong()),
        (8, TransitionKind.CLOSE, Italic()),
    ]


# ------------------------------------------------------------------------- #
# Test #15 — Transitions same-start
# ------------------------------------------------------------------------- #
def test_15_transitions_same_start():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=3, end=5)
    r.insert(Italic(), start=3, end=7)
    events = r.transitions(lo=0, hi=10)
    assert [(e.coordinate, e.kind, e.element) for e in events] == [
        (3, TransitionKind.OPEN, Strong()),
        (3, TransitionKind.OPEN, Italic()),
        (6, TransitionKind.CLOSE, Strong()),
        (8, TransitionKind.CLOSE, Italic()),
    ]


# ------------------------------------------------------------------------- #
# Test #16 — Transitions same-end (LIFO close order)
# ------------------------------------------------------------------------- #
def test_16_transitions_same_end_lifo():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=3, end=5)
    r.insert(Italic(), start=3, end=5)
    events = r.transitions(lo=0, hi=10)
    assert [(e.coordinate, e.kind, e.element) for e in events] == [
        (3, TransitionKind.OPEN, Strong()),
        (3, TransitionKind.OPEN, Italic()),
        (6, TransitionKind.CLOSE, Italic()),
        (6, TransitionKind.CLOSE, Strong()),
    ]


# ------------------------------------------------------------------------- #
# Test #17 — start > end raises
# ------------------------------------------------------------------------- #
def test_17_start_greater_than_end_raises():
    r: Rangeable = Rangeable()
    with pytest.raises(InvalidIntervalError):
        r.insert(Strong(), start=5, end=2)
    assert r.empty
    assert len(r) == 0


# ------------------------------------------------------------------------- #
# Test #18 — Negative start
# ------------------------------------------------------------------------- #
def test_18_negative_start():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=-2, end=3)
    assert r[-1].objs == (Strong(),)
    assert r[0].objs == (Strong(),)
    assert r[3].objs == (Strong(),)
    assert r[4].objs == ()


# ------------------------------------------------------------------------- #
# Test #19 — Insert/read interleave (rebuild correctness)
# ------------------------------------------------------------------------- #
def test_19_insert_read_interleave_rebuild():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=1, end=3)
    read1 = r[2].objs              # triggers lazy build
    r.insert(Strong(), start=5, end=7)  # must invalidate event index
    read2 = r[6].objs              # must rebuild
    assert read1 == (Strong(),)
    assert read2 == (Strong(),)
    assert r.get_range(Strong()) == [(1, 3), (5, 7)]


# ------------------------------------------------------------------------- #
# Test #21 — Idempotent insert MUST NOT bump version
# ------------------------------------------------------------------------- #
def test_21_idempotent_insert_no_version_bump():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    v1 = r.version
    r.insert(Strong(), start=2, end=5)
    v2 = r.version
    assert v1 == v2


# ------------------------------------------------------------------------- #
# Test #21.A — Idempotent insert with strict containment
# ------------------------------------------------------------------------- #
def test_21A_idempotent_strict_containment():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=10)
    v1 = r.version
    r.insert(Strong(), start=4, end=6)
    v2 = r.version
    assert r.get_range(Strong()) == [(2, 10)]
    assert v1 == v2


# ------------------------------------------------------------------------- #
# Test #22 — transitions with lo > hi raises
# ------------------------------------------------------------------------- #
def test_22_transitions_lo_greater_than_hi_raises():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    with pytest.raises(InvalidIntervalError):
        r.transitions(lo=5, hi=2)


# ------------------------------------------------------------------------- #
# Test #23 — Very negative lo (Python int has no Int.min, simulate)
# ------------------------------------------------------------------------- #
def test_23_int_min_simulator_as_lo():
    int_min = -(2**63)
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=int_min, end=int_min + 5)
    assert r[int_min].objs == (Strong(),)
    assert r[int_min + 5].objs == (Strong(),)
    assert r[int_min + 6].objs == ()
    assert r.get_range(Strong()) == [(int_min, int_min + 5)]


# ------------------------------------------------------------------------- #
# Test #23.A — Int.max sentinel via direct BoundaryIndex API.
# Python ints are unbounded; the public Rangeable does not opt in to a
# sentinel by default. Exercise via the explicit kwarg so the +∞ close
# coord is produced and total-order rules hold.
# ------------------------------------------------------------------------- #
def test_23A_int_max_sentinel_close_coord_is_none():
    int_max = (2**63) - 1
    intervals: dict = {Strong(): DisjointSet()}
    intervals[Strong()].insert(100, int_max)
    ord_map = {Strong(): 1}
    idx = BoundaryIndex.build(
        intervals, ord_map, snapshot_version=1, int_max_sentinel=int_max
    )
    coords_kinds = [(ev.coordinate, ev.kind) for ev in idx.events]
    assert coords_kinds == [
        (100, TransitionKind.OPEN),
        (None, TransitionKind.CLOSE),
    ]


# ------------------------------------------------------------------------- #
# Additional coverage: count / empty / iteration / copy independence
# ------------------------------------------------------------------------- #
def test_count_and_empty_track_distinct_elements():
    r: Rangeable = Rangeable()
    assert len(r) == 0
    assert r.empty
    r.insert(Strong(), start=1, end=2)
    assert len(r) == 1
    assert not r.empty
    r.insert(Strong(), start=3, end=4)  # same equivalence class
    assert len(r) == 1
    r.insert(Italic(), start=1, end=2)
    assert len(r) == 2


def test_iter_yields_pairs_in_first_insert_order():
    r: Rangeable = Rangeable()
    r.insert(Italic(), start=3, end=4)
    r.insert(Strong(), start=1, end=2)
    pairs = list(r)
    assert pairs == [(Italic(), [(3, 4)]), (Strong(), [(1, 2)])]


def test_copy_is_deep_and_independent():
    r1: Rangeable = Rangeable()
    r1.insert(Strong(), start=1, end=5)
    r2 = r1.copy()
    r2.insert(Strong(), start=10, end=12)
    assert r1.get_range(Strong()) == [(1, 5)]
    assert r2.get_range(Strong()) == [(1, 5), (10, 12)]


def test_insert_returns_self_for_chaining():
    r: Rangeable = Rangeable()
    out = r.insert(Strong(), start=1, end=2).insert(Italic(), start=3, end=4)
    assert out is r


def test_transitions_open_top_means_plus_infinity():
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=2, end=5)
    events = r.transitions(lo=0, hi=None)
    assert len(events) == 2
    assert events[-1].coordinate == 6
    assert events[-1].kind == TransitionKind.CLOSE
