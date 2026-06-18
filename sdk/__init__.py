"""
DEPRECATED — legacy `sdk` package (codename "Wayne Brain").

Use the public package instead:

    from reliability_gate import ReliabilityGate, AbstentionRequired

Kept as a backward-compatibility shim only. Not shipped in the public wheel.
"""
import warnings

warnings.warn(
    "The `sdk` package is deprecated; import from `reliability_gate` instead.",
    DeprecationWarning,
    stacklevel=2,
)

from reliability_gate.client import (  # noqa: F401,E402
    ReliabilityGate,
    ReliabilityGateClient,
    ReliabilityDecision,
    CISResult,
    ReliabilityGateError,
    AbstentionRequired,
    APIError,
    ConnectionError,
    WayneBrain,
    WayneBrainError,
    CognitiveLayer,
)
