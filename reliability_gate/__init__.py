"""
ReliabilityGate
===============
An anti-gameable permission-to-act layer for autonomous agents.

Usage:
    from reliability_gate import ReliabilityGate, AbstentionRequired

    gate = ReliabilityGate(api_key="my-project", agent_id="gpt-4o")
    gate.observe(prediction=72.0, actual=68.5, domain="finance")
    gate.should_act()  # → True/False — governs the next decision

(Prototyped internally under the codename "Wayne Brain"; the public name is
ReliabilityGate. Legacy names remain only as deprecated aliases.)
"""
from reliability_gate.client import (  # noqa: F401
    ReliabilityGate,
    ReliabilityGateClient,
    CISResult,
    ReliabilityGateError,
    AbstentionRequired,
    APIError,
    ConnectionError,
    # Aliases legacy dépréciés (codename interne) :
    WayneBrain,
    WayneBrainError,
    CognitiveLayer,
)
from reliability_gate.decision import (  # noqa: F401
    ReliabilityDecision,
    decide,
    OBSERVE,
    ADVISORY,
    HARD_GATE,
)

__version__ = "0.1.0"

__all__ = [
    "ReliabilityGate",
    "ReliabilityGateClient",
    "ReliabilityDecision",
    "decide",
    "CISResult",
    "ReliabilityGateError",
    "AbstentionRequired",
    "APIError",
    "ConnectionError",
    "OBSERVE",
    "ADVISORY",
    "HARD_GATE",
    "__version__",
]
