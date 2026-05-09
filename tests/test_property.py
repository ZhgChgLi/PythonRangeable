"""RFC §10 Test #20 — random insert + brute-force oracle parity."""

from __future__ import annotations

import random
from dataclasses import dataclass

from rangeable import Rangeable


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


ELEMENTS = (
    Strong(),
    Italic(),
    Code(),
    Link("x"),
    Link("y"),
)
COORD_BOUND = 200
N_OPS = 1000
SEED = 42


def _build_first_seen(ops: list[tuple]) -> dict:
    first_seen: dict = {}
    for ord_idx, (e, _, _) in enumerate(ops):
        first_seen.setdefault(e, ord_idx)
    return first_seen


def _brute_force_active(ops: list[tuple], first_seen: dict, i: int) -> tuple:
    """Return the active set at position i, sorted by first-insert order."""
    active = set()
    for e, lo, hi in ops:
        if lo <= i <= hi:
            active.add(e)
    return tuple(sorted(active, key=lambda e: first_seen[e]))


def test_random_inserts_match_brute_force():
    rng = random.Random(SEED)
    ops: list[tuple] = []
    for _ in range(N_OPS):
        e = ELEMENTS[rng.randrange(len(ELEMENTS))]
        lo = rng.randint(-COORD_BOUND, COORD_BOUND)
        hi = lo + rng.randint(0, 30)
        ops.append((e, lo, hi))

    r: Rangeable = Rangeable()
    for e, lo, hi in ops:
        r.insert(e, start=lo, end=hi)

    first_seen = _build_first_seen(ops)
    failures = 0
    sample_failure = None
    for i in range(-COORD_BOUND, COORD_BOUND + 1):
        expected = _brute_force_active(ops, first_seen, i)
        actual = r[i].objs
        if expected != actual:
            failures += 1
            if sample_failure is None:
                sample_failure = (i, expected, actual)
    assert failures == 0, f"{failures} mismatches; first={sample_failure}"


def test_random_get_range_matches_brute_force():
    rng = random.Random(SEED ^ 0xDEADBEEF)
    ops: list[tuple] = []
    for _ in range(500):
        e = ELEMENTS[rng.randrange(len(ELEMENTS))]
        lo = rng.randint(-COORD_BOUND, COORD_BOUND)
        hi = lo + rng.randint(0, 30)
        ops.append((e, lo, hi))

    r: Rangeable = Rangeable()
    for e, lo, hi in ops:
        r.insert(e, start=lo, end=hi)

    # Brute-force canonicalisation: collect every covered coord per element,
    # then re-merge into disjoint intervals.
    by_element: dict = {}
    for e, lo, hi in ops:
        by_element.setdefault(e, set()).update(range(lo, hi + 1))

    for e, covered in by_element.items():
        if not covered:
            assert r.get_range(e) == []
            continue
        sorted_coords = sorted(covered)
        ranges: list[tuple[int, int]] = []
        run_lo = sorted_coords[0]
        prev = run_lo
        for c in sorted_coords[1:]:
            if c == prev + 1:
                prev = c
            else:
                ranges.append((run_lo, prev))
                run_lo = c
                prev = c
        ranges.append((run_lo, prev))
        assert r.get_range(e) == ranges
