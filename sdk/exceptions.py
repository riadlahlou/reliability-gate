"""
DEPRECATED — legacy `sdk.exceptions` (codename "Wayne Brain").

Use the public package instead:

    from reliability_gate import AbstentionRequired, APIError, ReliabilityGateError

Backward-compatibility shim only.
"""
from reliability_gate.client import (  # noqa: F401
    ReliabilityGateError,
    AbstentionRequired,
    APIError,
    ConnectionError,
    WayneBrainError,  # alias legacy déprécié
)
