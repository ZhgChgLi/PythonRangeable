"""Rangeable — hashable-element interval set with first-insert ordered active queries.

Reference Python implementation of the language-neutral Rangeable spec.
See https://github.com/ZhgChgLi/RangeableRFC for the normative document.
"""

from __future__ import annotations

from ._core import Rangeable
from ._errors import InvalidIntervalError, RangeableError
from ._interval import Interval
from ._slot import Slot
from ._transition import TransitionEvent, TransitionKind

__version__ = "1.0.0"

__all__ = [
    "Rangeable",
    "Interval",
    "Slot",
    "TransitionEvent",
    "TransitionKind",
    "RangeableError",
    "InvalidIntervalError",
    "__version__",
]
