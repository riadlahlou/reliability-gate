"""
ReliabilityGate — exceptions
============================
Canonical exceptions live in `reliability_gate.client` (single source).
This module re-exports them for `from reliability_gate.exceptions import ...`.

Usage:
    from reliability_gate import AbstentionRequired, APIError, ReliabilityGateError
    # or
    from reliability_gate.exceptions import AbstentionRequired
"""
from reliability_gate.client import (  # noqa: F401
    ReliabilityGateError,
    AbstentionRequired,
    APIError,
    ConnectionError,
    WayneBrainError,  # alias legacy déprécié
)
