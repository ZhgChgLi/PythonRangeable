"""Cross-language fixture replay (v1 + v2).

Consumes the shared `cross_language.json` and replays it through the
live :class:`Rangeable` implementation. Verifies every probe and every
``set_ops`` ``expected_state`` matches byte-identically against the
fixture (the same JSON that Ruby / Swift / JS / Kotlin / Go consume).

Schema versions handled:

* v1 — no ``schema_version``; ``ops`` are all ``insert``; one snapshot.
* v2 — ``schema_version == 2``; ``ops`` may be
  ``insert``/``remove``/``remove_element``/``clear``/``remove_ranges``;
  probes carry an optional ``phase`` field selecting the snapshot
  (``"v1"`` (or absent) / ``"after_removes"`` / ``"final"``); a
  ``set_ops`` array drives non-mutating set-op conformance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from rangeable import Rangeable

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cross_language.json"


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


# Element index in the fixture corresponds to position in this list.
ELEMENT_FACTORY = (
    lambda: Strong(),
    lambda: Italic(),
    lambda: Code(),
    lambda: Link("a"),
    lambda: Link("b"),
)


def _canonical_key(element) -> str:
    if isinstance(element, Strong):
        return "strong"
    if isinstance(element, Italic):
        return "italic"
    if isinstance(element, Code):
        return "code"
    if isinstance(element, Link):
        return f"link:{element.url}"
    raise AssertionError(f"unknown element {element!r}")


# --------------------------------------------------------------------- #
# Fixture loading
# --------------------------------------------------------------------- #


with FIXTURE_PATH.open() as _f:
    _FIXTURE = json.load(_f)

_SCHEMA_VERSION: int = _FIXTURE.get("schema_version", 1)
_OPS: list[dict] = _FIXTURE["ops"]
_PROBES: list[dict] = _FIXTURE.get("probes", [])
_SET_OPS: list[dict] = _FIXTURE.get("set_ops", [])


def _apply_op(r: Rangeable, op: dict) -> None:
    """Dispatch a single op record onto ``r`` per RFC §6.6–§6.9."""
    kind = op.get("op", "insert")
    if kind == "insert":
        e = ELEMENT_FACTORY[op["element"]]()
        r.insert(e, start=op["start"], end=op["end"])
    elif kind == "remove":
        e = ELEMENT_FACTORY[op["element"]]()
        r.remove(e, start=op["start"], end=op["end"])
    elif kind == "remove_element":
        e = ELEMENT_FACTORY[op["element"]]()
        r.remove_element(e)
    elif kind == "clear":
        r.clear()
    elif kind == "remove_ranges":
        r.remove_ranges(start=op["start"], end=op["end"])
    else:
        raise AssertionError(f"unknown op kind: {kind!r}")


def _build_via_ops(ops: list[dict]) -> Rangeable:
    r: Rangeable = Rangeable()
    for op in ops:
        _apply_op(r, op)
    return r


def _v1_boundary(ops: list[dict]) -> int:
    """Index of the first non-``insert`` op (or ``len(ops)`` if none).

    Matches Ruby's `run_v2`: snapshot 1 is `ops[0:_v1_boundary(ops)]`,
    so callers slice with `ops[0:boundary]`.
    """
    for i, op in enumerate(ops):
        if op.get("op", "insert") != "insert":
            return i
    return len(ops)


def _build_after_removes(ops: list[dict], boundary: int) -> Rangeable:
    """Snapshot 2: v1 ops + the first 30 ``remove`` ops *only*
    (skipping any non-``remove`` op encountered in between).
    """
    r = _build_via_ops(ops[:boundary])
    taken = 0
    for op in ops[boundary:]:
        if taken == 30:
            break
        if op.get("op") == "remove":
            _apply_op(r, op)
            taken += 1
    return r


# --------------------------------------------------------------------- #
# Snapshot construction (module-scoped, shared by all probe tests)
# --------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def snapshots() -> dict[str, Rangeable]:
    """Build the three v2 snapshots (or one v1 snapshot) once per session."""
    if _SCHEMA_VERSION == 1:
        return {"v1": _build_via_ops(_OPS)}
    if _SCHEMA_VERSION != 2:
        raise AssertionError(f"unsupported schema_version: {_SCHEMA_VERSION!r}")

    boundary = _v1_boundary(_OPS)
    return {
        "v1": _build_via_ops(_OPS[:boundary]),
        "after_removes": _build_after_removes(_OPS, boundary),
        "final": _build_via_ops(_OPS),
    }


def _resolve(snapshots: dict[str, Rangeable], probe: dict) -> Rangeable:
    phase = probe.get("phase") or "v1"
    if phase not in snapshots:
        raise AssertionError(
            f"unknown probe phase {phase!r} (have {sorted(snapshots)})"
        )
    return snapshots[phase]


# --------------------------------------------------------------------- #
# Probe assertion (shared between fixture-level probes and set_op probes)
# --------------------------------------------------------------------- #


def _assert_probe(r: Rangeable, probe: dict, *, context: str) -> None:
    kind = probe["kind"]
    if kind == "subscript":
        actual = [_canonical_key(e) for e in r[probe["i"]].objs]
        assert actual == probe["expected"], (
            f"{context}: subscript mismatch at i={probe['i']}: "
            f"actual={actual} expected={probe['expected']}"
        )
    elif kind == "transitions":
        events = r.transitions(lo=probe["lo"], hi=probe["hi"])
        actual = [
            {
                "coordinate": e.coordinate,
                "kind": e.kind.value,
                "element": _canonical_key(e.element),
            }
            for e in events
        ]
        # Re-shape expected to drop any extra keys / preserve order.
        expected = [
            {
                "coordinate": ev["coordinate"],
                "kind": ev["kind"],
                "element": ev["element"],
            }
            for ev in probe["expected"]
        ]
        assert actual == expected, (
            f"{context}: transitions mismatch at "
            f"[{probe['lo']}, {probe['hi']}]: actual={actual} expected={expected}"
        )
    else:
        raise AssertionError(f"{context}: unknown probe kind {kind!r}")


# --------------------------------------------------------------------- #
# Probe IDs (stable, human-readable; phase suffix when present)
# --------------------------------------------------------------------- #


def _probe_id(p: dict) -> str:
    phase = p.get("phase") or "v1"
    if p["kind"] == "subscript":
        return f"{phase}:i={p['i']}"
    return f"{phase}:lo={p['lo']}_hi={p['hi']}"


# --------------------------------------------------------------------- #
# Tests: subscript & transitions probes
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "probe",
    [p for p in _PROBES if p["kind"] == "subscript"],
    ids=lambda p: _probe_id(p),
)
def test_subscript_probe(snapshots: dict[str, Rangeable], probe: dict) -> None:
    _assert_probe(_resolve(snapshots, probe), probe, context="probe")


@pytest.mark.parametrize(
    "probe",
    [p for p in _PROBES if p["kind"] == "transitions"],
    ids=lambda p: _probe_id(p),
)
def test_transitions_probe(snapshots: dict[str, Rangeable], probe: dict) -> None:
    _assert_probe(_resolve(snapshots, probe), probe, context="probe")


# --------------------------------------------------------------------- #
# Set-op conformance (RFC §6.10–§6.13)
# --------------------------------------------------------------------- #


def _apply_set_op(self_r: Rangeable, other_r: Rangeable, name: str) -> Rangeable:
    """Dispatch the *non-mutating* set op named ``name``.

    Note the fixture spelling: ``intersect`` (matches Ruby's method
    name) maps onto Python's :meth:`Rangeable.intersection`.
    """
    if name == "union":
        return self_r.union(other_r)
    if name == "intersect":
        return self_r.intersection(other_r)
    if name == "difference":
        return self_r.difference(other_r)
    if name == "symmetric_difference":
        return self_r.symmetric_difference(other_r)
    raise AssertionError(f"unknown set op {name!r}")


def _serialise_state(r: Rangeable) -> dict:
    """Snapshot ``r`` into the fixture's ``expected_state`` shape."""
    insertion_order: list[str] = []
    intervals: dict[str, list[list[int]]] = {}
    for element, pairs in r:
        key = _canonical_key(element)
        insertion_order.append(key)
        intervals[key] = [[lo, hi] for lo, hi in pairs]
    return {"insertion_order": insertion_order, "intervals": intervals}


def _normalise_intervals(d: dict) -> dict:
    """Coerce expected ``intervals`` values from ``[lo, hi]`` (which JSON
    decodes as `list`) so dict comparison is well-defined.

    The fixture's intervals are already lists of two-element lists, so
    this is a no-op, but it documents the contract.
    """
    return {k: [list(pair) for pair in v] for k, v in d.items()}


@pytest.mark.parametrize(
    "entry",
    _SET_OPS,
    ids=lambda e: e["id"],
)
def test_set_op(entry: dict) -> None:
    self_r = _build_via_ops(entry["self_ops"])
    other_r = _build_via_ops(entry["other_ops"])
    result = _apply_set_op(self_r, other_r, entry["op"])
    if entry.get("chain_ops"):
        chain_r = _build_via_ops(entry["chain_ops"])
        result = _apply_set_op(result, chain_r, entry["op"])

    expected_state = entry["expected_state"]
    actual_state = _serialise_state(result)

    assert actual_state["insertion_order"] == expected_state["insertion_order"], (
        f"set_op {entry['id']}: insertion_order mismatch: "
        f"actual={actual_state['insertion_order']} "
        f"expected={expected_state['insertion_order']}"
    )
    assert actual_state["intervals"] == _normalise_intervals(
        expected_state["intervals"]
    ), (
        f"set_op {entry['id']}: intervals mismatch: "
        f"actual={actual_state['intervals']} "
        f"expected={expected_state['intervals']}"
    )

    for p in entry.get("probes") or []:
        _assert_probe(result, p, context=f"set_op {entry['id']}")
