# Changelog

All notable changes to this project will be documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-10

Initial public release of the Python reference implementation of the
[Rangeable RFC](https://github.com/ZhgChgLi/RangeableRFC).

### Added
- `Rangeable[E]` generic container with the full RFC §3 API:
  `insert`, `__getitem__` / `active_at`, `get_range`, `transitions`,
  `copy`, iteration over `(element, ranges)` pairs, `len`, `__bool__`,
  `version`, `count`, `empty`.
- `Interval`, `Slot`, `TransitionEvent`, `TransitionKind` value types
  (frozen dataclasses with slots).
- `RangeableError` (subclass of `ValueError`) and
  `InvalidIntervalError` (subclass of `RangeableError`).
- PEP 561 `py.typed` marker for downstream type checkers.

### Verified
- 23 RFC §10 contract tests.
- 86 cross-language probes against the shared 160-op fixture (sha256
  `316ac8619fd632174b2374ed2137348e8d744e3904b002761d0dbdce38ea2edf`,
  byte-identical to the Ruby and Swift fixtures).
- Property test against a brute-force oracle over 1000 random ops.
