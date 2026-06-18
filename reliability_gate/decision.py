"""
ReliabilityGate — action-aware decision (V0)
============================================
Décide non seulement si un agent est globalement fiable, mais s'il a *mérité le
droit d'exécuter une action donnée*.

Logique PURE (aucune dépendance réseau / serveur) — testable directement.
Le client `ReliabilityGate.should_act(action=...)` se contente de récupérer les
scores (global + action) puis appelle `decide(...)`.

Croise trois signaux :
  1. score GLOBAL de l'agent (CIS)         → un agent globalement peu fiable
     n'a pas le droit d'exécuter une action RISQUÉE ;
  2. score ACTION-spécifique (CIS filtré)  → l'action elle-même doit être prouvée ;
  3. taille d'échantillon vs requis        → pas assez de preuves action-spécifiques
     → on ne CLAIME pas la fiabilité (advisory/observe), on ne bloque pas à tort.

Trois modes d'enforcement (comment le verdict est *appliqué*) :
  - "observe"   : ne bloque JAMAIS (allow=True), log/recommande seulement ;
  - "advisory"  : ne bloque pas (allow=True), expose une recommandation allow/block ;
  - "hard_gate" : bloque réellement (allow=False) quand le verdict est un blocage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ── Enforcement modes (comment le verdict est appliqué) ────────────────────────
OBSERVE = "observe"
ADVISORY = "advisory"
HARD_GATE = "hard_gate"
_ENFORCEMENT_MODES = {OBSERVE, ADVISORY, HARD_GATE}

# ── Decision modes (résultat effectif exposé à l'appelant) ─────────────────────
MODE_OBSERVE_ONLY = "OBSERVE_ONLY"
MODE_ADVISORY = "ADVISORY"
MODE_SOFT_BLOCK = "SOFT_BLOCK"
MODE_HARD_BLOCK = "HARD_BLOCK"
MODE_ALLOW = "ALLOW"

# ── Recommandations (l'avis du gate, indépendant de l'enforcement) ─────────────
RECO_ALLOW = "allow"
RECO_BLOCK = "block"
RECO_GATHER = "gather_more_data"

# ── Seuils CIS (bandes canoniques du moteur, cf. storage/cis_engine.py) ────────
_BLOCK_CIS = 0.40   # CIS < 0.40 → "unreliable"
_ALLOW_CIS = 0.65   # CIS ≥ 0.65 → "calibrated"/"trusted" → action prouvée

# ── Taxonomie de risque → (required_sample_size, risky) ────────────────────────
# Une action "risquée" (customer-visible / destructrice / financière) exige
# davantage de preuves action-spécifiques avant tout ALLOW autonome.
_RISK_TABLE: dict[str, tuple[int, bool]] = {
    "low":             (3,  False),
    "internal":        (3,  False),
    "read_only":       (3,  False),
    "readonly":        (3,  False),
    "normal":          (5,  False),
    "medium":          (10, True),
    "customer_visible": (10, True),
    "high":            (20, True),
    "irreversible":    (20, True),
    "destructive":     (20, True),
    "financial":       (20, True),
}
# Risque inconnu → fail-closed : traité comme "high" (le plus exigeant).
_DEFAULT_RISK: tuple[int, bool] = (20, True)


def _risk_entry(risk_level: str) -> tuple[int, bool]:
    return _RISK_TABLE.get((risk_level or "").strip().lower(), _DEFAULT_RISK)


def required_sample_size(risk_level: str) -> int:
    """Nombre minimal d'outcomes action-spécifiques requis pour ce niveau de risque."""
    return _risk_entry(risk_level)[0]


def is_risky(risk_level: str) -> bool:
    """True si l'action est considérée risquée (customer-visible / destructrice / inconnue)."""
    return _risk_entry(risk_level)[1]


# ── Résultat structuré ─────────────────────────────────────────────────────────

@dataclass
class ReliabilityDecision:
    """Verdict action-aware retourné par `ReliabilityGate.should_act(action=...)`.

    Truthy ssi `allow` (donc `if gate.should_act(action="x"):` fonctionne aussi).

    ⚠️ Sémantique `allow` vs `recommended_allow` (à ne PAS confondre) :
      - `allow` (= `enforced_allow`) : la décision EFFECTIVE selon `enforcement_mode`.
        C'est ce que `if decision.allow:` exécute. En `observe`/`advisory`, elle est
        TOUJOURS True — « not enforced », PAS « safe ». Seul `hard_gate` peut la mettre
        à False.
      - `recommended_allow` : ce que le gate PENSE qu'il faudrait faire, indépendamment
        du mode. False si le gate recommande de bloquer OU s'il manque des preuves
        (`gather_more_data`). Pour lire l'avis réel du gate, utilisez ce champ
        (ou `recommendation`), pas `allow` en mode observe/advisory.
    """
    allow: bool                     # décision EFFECTIVE (selon enforcement_mode) — alias: enforced_allow
    mode: str                       # OBSERVE_ONLY | ADVISORY | SOFT_BLOCK | HARD_BLOCK | ALLOW
    reason: str
    agent_id: str
    action: str
    risk_level: str
    cis_score: float                # score GLOBAL de l'agent
    enforcement_mode: str           # observe | advisory | hard_gate
    recommendation: str             # allow | block | gather_more_data
    recommended_allow: bool         # avis du gate (True ssi recommendation == "allow")
    enforced_allow: bool            # = allow (décision effective, nom explicite)
    sample_size: int                # outcomes action-spécifiques disponibles
    required_sample_size: int       # outcomes requis pour ce risk_level
    action_score: float | None = None   # CIS filtré sur l'action (None si indisponible)

    def __bool__(self) -> bool:
        return self.allow

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:
        return (
            f"ReliabilityDecision(allow={self.allow}, mode={self.mode!r}, "
            f"action={self.action!r}, recommendation={self.recommendation!r}, "
            f"reason={self.reason!r})"
        )


# ── Verdict brut (indépendant de l'enforcement) ────────────────────────────────

def _raw_verdict(
    cis_score: float,
    action_score: float | None,
    sample_size: int,
    required_n: int,
    risky: bool,
    risk_level: str,
    action: str,
) -> tuple[str, str, str]:
    """Retourne (verdict, recommendation, reason).

    verdict ∈ {ALLOW, BLOCK_HARD, BLOCK_SOFT, INSUFFICIENT}.
    Ordre des règles : sécurité d'abord (agent faible sur action risquée), puis
    suffisance des preuves, puis qualité de l'action.
    """
    # Règle A — agent globalement peu fiable tentant une action risquée → blocage dur.
    if risky and cis_score < _BLOCK_CIS:
        return (
            "BLOCK_HARD", RECO_BLOCK,
            f"agent global reliability too low (CIS={cis_score:.3f} < {_BLOCK_CIS:.2f}) "
            f"for a {risk_level} action '{action}'",
        )
    # Règle B — pas assez de preuves action-spécifiques → on ne claime PAS la fiabilité.
    if sample_size < required_n:
        return (
            "INSUFFICIENT", RECO_GATHER,
            f"not enough action-specific outcomes yet "
            f"({sample_size}/{required_n} for '{action}')",
        )
    # Règle C — preuves suffisantes + action prouvée fiable → autorisation.
    if action_score is not None and action_score >= _ALLOW_CIS:
        return (
            "ALLOW", RECO_ALLOW,
            f"action '{action}' proven reliable "
            f"(action_score={action_score:.3f}, n={sample_size})",
        )
    # Règle D — preuves suffisantes mais fiabilité de l'action insuffisante → blocage.
    score_txt = "n/a" if action_score is None else f"{action_score:.3f}"
    if cis_score < _BLOCK_CIS:
        return (
            "BLOCK_HARD", RECO_BLOCK,
            f"action '{action}' reliability insufficient "
            f"(action_score={score_txt}, CIS={cis_score:.3f})",
        )
    return (
        "BLOCK_SOFT", RECO_BLOCK,
        f"action '{action}' not yet proven reliable "
        f"(action_score={score_txt}, CIS={cis_score:.3f})",
    )


# ── Fonction publique de décision ──────────────────────────────────────────────

def decide(
    *,
    agent_id: str,
    action: str,
    risk_level: str = "medium",
    cis_score: float,
    action_score: float | None,
    sample_size: int,
    enforcement_mode: str = ADVISORY,
) -> ReliabilityDecision:
    """Décision action-aware PURE. Voir module docstring pour la sémantique.

    `enforcement_mode` inconnu → ramené à "advisory" (jamais bloquant par défaut).
    """
    enforcement = (enforcement_mode or ADVISORY).strip().lower()
    if enforcement not in _ENFORCEMENT_MODES:
        enforcement = ADVISORY  # fail vers non-bloquant

    risky = is_risky(risk_level)
    required_n = required_sample_size(risk_level)

    verdict, recommendation, reason = _raw_verdict(
        cis_score=cis_score,
        action_score=action_score,
        sample_size=sample_size,
        required_n=required_n,
        risky=risky,
        risk_level=risk_level,
        action=action,
    )

    # Application de l'enforcement → (mode effectif, allow).
    if enforcement == OBSERVE:
        mode, allow = MODE_OBSERVE_ONLY, True
    elif enforcement == ADVISORY:
        mode, allow = MODE_ADVISORY, True
    else:  # HARD_GATE — seul mode qui peut poser allow=False
        if verdict == "ALLOW":
            mode, allow = MODE_ALLOW, True
        elif verdict == "BLOCK_HARD":
            mode, allow = MODE_HARD_BLOCK, False
        elif verdict == "BLOCK_SOFT":
            mode, allow = MODE_SOFT_BLOCK, False
        else:  # INSUFFICIENT
            if risky:
                mode, allow = MODE_SOFT_BLOCK, False   # action risquée non prouvée → précaution
            else:
                mode, allow = MODE_ALLOW, True          # action peu risquée + données manquantes → ne pas bloquer

    # Avis du gate, indépendant de l'enforcement : True seulement si le gate
    # recommande explicitement d'agir (ni "block" ni "gather_more_data").
    recommended_allow = (recommendation == RECO_ALLOW)

    return ReliabilityDecision(
        allow=allow,
        mode=mode,
        reason=reason,
        agent_id=agent_id,
        action=action,
        risk_level=risk_level,
        cis_score=round(float(cis_score), 3),
        enforcement_mode=enforcement,
        recommendation=recommendation,
        recommended_allow=recommended_allow,
        enforced_allow=allow,
        sample_size=int(sample_size),
        required_sample_size=int(required_n),
        action_score=(round(float(action_score), 3) if action_score is not None else None),
    )


__all__ = [
    "ReliabilityDecision",
    "decide",
    "required_sample_size",
    "is_risky",
    "OBSERVE",
    "ADVISORY",
    "HARD_GATE",
    "MODE_OBSERVE_ONLY",
    "MODE_ADVISORY",
    "MODE_SOFT_BLOCK",
    "MODE_HARD_BLOCK",
    "MODE_ALLOW",
    "RECO_ALLOW",
    "RECO_BLOCK",
    "RECO_GATHER",
]
