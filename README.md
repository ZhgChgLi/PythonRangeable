# PythonRangeable

[![PyPI](https://img.shields.io/pypi/v/rangeable.svg)](https://pypi.org/project/rangeable/)
[![Python](https://img.shields.io/pypi/pyversions/rangeable.svg)](https://pypi.org/project/rangeable/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Reference Python implementation of [`Rangeable<Element>`](https://github.com/ZhgChgLi/RangeableRFC) — a generic, integer-coordinate, closed-interval set container with first-insert ordered active queries.

## Installation

```bash
pip install rangeable
```

## Usage

```python
from dataclasses import dataclass
from rangeable import Rangeable

@dataclass(frozen=True, slots=True)
class Strong: pass

@dataclass(frozen=True, slots=True)
class Italic: pass

@dataclass(frozen=True, slots=True)
class Link:
    url: str

r: Rangeable = Rangeable()
r.insert(Strong(), start=2, end=5)
r.insert(Strong(), start=3, end=7)        # merges with [2, 5] → [2, 7]
r.insert(Strong(), start=9, end=11)       # disjoint
r.insert(Italic(), start=3, end=8)

r.get_range(Strong())   # [(2, 7), (9, 11)]
r.get_range(Italic())   # [(3, 8)]

r[4].objs               # (Strong(), Italic())   first-insert order
r[8].objs               # (Italic(),)
r[10].objs              # (Strong(),)
```

### Sweep iteration via transitions

```python
for event in r.transitions(lo=0, hi=15):
    print(event.coordinate, event.kind.value, event.element)
```

## API

| Member | Returns | Notes |
|---|---|---|
| `Rangeable()` | constructor | empty container |
| `r.insert(e, *, start, end)` | `Rangeable` (chainable) | raises `InvalidIntervalError` on `start > end` |
| `r[i]` | `Slot[E]` | `Slot.objs` is the active-set tuple |
| `r.get_range(e)` | `list[tuple[int, int]]` | merged disjoint ranges |
| `r.transitions(*, lo, hi)` | `list[TransitionEvent[E]]` | `hi=None` means +∞ |
| `r.count` / `len(r)` | `int` | distinct elements |
| `r.empty` / `bool(r)` | `bool` | |
| `iter(r)` | `Iterator[(E, list[(int, int)])]` | first-insert order |
| `r.copy()` | `Rangeable[E]` | deep copy |
| `r.version` | `int` | unchanged on idempotent insert |

## Semantics

- **End is inclusive**: `[a, b]` covers `a..=b`, both ends.
- **Same-element merging**: equal elements (by `__eq__` + `__hash__`) merge on overlap or integer adjacency. `[2, 4] ∪ [5, 7] = [2, 7]`.
- **Idempotent insert**: re-inserting a contained interval does not bump `version`.
- **Out-of-order rejected**: `r.insert(e, start=5, end=2)` raises `InvalidIntervalError`.
- **Active-set ordering**: deterministic — first-insert order of the element.
- **Coordinate sentinel**: a close event for an interval ending at the optional `int_max` sentinel carries `coordinate is None` (None == +∞ per RFC §4.7). Python ints are unbounded, so this only matters when integrating with bounded-int languages; the fixture does not exercise it.

See [RangeableRFC](https://github.com/ZhgChgLi/RangeableRFC) § 4 for normative semantics and § 10 for the 23-case test contract.

## Cross-language consistency

This Python implementation, the [Ruby implementation](https://github.com/ZhgChgLi/RubyRangeable), and the [Swift implementation](https://github.com/ZhgChgLi/SwiftRangeable) share a 160-op / 86-probe JSON fixture; all three produce byte-identical outputs.

## See also

- **[RangeableRFC](https://github.com/ZhgChgLi/RangeableRFC)** — normative specification.
- **[RubyRangeable](https://github.com/ZhgChgLi/RubyRangeable)** — sibling Ruby reference implementation, published as the `rangeable` gem.
- **[SwiftRangeable](https://github.com/ZhgChgLi/SwiftRangeable)** — sibling Swift reference implementation.
- **[JSRangeable](https://github.com/ZhgChgLi/JSRangeable)** — sibling TypeScript reference implementation, published as the `rangeable-js` npm package.

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
```

The suite covers the full RFC § 10 contract, the cross-language fixture replay, and a property test against a brute-force oracle.

## License

MIT (c) ZhgChgLi
