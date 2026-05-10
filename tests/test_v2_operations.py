"""RFC v2 §10.B–§10.G — Removal + Set-operation contract tests.

Covers tests #21–#80 from the RFC. Test ids in the function names use
the `bNN` / `cNN` / `dNN` / `eNN` / `fNN` / `gNN` prefix that mirrors the
RFC subsection (§10.B / §10.C / …) to disambiguate from v1's §10.A
#21–#28 (already exercised in ``test_contract.py``).

Naming convention (mirrors ``test_contract.py``):

* ``Strong`` / ``Italic`` / ``Code`` / ``Link`` are frozen dataclasses
  used as ``Hashable`` element instances. Two instances of the same
  zero-field class are ``==`` (dataclass equality), so they share an
  ``ord`` row in the same way the Ruby fixture does.
* Tests assert on (a) ``r.get_range`` outputs, (b) ``insertion_order``
  via ``[e for e, _ in r]``, (c) ``r.version`` deltas to verify the
  no-bump-on-no-op rule, and (d) ``pytest.raises(InvalidIntervalError)``
  for pre-condition violations.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rangeable import InvalidIntervalError, Rangeable


# ------------------------------------------------------------------------- #
# Element fixtures (hashable, frozen — match Ruby/Swift counterpart shape)
# ------------------------------------------------------------------------- #


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
    name: str


def _insertion_order(r: Rangeable) -> list:
    return [e for e, _ in r]


def _build(*ops):
    """Convenience: build a fresh Rangeable and apply ``ops``.

    Each ``op`` is a tuple ``(element, start, end)`` interpreted as
    ``insert``.
    """
    r: Rangeable = Rangeable()
    for element, start, end in ops:
        r.insert(element, start=start, end=end)
    return r


# ========================================================================== #
# §10.B — Removal Tests (#21–#43)
# ========================================================================== #


# Test #21 — remove(e, start, end) no overlap (no-op, no version bump)
def test_b21_remove_no_overlap_no_bump():
    r = _build((Strong(), 10, 20))
    v0 = r.version
    r.remove(Strong(), start=0, end=5)
    assert r.get_range(Strong()) == [(10, 20)]
    assert r.version == v0
    assert r.count == 1


# Test #22 — exact match consumes one entry (eager prune)
def test_b22_remove_exact_match_prunes():
    r = _build((Strong(), 10, 20))
    r.remove(Strong(), start=10, end=20)
    assert r.count == 0
    assert r.empty
    assert _insertion_order(r) == []


# Test #23 — leaves left residual only
def test_b23_remove_left_residual_only():
    r = _build((Strong(), 0, 10))
    r.remove(Strong(), start=5, end=100)
    assert r.get_range(Strong()) == [(0, 4)]


# Test #24 — leaves right residual only
def test_b24_remove_right_residual_only():
    r = _build((Strong(), 0, 10))
    r.remove(Strong(), start=-100, end=5)
    assert r.get_range(Strong()) == [(6, 10)]


# Test #25 — splits one entry into two
def test_b25_remove_split_one_entry():
    r = _build((Strong(), 0, 10))
    r.remove(Strong(), start=3, end=6)
    assert r.get_range(Strong()) == [(0, 2), (7, 10)]


# Test #26 — spans multiple entries
def test_b26_remove_spans_multiple_entries():
    r = _build((Strong(), 0, 5), (Strong(), 10, 15), (Strong(), 20, 25))
    r.remove(Strong(), start=3, end=22)
    assert r.get_range(Strong()) == [(0, 2), (23, 25)]


# Test #27 — spans entire R(e), prunes element + renumbers ord
def test_b27_remove_spans_entire_re_prunes_element():
    r = _build((Strong(), 0, 5), (Strong(), 10, 15), (Italic(), 7, 8))
    v0 = r.version
    r.remove(Strong(), start=-100, end=100)
    assert r.count == 1
    assert _insertion_order(r) == [Italic()]
    assert r.version == v0 + 1


# Test #28 — no-op MUST NOT bump version (two flavours)
def test_b28_remove_noop_no_version_bump_two_flavours():
    r = _build((Strong(), 10, 20))
    v0 = r.version
    r.remove(Strong(), start=30, end=40)  # no overlap
    v1 = r.version
    r.remove(Italic(), start=0, end=5)  # element not present
    v2 = r.version
    assert v0 == v1 == v2


# Test #29 — start > end raises
def test_b29_remove_start_greater_than_end_raises():
    r = _build((Strong(), 0, 10))
    with pytest.raises(InvalidIntervalError):
        r.remove(Strong(), start=7, end=3)
    # State unchanged.
    assert r.get_range(Strong()) == [(0, 10)]


# Test #30 — start == Int.min underflow safe
def test_b30_remove_int_min_safe():
    int_min = -(2**63)
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=int_min, end=int_min + 100)
    r.remove(Strong(), start=int_min, end=int_min + 50)
    assert r.get_range(Strong()) == [(int_min + 51, int_min + 100)]


# Test #31 — end == Int.max overflow safe
def test_b31_remove_int_max_safe():
    int_max = (2**63) - 1
    r: Rangeable = Rangeable()
    r.insert(Strong(), start=0, end=int_max)
    r.remove(Strong(), start=1000, end=int_max)
    assert r.get_range(Strong()) == [(0, 999)]


# Test #32 — remove_element excises and renumbers ord
def test_b32_remove_element_excises_and_renumbers():
    r = _build((Strong(), 0, 5), (Italic(), 7, 12), (Code(), 15, 20))
    v0 = r.version
    r.remove_element(Italic())
    assert r.count == 2
    assert _insertion_order(r) == [Strong(), Code()]
    # ord renumbered: Strong=1, Code=2 (was 3).
    assert r._ord[Strong()] == 1
    assert r._ord[Code()] == 2
    assert r.version == v0 + 1


# Test #33 — remove_element on never-inserted element no-op
def test_b33_remove_element_never_inserted_no_bump():
    r = _build((Strong(), 0, 5))
    v0 = r.version
    r.remove_element(Italic())
    assert r.count == 1
    assert r.version == v0


# Test #34 — remove_element on single-interval element
def test_b34_remove_element_single_interval():
    r = _build((Strong(), 5, 10))
    r.remove_element(Strong())
    assert r.empty
    assert r.count == 0


# Test #35 — remove_element on element with many intervals
def test_b35_remove_element_many_intervals():
    r = _build((Strong(), 0, 5), (Strong(), 10, 15), (Strong(), 20, 25))
    r.remove_element(Strong())
    assert r.empty
    assert r.get_range(Strong()) == []


# Test #35.A — del r[e] sugar parity with remove_element
def test_b35a_delitem_sugar_matches_remove_element():
    r = _build((Strong(), 0, 5), (Italic(), 10, 12))
    v0 = r.version
    del r[Italic()]
    assert _insertion_order(r) == [Strong()]
    assert r.version == v0 + 1


# Test #35.B — del r[e] no-op when e absent
def test_b35b_delitem_noop_when_absent():
    r = _build((Strong(), 0, 5))
    v0 = r.version
    del r[Italic()]
    assert r.version == v0


# Test #36 — clear non-empty
def test_b36_clear_non_empty():
    r = _build((Strong(), 0, 5), (Italic(), 7, 12))
    v0 = r.version
    r.clear()
    assert r.empty
    assert r.count == 0
    assert r.get_range(Strong()) == []
    assert r.get_range(Italic()) == []
    assert r.version == v0 + 1


# Test #37 — clear empty no version bump
def test_b37_clear_empty_no_bump():
    r: Rangeable = Rangeable()
    v0 = r.version
    r.clear()
    assert r.empty
    assert r.version == v0


# Test #38 — post-clear isEmpty/transitions stay consistent
def test_b38_post_clear_subscript_and_transitions():
    r = _build((Strong(), 0, 5))
    r.clear()
    assert r.empty
    assert r[3].objs == ()
    assert r.transitions(lo=0, hi=10) == []


# Test #39 — post-clear iter yields nothing
def test_b39_post_clear_iter_yields_nothing():
    r = _build((Strong(), 0, 5), (Italic(), 7, 12))
    r.clear()
    assert r.count == 0
    assert list(r) == []


# Test #40 — insert after clear assigns ord = 1
def test_b40_insert_after_clear_assigns_ord_one():
    r = _build((Strong(), 0, 5), (Italic(), 7, 12))
    r.clear()
    r.insert(Code(), start=100, end=110)
    assert r.count == 1
    assert r._ord[Code()] == 1


# Test #41 — remove_ranges hits multiple elements (single bump)
def test_b41_remove_ranges_multi_element_single_bump():
    r = _build(
        (Strong(), 0, 10),
        (Italic(), 5, 15),
        (Code(), 100, 110),
    )
    v0 = r.version
    r.remove_ranges(start=3, end=8)
    assert r.get_range(Strong()) == [(0, 2), (9, 10)]
    assert r.get_range(Italic()) == [(9, 15)]
    assert r.get_range(Code()) == [(100, 110)]
    # Single atomic bump (NOT three).
    assert r.version == v0 + 1


# Test #42 — remove_ranges no overlap MUST NOT bump
def test_b42_remove_ranges_no_overlap_no_bump():
    r = _build((Strong(), 0, 10), (Italic(), 50, 60))
    v0 = r.version
    r.remove_ranges(start=20, end=30)
    assert r.get_range(Strong()) == [(0, 10)]
    assert r.get_range(Italic()) == [(50, 60)]
    assert r.version == v0


# Test #43 — remove_ranges fully covers everything
def test_b43_remove_ranges_full_cover_prunes_all():
    r = _build((Strong(), 0, 5), (Italic(), 10, 20), (Code(), 25, 30))
    v0 = r.version
    r.remove_ranges(start=0, end=30)
    assert r.empty
    assert r.count == 0
    assert r.version == v0 + 1


# Test #43.B — variant: mixed prune + retain with renumbered ord
def test_b43b_remove_ranges_mixed_prune_retain():
    r = _build((Strong(), 0, 5), (Italic(), 10, 20), (Code(), 25, 30))
    v0 = r.version
    r.remove_ranges(start=8, end=22)
    assert r.get_range(Strong()) == [(0, 5)]
    assert r.get_range(Italic()) == []  # fully pruned
    assert r.get_range(Code()) == [(25, 30)]
    assert r.count == 2
    assert _insertion_order(r) == [Strong(), Code()]
    assert r._ord[Strong()] == 1
    assert r._ord[Code()] == 2  # renumbered from 3
    assert r.version == v0 + 1


# Test #43.C — remove_ranges start > end raises pre-mutation
def test_b43c_remove_ranges_start_greater_than_end_raises():
    r = _build((Strong(), 0, 10))
    v0 = r.version
    with pytest.raises(InvalidIntervalError):
        r.remove_ranges(start=10, end=5)
    assert r.get_range(Strong()) == [(0, 10)]
    assert r.version == v0


# Test #43.D — remove returns self for chaining
def test_b43d_remove_methods_return_self_for_chaining():
    r = _build((Strong(), 0, 10), (Italic(), 20, 30))
    assert r.remove(Strong(), start=0, end=4) is r
    assert r.remove_element(Italic()) is r
    assert r.remove_ranges(start=0, end=100) is r
    assert r.clear() is r


# ========================================================================== #
# §10.C — Union Tests (#44–#50)
# ========================================================================== #


# Test #44 — disjoint elements
def test_c44_union_disjoint_elements():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Italic(), 10, 15))
    v1, v2 = r1.version, r2.version
    r3 = r1.union(r2)
    assert r3.count == 2
    assert _insertion_order(r3) == [Strong(), Italic()]
    assert r3.get_range(Strong()) == [(0, 5)]
    assert r3.get_range(Italic()) == [(10, 15)]
    assert r3.version == 0
    # Sources unchanged.
    assert r1.version == v1
    assert r2.version == v2


# Test #45 — same element, overlapping intervals merge
def test_c45_union_overlapping_intervals():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 15))
    r3 = r1.union(r2)
    assert r3.get_range(Strong()) == [(0, 15)]
    assert r3.count == 1


# Test #46 — adjacency-merge (5+1 == 6)
def test_c46_union_integer_adjacency_collapse():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Strong(), 6, 10))
    r3 = r1.union(r2)
    assert r3.get_range(Strong()) == [(0, 10)]


# Test #47 — mutating form (update) on idempotent subset MUST NOT bump
def test_c47_update_idempotent_subset_no_version_bump():
    r1 = _build((Strong(), 0, 10), (Italic(), 20, 30))
    r2 = _build((Strong(), 3, 7))  # R_r2(Strong) ⊆ R_r1(Strong)
    v0 = r1.version
    r1.update(r2)
    assert r1.get_range(Strong()) == [(0, 10)]
    assert r1.get_range(Italic()) == [(20, 30)]
    assert r1.version == v0


# Test #48 — union of two empties = empty
def test_c48_union_two_empties():
    r1: Rangeable = Rangeable()
    r2: Rangeable = Rangeable()
    r3 = r1.union(r2)
    assert r3.empty
    assert r3.count == 0
    assert r3.version == 0


# Test #49 — union with self (non-mutating)
def test_c49_union_with_self_non_mutating():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    v0 = r1.version
    r2 = r1.union(r1)
    assert _insertion_order(r2) == _insertion_order(r1)
    assert r2.get_range(Strong()) == r1.get_range(Strong())
    assert r2.get_range(Italic()) == r1.get_range(Italic())
    assert r2.version == 0
    assert r1.version == v0


# Test #49b — mutating form on self idempotent
def test_c49b_update_with_self_no_version_bump():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    v0 = r1.version
    r1.update(r1)
    assert r1.version == v0
    assert _insertion_order(r1) == [Strong(), Italic()]


# Test #50 — insertion-order tail-append
def test_c50_union_insertion_order_tail_append():
    A, B, C, D = Link("A"), Link("B"), Link("C"), Link("D")
    r1 = _build((A, 0, 1), (B, 2, 3))
    r2 = _build((C, 4, 5), (B, 10, 11), (D, 12, 13))
    r3 = r1.union(r2)
    assert _insertion_order(r3) == [A, B, C, D]
    assert r3._ord[A] == 1
    assert r3._ord[B] == 2
    assert r3._ord[C] == 3
    assert r3._ord[D] == 4


# Test #50b — operator | mirrors union
def test_c50b_or_operator_matches_union():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Italic(), 10, 15))
    r_op = r1 | r2
    r_method = r1.union(r2)
    assert _insertion_order(r_op) == _insertion_order(r_method)
    assert r_op.get_range(Strong()) == r_method.get_range(Strong())


# Test #50c — |= mirrors update and bumps version once
def test_c50c_ior_operator_matches_update_and_bumps():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Italic(), 10, 15))
    v0 = r1.version
    r1 |= r2
    assert _insertion_order(r1) == [Strong(), Italic()]
    assert r1.version == v0 + 1


# ========================================================================== #
# §10.D — Intersect Tests (#51–#57)
# ========================================================================== #


# Test #51 — no shared elements
def test_d51_intersect_no_shared_elements():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Italic(), 5, 15))
    r3 = r1.intersection(r2)
    assert r3.empty
    assert r3.count == 0


# Test #52 — shared elements, overlapping intervals
def test_d52_intersect_shared_overlapping_intervals():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 15))
    r3 = r1.intersection(r2)
    assert r3.get_range(Strong()) == [(5, 10)]
    assert r3.count == 1


# Test #53 — shared elements, disjoint intervals → eager prune
def test_d53_intersect_shared_disjoint_eager_prune():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Strong(), 100, 200))
    r3 = r1.intersection(r2)
    assert r3.empty
    assert _insertion_order(r3) == []


# Test #54 — intersect with self
def test_d54_intersect_with_self():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    v0 = r1.version
    r2 = r1.intersection(r1)
    assert _insertion_order(r2) == _insertion_order(r1)
    assert r2.get_range(Strong()) == [(0, 5)]
    assert r2.get_range(Italic()) == [(10, 15)]
    assert r2.version == 0
    assert r1.version == v0


# Test #55 — intersect with empty
def test_d55_intersect_with_empty():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    r2: Rangeable = Rangeable()
    r3 = r1.intersection(r2)
    assert r3.empty


# Test #56 — produces multiple sub-intervals per element
def test_d56_intersect_multiple_sub_intervals():
    r1 = _build(
        (Strong(), 0, 5),
        (Strong(), 10, 15),
        (Strong(), 20, 25),
    )
    r2 = _build((Strong(), 3, 22))
    r3 = r1.intersection(r2)
    assert r3.get_range(Strong()) == [(3, 5), (10, 15), (20, 22)]


# Test #57 — insertion-order preservation + dense ord renumber
def test_d57_intersect_insertion_order_preservation_dense_ord():
    A, B, C, D, E = Link("A"), Link("B"), Link("C"), Link("D"), Link("E")
    r1 = _build((A, 0, 5), (B, 10, 15), (C, 20, 25), (D, 30, 35))
    r2 = _build((A, 0, 5), (C, 21, 24), (E, 100, 200))
    r3 = r1.intersection(r2)
    assert _insertion_order(r3) == [A, C]
    assert r3._ord[A] == 1
    assert r3._ord[C] == 2  # densely renumbered, NOT 3
    assert r3.get_range(A) == [(0, 5)]
    assert r3.get_range(C) == [(21, 24)]


# Test #57b — operator & mirrors intersection
def test_d57b_and_operator_matches_intersection():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 15))
    assert (r1 & r2).get_range(Strong()) == [(5, 10)]


# Test #57c — &= update is idempotent on self
def test_d57c_iand_with_self_no_version_bump():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    v0 = r1.version
    r1 &= r1
    assert r1.version == v0
    assert _insertion_order(r1) == [Strong(), Italic()]


# ========================================================================== #
# §10.E — Difference Tests (#58–#65)
# ========================================================================== #


# Test #58 — disjoint elements (returns self structurally)
def test_e58_difference_disjoint_elements_self_structural():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Italic(), 5, 15))
    r3 = r1.difference(r2)
    assert _insertion_order(r3) == _insertion_order(r1)
    assert r3.get_range(Strong()) == [(0, 10)]
    assert r3.version == 0


# Test #59 — difference with self = empty
def test_e59_difference_with_self_is_empty():
    r1 = _build((Strong(), 0, 10), (Italic(), 20, 30))
    r2 = r1.difference(r1)
    assert r2.empty
    assert r2.count == 0


# Test #60 — left residuals
def test_e60_difference_left_residuals():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 100))
    r3 = r1.difference(r2)
    assert r3.get_range(Strong()) == [(0, 4)]


# Test #61 — right residuals
def test_e61_difference_right_residuals():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), -100, 5))
    r3 = r1.difference(r2)
    assert r3.get_range(Strong()) == [(6, 10)]


# Test #62 — both residuals (split)
def test_e62_difference_split_both_residuals():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 3, 6))
    r3 = r1.difference(r2)
    assert r3.get_range(Strong()) == [(0, 2), (7, 10)]


# Test #63 — spans multiple L_a entries
def test_e63_difference_spans_multiple_entries():
    r1 = _build(
        (Strong(), 0, 5),
        (Strong(), 10, 15),
        (Strong(), 20, 25),
    )
    r2 = _build((Strong(), 3, 22))
    r3 = r1.difference(r2)
    assert r3.get_range(Strong()) == [(0, 2), (23, 25)]


# Test #64 — insertion-order preservation; pruned key dropped
def test_e64_difference_insertion_order_preservation():
    A, B, C, D, E = Link("A"), Link("B"), Link("C"), Link("D"), Link("E")
    r1 = _build((A, 0, 5), (B, 10, 15), (C, 20, 25), (D, 30, 35))
    r2 = _build((B, 9, 16), (E, 100, 200))
    r3 = r1.difference(r2)
    assert _insertion_order(r3) == [A, C, D]  # B fully consumed; E ignored
    assert r3._ord[A] == 1
    assert r3._ord[C] == 2
    assert r3._ord[D] == 3


# Test #65 — difference ≡ removeRanges-loop equivalence (structural)
#
# Deviation from RFC §10.E #65 wording: the RFC's worked example
# (`r1.Strong=(0,10), r1.Italic=(5,15); r2.Strong=(3,6), r2.Italic=(12,18)`)
# claims structural equivalence between
#   r3 = r1.difference(r2)
# and
#   r4 = r1.copy(); for (lo,hi) in flatten(r2): r4.remove_ranges(lo,hi)
# but `remove_ranges` is element-cross-cutting (it removes from EVERY
# element), so `remove_ranges(12, 18)` shrinks `r4.Italic = (7, 15)` to
# `(7, 11)` whereas `r1.difference(r2)` only cuts Italic by `r2.Italic`,
# yielding `(5, 11)`. The two are equal only when each interval in
# `flatten(r2)` overlaps exactly the elements that `r2` had it for.
#
# The RFC §6.12 "informative equivalence" note really means a per-element
# reduction; we test the strict per-element-scoped equivalence here (the
# only one that actually holds), plus the Strong-half of the RFC's example
# (which does match because r2.Strong's range happens not to touch
# r1.Italic's support).
def test_e65_difference_equivalent_to_remove_ranges_per_element():
    # Per-element-scoped reduction: only one element in r2.
    r1 = _build((Strong(), 0, 10), (Italic(), 5, 15))
    r2 = _build((Strong(), 3, 6))
    r3 = r1.difference(r2)
    r4 = r1.copy()
    # Apply r2's intervals only against r1's matching key. (Single-element
    # r2 means the cross-cutting hazard is avoided.)
    for lo, hi in r2.get_range(Strong()):
        r4.remove(Strong(), start=lo, end=hi)
    assert _insertion_order(r3) == _insertion_order(r4)
    assert r3.get_range(Strong()) == r4.get_range(Strong())
    assert r3.get_range(Italic()) == r4.get_range(Italic())


def test_e65b_difference_equivalent_for_strong_half_of_rfc_example():
    # RFC §10.E #65 worked example, restricted to its Strong half (which
    # genuinely does match across the difference vs. remove_ranges-loop
    # equivalence — because r2.Strong's range (3, 6) does not touch
    # r1.Italic's support (5, 15) and neither does r2.Italic's (12, 18)
    # touch r1.Strong's (0, 10)). The Italic half is documented as a
    # cross-element-cutting asymmetry; see test_e65_*.
    r1 = _build((Strong(), 0, 10), (Italic(), 5, 15))
    r2 = _build((Strong(), 3, 6), (Italic(), 12, 18))
    r3 = r1.difference(r2)
    # r3 is per-element scoped: Strong is cut by r2.Strong, Italic by
    # r2.Italic.
    assert r3.get_range(Strong()) == [(0, 2), (7, 10)]
    assert r3.get_range(Italic()) == [(5, 11)]


# Test #65b — operator - mirrors difference
def test_e65b_sub_operator_matches_difference():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 3, 6))
    assert (r1 - r2).get_range(Strong()) == [(0, 2), (7, 10)]


# Test #65c — -= mutates self and bumps version once
def test_e65c_isub_operator_bumps_once():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 3, 6))
    v0 = r1.version
    r1 -= r2
    assert r1.get_range(Strong()) == [(0, 2), (7, 10)]
    assert r1.version == v0 + 1


# Test #65d — difference_update on disjoint other = no bump (idempotent)
def test_e65d_difference_update_disjoint_no_bump():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Italic(), 5, 15))
    v0 = r1.version
    r1.difference_update(r2)
    assert r1.version == v0
    assert r1.get_range(Strong()) == [(0, 10)]


# ========================================================================== #
# §10.F — Symmetric Difference Tests (#66–#71)
# ========================================================================== #


# Test #66 — sym-diff with empty = self structurally
def test_f66_symmetric_difference_with_empty_is_self():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    r2: Rangeable = Rangeable()
    r3 = r1.symmetric_difference(r2)
    assert _insertion_order(r3) == [Strong(), Italic()]
    assert r3.get_range(Strong()) == [(0, 5)]
    assert r3.get_range(Italic()) == [(10, 15)]
    assert r3.version == 0


# Test #67 — sym-diff with self = empty
def test_f67_symmetric_difference_with_self_is_empty():
    r1 = _build((Strong(), 0, 5), (Italic(), 10, 15))
    r2 = r1.symmetric_difference(r1)
    assert r2.empty
    assert r2.count == 0


# Test #68 — per-element residuals from both sides
def test_f68_symmetric_difference_residuals_both_sides():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 15))
    r3 = r1.symmetric_difference(r2)
    assert r3.get_range(Strong()) == [(0, 4), (11, 15)]


# Test #68b — adjacency case: [(0,5)] △ [(6,10)] == [(0,10)]
def test_f68b_symmetric_difference_adjacency_collapse():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Strong(), 6, 10))
    r3 = r1.symmetric_difference(r2)
    assert r3.get_range(Strong()) == [(0, 10)]


# Test #69 — commutativity of per-element R(e), modulo insertion_order
def test_f69_symmetric_difference_commutativity_modulo_order():
    A, B, C = Link("A"), Link("B"), Link("C")
    r1 = _build((A, 0, 5), (B, 10, 15))
    r2 = _build((B, 12, 17), (C, 20, 25))
    r3 = r1.symmetric_difference(r2)
    r4 = r2.symmetric_difference(r1)
    # Per-element R(e) commutes.
    for e in [A, B, C]:
        assert r3.get_range(e) == r4.get_range(e), e
    # Specifically the BY-DESIGN values from the RFC test.
    assert r3.get_range(A) == [(0, 5)]
    assert r3.get_range(B) == [(10, 11), (16, 17)]
    assert r3.get_range(C) == [(20, 25)]
    # Insertion order is self-primary (NOT commutative).
    assert _insertion_order(r3) == [A, B, C]
    assert _insertion_order(r4) == [B, C, A]


# Test #70 — associativity, RFC §10.F worked example
def test_f70_symmetric_difference_associativity():
    A = Link("A")
    r1 = _build((A, 0, 10))
    r2 = _build((A, 5, 15))
    r3 = _build((A, 10, 20))
    r_left = r1.symmetric_difference(r2).symmetric_difference(r3)
    r_right = r1.symmetric_difference(r2.symmetric_difference(r3))
    expected = [(0, 4), (10, 10), (16, 20)]
    assert r_left.get_range(A) == expected
    assert r_right.get_range(A) == expected
    assert _insertion_order(r_left) == [A]
    assert _insertion_order(r_right) == [A]
    assert r_left._ord[A] == 1
    assert r_right._ord[A] == 1


# Test #71 — insertion-order tail-append for keys ∈ other ∖ self
def test_f71_symmetric_difference_insertion_order_tail_append():
    A, B, C, D = Link("A"), Link("B"), Link("C"), Link("D")
    r1 = _build((A, 0, 5), (B, 10, 15))
    r2 = _build((C, 20, 25), (D, 30, 35))
    r3 = r1.symmetric_difference(r2)
    assert _insertion_order(r3) == [A, B, C, D]
    assert r3._ord[A] == 1
    assert r3._ord[B] == 2
    assert r3._ord[C] == 3
    assert r3._ord[D] == 4


# Test #71b — operator ^ mirrors symmetric_difference
def test_f71b_xor_operator_matches_symmetric_difference():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 15))
    assert (r1 ^ r2).get_range(Strong()) == [(0, 4), (11, 15)]


# Test #71c — ^= matches symmetric_difference_update
def test_f71c_ixor_operator_bumps_once():
    r1 = _build((Strong(), 0, 10))
    r2 = _build((Strong(), 5, 15))
    v0 = r1.version
    r1 ^= r2
    assert r1.get_range(Strong()) == [(0, 4), (11, 15)]
    assert r1.version == v0 + 1


# ========================================================================== #
# §10.G — Set-op Insertion-order Stress Tests (#72–#80)
# ========================================================================== #


# Test #72 — dense ord renumber after multi-element prune
def test_g72_dense_ord_renumber_after_multi_element_prune():
    A, B, C, D, E = Link("A"), Link("B"), Link("C"), Link("D"), Link("E")
    r1 = _build(
        (A, 0, 1), (B, 2, 3), (C, 4, 5), (D, 6, 7), (E, 8, 9)
    )
    r2 = _build((B, 100, 200), (D, 100, 200))
    r3 = r1.intersection(r2)
    # Both B and D intersect to empty against r1's ranges.
    assert r3.empty
    assert r3.count == 0


# Test #73 — union then intersect chain preserves insertion_order
def test_g73_union_then_intersect_chain_insertion_order():
    A, B, C = Link("A"), Link("B"), Link("C")
    r1 = _build((A, 0, 5), (B, 10, 15))
    r2 = _build((C, 20, 25), (B, 12, 17))
    r3 = _build((B, 0, 100), (C, 0, 100))
    union_result = r1.union(r2)
    assert _insertion_order(union_result) == [A, B, C]
    chain = union_result.intersection(r3)
    assert _insertion_order(chain) == [B, C]
    assert chain._ord[B] == 1
    assert chain._ord[C] == 2


# Test #74 — set-op result ord is correct even when input was pruned
def test_g74_set_op_result_ord_after_input_prune():
    A, B, C = Link("A"), Link("B"), Link("C")
    r1 = _build((A, 0, 5), (B, 10, 15), (C, 20, 25))
    r1.remove_element(B)
    # r1 now: insertion_order [A, C]; ord(C) == 2.
    r2: Rangeable = Rangeable()
    r3 = r1.union(r2)
    assert _insertion_order(r3) == [A, C]
    assert r3._ord[A] == 1
    assert r3._ord[C] == 2


# Test #75 — difference then union recovers insertion_order
def test_g75_difference_then_union_recovers_insertion_order():
    A, B, C = Link("A"), Link("B"), Link("C")
    r1 = _build((A, 0, 10), (B, 20, 30), (C, 40, 50))
    r2 = _build((B, 0, 100))  # fully consumes B
    r3 = r1.difference(r2).union(r1)
    # difference drops B; union with r1 re-introduces B at the tail.
    assert _insertion_order(r3) == [A, C, B]


# Test #76 — union of three with overlapping keys
def test_g76_union_of_three_overlapping_keys():
    A, B, C, D = Link("A"), Link("B"), Link("C"), Link("D")
    r1 = _build((A, 0, 5), (B, 10, 15))
    r2 = _build((B, 20, 25), (C, 30, 35))
    r3 = _build((C, 40, 45), (D, 50, 55))
    chain = r1.union(r2).union(r3)
    assert _insertion_order(chain) == [A, B, C, D]
    assert chain._ord[A] == 1
    assert chain._ord[B] == 2
    assert chain._ord[C] == 3
    assert chain._ord[D] == 4
    assert chain.get_range(A) == [(0, 5)]
    assert chain.get_range(B) == [(10, 15), (20, 25)]
    assert chain.get_range(C) == [(30, 35), (40, 45)]
    assert chain.get_range(D) == [(50, 55)]


# Test #77 — sym-diff equals (self ∪ other) ∖ (self ∩ other) per-element
def test_g77_symmetric_difference_two_algebraic_forms_equiv():
    A, B, C = Link("A"), Link("B"), Link("C")
    r1 = _build((A, 0, 10), (B, 20, 30))
    r2 = _build((A, 5, 15), (C, 40, 50))
    r_form1 = r1.symmetric_difference(r2)
    r_form2 = r1.union(r2).difference(r1.intersection(r2))
    # Per-element identity (insertion_order may differ — that's by design).
    keys = set([e for e, _ in r_form1] + [e for e, _ in r_form2])
    for e in keys:
        assert r_form1.get_range(e) == r_form2.get_range(e), e


# Test #78 — insert-after-remove ord reassignment (R14 deliberate side-effect)
def test_g78_insert_after_remove_ord_reassigned_at_tail():
    A, B = Link("A"), Link("B")
    r: Rangeable = Rangeable()
    r.insert(A, start=0, end=5)
    r.insert(B, start=10, end=15)
    # ord(A) == 1, ord(B) == 2.
    r.remove_element(A)
    # After excise: insertion_order == [B], ord(B) == 1.
    assert _insertion_order(r) == [B]
    assert r._ord[B] == 1
    r.insert(A, start=100, end=110)
    # A is now a NEW first-insert at the tail.
    assert _insertion_order(r) == [B, A]
    assert r._ord[B] == 1
    assert r._ord[A] == 2


# Test #79 — cross-op ord consistency (intersect after union)
def test_g79_intersect_after_union_ord_consistency():
    A, B, C, D = Link("A"), Link("B"), Link("C"), Link("D")
    r1 = _build((A, 0, 5), (B, 10, 15), (C, 20, 25))
    r2 = _build((B, 12, 17), (D, 30, 35))
    r_union = r1.union(r2)
    assert _insertion_order(r_union) == [A, B, C, D]
    r3 = _build((B, 0, 100), (D, 0, 100), (A, 0, 100))
    r_intersect = r_union.intersection(r3)
    # C dropped (not in keys(r3)). Insertion order from r_union is preserved.
    assert _insertion_order(r_intersect) == [A, B, D]
    assert r_intersect._ord[A] == 1
    assert r_intersect._ord[B] == 2
    assert r_intersect._ord[D] == 3


# Test #80 — empty result eager prune across set-op chain
def test_g80_empty_result_eager_prune_across_chain():
    A, B = Link("A"), Link("B")
    r1 = _build((A, 0, 5), (B, 10, 15))
    r2 = _build((A, 100, 200), (B, 100, 200))
    r3 = r1.intersection(r2)
    assert r3.empty
    r4 = r3.union(r1)
    assert _insertion_order(r4) == [A, B]
    assert r4._ord[A] == 1
    assert r4._ord[B] == 2


# ========================================================================== #
# Cross-cutting concerns: source isolation, operator parity, error precedence
# ========================================================================== #


# Test x1 — non-mutating set ops do not touch source versions
def test_x1_non_mutating_does_not_touch_source_version():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Italic(), 10, 15))
    v1, v2 = r1.version, r2.version
    _ = r1.union(r2)
    _ = r1.intersection(r2)
    _ = r1.difference(r2)
    _ = r1.symmetric_difference(r2)
    assert r1.version == v1
    assert r2.version == v2


# Test x2 — non-mutating set ops produce independent containers
def test_x2_non_mutating_returns_independent_container():
    r1 = _build((Strong(), 0, 5))
    r2 = _build((Italic(), 10, 15))
    r3 = r1.union(r2)
    r3.insert(Code(), start=100, end=110)
    # r1, r2 untouched.
    assert _insertion_order(r1) == [Strong()]
    assert _insertion_order(r2) == [Italic()]
    assert _insertion_order(r3) == [Strong(), Italic(), Code()]


# Test x3 — mutating set ops invalidate the event index
def test_x3_mutating_set_op_invalidates_event_index():
    r1 = _build((Strong(), 0, 10))
    _ = r1[5]  # builds event_index lazily
    assert r1._event_index is not None
    r2 = _build((Italic(), 20, 30))
    r1 |= r2
    # Updated container must invalidate the cached event_index.
    assert r1._event_index is None
    # Subsequent query rebuilds correctly.
    assert r1[25].objs == (Italic(),)


# Test x4 — remove invalidates event index and yields fresh subscript
def test_x4_remove_invalidates_event_index():
    r = _build((Strong(), 0, 10))
    _ = r[5]
    assert r._event_index is not None
    r.remove(Strong(), start=3, end=7)
    assert r._event_index is None
    # Post-removal subscript reflects the split.
    assert r[5].objs == ()
    assert r[2].objs == (Strong(),)
    assert r[8].objs == (Strong(),)


# Test x5 — non-mutating set ops between empty containers are safe
def test_x5_non_mutating_set_ops_between_empties():
    r1: Rangeable = Rangeable()
    r2: Rangeable = Rangeable()
    assert r1.union(r2).empty
    assert r1.intersection(r2).empty
    assert r1.difference(r2).empty
    assert r1.symmetric_difference(r2).empty


# Test x6 — operator precedence parity with method calls
def test_x6_operator_method_parity():
    r1 = _build((Strong(), 0, 10), (Italic(), 5, 15))
    r2 = _build((Strong(), 3, 6), (Code(), 20, 30))
    assert _insertion_order(r1 | r2) == _insertion_order(r1.union(r2))
    assert _insertion_order(r1 & r2) == _insertion_order(r1.intersection(r2))
    assert _insertion_order(r1 - r2) == _insertion_order(r1.difference(r2))
    assert _insertion_order(r1 ^ r2) == _insertion_order(
        r1.symmetric_difference(r2)
    )


# Test x7 — set-op chain on Link("a") equality-by-value works
def test_x7_link_value_equality_in_set_ops():
    r1 = _build((Link("a"), 0, 10))
    r2 = _build((Link("a"), 5, 15))
    r3 = r1.union(r2)
    assert r3.get_range(Link("a")) == [(0, 15)]


# Test x8 — remove_ranges idempotency on empty container
def test_x8_remove_ranges_on_empty_container_no_bump():
    r: Rangeable = Rangeable()
    v0 = r.version
    r.remove_ranges(start=0, end=10)
    assert r.version == v0
    assert r.empty
