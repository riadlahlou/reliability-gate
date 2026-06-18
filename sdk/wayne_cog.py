"""
DEPRECATED — `sdk.wayne_cog` is the legacy import path (codename "Wayne Brain").

Use the public package instead:

    from reliability_gate import ReliabilityGate, AbstentionRequired

This module re-exports the canonical implementation from `reliability_gate`
for backward compatibility only. It emits a DeprecationWarning on import and is
NOT shipped in the public wheel.
"""
import warnings

warnings.warn(
    "`sdk.wayne_cog` is deprecated; import from `reliability_gate` instead "
    "(e.g. `from reliability_gate import ReliabilityGate`).",
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
    # Legacy names (kept so old code `from sdk.wayne_cog import WayneBrain` works):
    WayneBrain,
    WayneBrainError,
    CognitiveLayer,
)
