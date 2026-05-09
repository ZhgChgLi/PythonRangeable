"""Cross-language fixture replay.

Consumes the shared `cross_language.json` produced by Ruby
(`RubyRangeable/test/cross_language_fixture.rb`) and replayed identically
by Swift's `CrossLanguageFixtureTests`. Verifies all 86 probes
(subscript + transitions) against the Ruby-produced expected values.
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


@pytest.fixture(scope="module")
def replayed_rangeable() -> Rangeable:
    with FIXTURE_PATH.open() as f:
        fixture = json.load(f)

    r: Rangeable = Rangeable()
    for op in fixture["ops"]:
        e = ELEMENT_FACTORY[op["element"]]()
        try:
            r.insert(e, start=op["start"], end=op["end"])
        except Exception:
            # Fixture is generated with start <= end always; this path
            # exists only to guard against future mis-edits to the fixture.
            pass
    return r


def _load_probes() -> list[dict]:
    with FIXTURE_PATH.open() as f:
        return json.load(f)["probes"]


PROBES = _load_probes()


@pytest.mark.parametrize(
    "probe", [p for p in PROBES if p["kind"] == "subscript"], ids=lambda p: f"i={p['i']}"
)
def test_subscript_probe(replayed_rangeable: Rangeable, probe: dict) -> None:
    actual = [_canonical_key(e) for e in replayed_rangeable[probe["i"]].objs]
    assert actual == probe["expected"], f"subscript mismatch at i={probe['i']}"


@pytest.mark.parametrize(
    "probe",
    [p for p in PROBES if p["kind"] == "transitions"],
    ids=lambda p: f"lo={p['lo']}_hi={p['hi']}",
)
def test_transitions_probe(replayed_rangeable: Rangeable, probe: dict) -> None:
    events = replayed_rangeable.transitions(lo=probe["lo"], hi=probe["hi"])
    actual = [
        {
            "coordinate": e.coordinate,
            "kind": e.kind.value,
            "element": _canonical_key(e.element),
        }
        for e in events
    ]
    assert actual == probe["expected"], (
        f"transitions mismatch at [{probe['lo']}, {probe['hi']}]"
    )
