"""
ReliabilityGate — CIS Engine (standalone)
======================================
Implémente la vraie formule CIS à 4 composantes directement sur une liste
d'outcomes bruts (sans dépendance à causal_recall / cell_store de Wayne OS).

FORMULE CANONIQUE (identique à core/cognitive_integrity_score.py) :
  CIS = 0.40 × mae_score         (calibration prédiction vs réalité)
      + 0.25 × abstention_score  (se tait au bon moment)
      + 0.20 × skill_score       (bat la baseline naïve persistence)
      + 0.15 × falsif_score      (peu de fausses prédictions fortes)

LABELS (seuils canoniques) :
  [0.00, 0.40) → unreliable  : ne pas décider sans supervision
  [0.40, 0.65) → learning    : décisions taguées incertaines
  [0.65, 0.85) → calibrated  : fiabilité établie
  [0.85, 1.00] → trusted     : fiabilité élevée

Référence : core/cognitive_integrity_score.py (formules identiques)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# ── Poids canoniques ───────────────────────────────────────────────────────────
_W_MAE    = 0.40
_W_ABST   = 0.25
_W_SKILL  = 0.20
_W_FALSIF = 0.15

# ── Seuils ────────────────────────────────────────────────────────────────────
_MAE_FLOOR       = 40.0   # MAE ≥ 40 → score MAE = 0
_FALSIF_FLOOR    = 30.0   # falsif ≥ 30% → score falsif = 0
_FALSIF_THRESH   = 20.0   # |erreur| > 20 → comptée comme "forte erreur" (falsification)

_CIS_TRUSTED     = 0.85
_CIS_CALIBRATED  = 0.65
_CIS_LEARNING    = 0.40
_MIN_OUTCOMES    = 3
_MAE_WINDOW      = 20     # fenêtre pour le calcul du MAE et du skill


# ── Sous-formules (identiques au core) ────────────────────────────────────────

def _mae_to_score(mae: float | None) -> float:
    """MAE → score [0,1]. Décroissant. log-linéaire pour sensibilité aux petites MAE."""
    if mae is None:
        return 0.0
    if mae <= 0.0:
        return 1.0
    if mae >= _MAE_FLOOR:
        return 0.0
    return round(max(0.0, 1.0 - math.log1p(mae) / math.log1p(_MAE_FLOOR)), 3)


def _skill_to_score(forecast_skill: float | None) -> float:
    """forecast_skill → score [0,1]."""
    if forecast_skill is None:
        return 0.0
    if forecast_skill < -0.05:   # harmful_vs_persistence
        return 0.0
    if forecast_skill < 0.05:    # no_skill_vs_persistence
        return 0.4
    # real_anticipation : skill ∈ (0.05, 1] → score ∈ (0.5, 1]
    return round(min(1.0, 0.5 + forecast_skill * 0.5), 3)


def _skill_label(forecast_skill: float | None) -> str:
    if forecast_skill is None:
        return "insufficient"
    if forecast_skill < -0.05:
        return "harmful_vs_persistence"
    if forecast_skill < 0.05:
        return "no_skill_vs_persistence"
    return "real_anticipation"


def _falsif_to_score(falsif_rate: float | None) -> float:
    """Taux de falsification → score [0,1]. Décroissant."""
    if falsif_rate is None:
        return 0.5   # neutre : pas assez de données
    if falsif_rate <= 0.0:
        return 1.0
    if falsif_rate >= _FALSIF_FLOOR:
        return 0.0
    return round(1.0 - falsif_rate / _FALSIF_FLOOR, 3)


_MAE_RELIABLE = 12.0   # MAE en deçà = acting fiable (seuil "calibré", cohérent _mae_to_score)


def _abstention_score(mae: float | None, abstention_rate: float,
                      mae_improving: bool | None) -> float:
    """Qualité d'abstention = SÉLECTIVITÉ MESURÉE, pas un simple taux.

    Mesure si l'agent prend de bonnes décisions agir/s'abstenir :
      (a) il agit de façon fiable (faible erreur sur les prédictions AGIES) ;
      (b) il ne s'abstient pas excessivement.
    Pénalise fortement l'agent IMPRUDENT : erreur élevée sur ce qu'il agit MAIS
    ne s'abstient quasi jamais — il devrait se taire quand il ne sait pas, il ne
    le fait pas (échec d'abstention). C'est ce qui distingue cette composante de
    la simple MAE : elle juge la DÉCISION agir/s'abstenir, pas que la précision.

    Cas limites honnêtes :
      - que des abstentions (mae None) → 0.5 neutre (fiabilité d'action non évaluable) ;
      - acting fiable → score élevé, quel que soit le taux d'abstention.
    """
    if mae is None:
        return 0.5
    sel = _mae_to_score(mae)                       # acting fiable → élevé
    # Imprudence : agir mal SANS s'abstenir = l'échec d'abstention central.
    if mae >= _MAE_RELIABLE and abstention_rate < 0.10:
        sel *= 0.3
    elif mae >= _MAE_RELIABLE and abstention_rate < 0.30:
        sel *= 0.6
    # Sur-abstention : se tait trop (agit sur presque rien).
    if abstention_rate > 0.6:
        sel *= 0.7
    # Nudge calibration (signal secondaire).
    if mae_improving is True:
        sel = min(1.0, sel + 0.05)
    elif mae_improving is False:
        sel = max(0.0, sel - 0.1)
    return round(max(0.0, min(1.0, sel)), 3)


# ── Résultat structuré ─────────────────────────────────────────────────────────

@dataclass
class CISResult:
    """Résultat complet du calcul CIS depuis des outcomes bruts."""
    cis: float
    label: str
    n: int
    mae: float | None
    forecast_skill: float | None
    skill_label: str
    falsification_rate_pct: float | None
    abstention_rate: float
    mae_improving: bool | None
    components: dict[str, float]
    should_abstain: bool
    observation_backed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "cis": self.cis,
            "label": self.label,
            "n": self.n,
            "mae": self.mae,
            "forecast_skill": self.forecast_skill,
            "skill_label": self.skill_label,
            "falsification_rate_pct": self.falsification_rate_pct,
            "abstention_rate": self.abstention_rate,
            "mae_improving": self.mae_improving,
            "components": self.components,
            "should_abstain": self.should_abstain,
            "observation_backed": self.observation_backed,
        }


# ── Fonction principale ────────────────────────────────────────────────────────

def compute_cis_from_outcomes(outcomes: list[dict[str, Any]]) -> CISResult:
    """Calcule le CIS complet depuis une liste d'outcomes bruts.

    Chaque outcome est un dict avec au minimum :
      - prediction : float | None   (valeur prédite, 0-100)
      - actual     : float | None   (valeur observée, 0-100)
      - abstained  : bool           (l'agent s'est-il abstenu ?)

    Retourne un CISResult avec le score CIS et le détail des 4 composantes.
    """
    if not outcomes:
        return _insufficient(0)

    # ── 1. Collecter les paires (prediction, actual) ──────────────────────────
    errors: list[float] = []          # |prediction - actual|
    p_errors: list[float] = []        # |actual[i-1] - actual[i]| (persistence baseline)
    last_actual: float | None = None
    abstentions = 0

    window = outcomes[-_MAE_WINDOW:]  # fenêtre glissante

    for o in window:
        if o.get("abstained"):
            abstentions += 1
            last_actual = o.get("actual", last_actual)
            continue
        pred = o.get("prediction")
        actual = o.get("actual")
        if pred is not None and actual is not None:
            err = abs(float(pred) - float(actual))
            errors.append(err)
            if last_actual is not None:
                p_errors.append(abs(last_actual - float(actual)))
            last_actual = float(actual)

    n = len(errors)
    if n < _MIN_OUTCOMES:
        return _insufficient(n)

    # ── 2. MAE ────────────────────────────────────────────────────────────────
    mae = sum(errors) / n

    # MAE trend : 1ère moitié vs 2ème moitié (improving / worsening / stable)
    mid = n // 2
    mae_improving: bool | None = None
    if mid >= 2:
        old_mae = sum(errors[:mid]) / mid
        new_mae = sum(errors[mid:]) / (n - mid)
        if new_mae < old_mae - 2.0:
            mae_improving = True
        elif new_mae > old_mae + 2.0:
            mae_improving = False

    # ── 3. Forecast skill vs persistence baseline ─────────────────────────────
    forecast_skill: float | None = None
    if len(p_errors) >= _MIN_OUTCOMES:
        p_mae = sum(p_errors) / len(p_errors)
        if p_mae > 1e-6:
            forecast_skill = round(1.0 - mae / p_mae, 3)
        else:
            forecast_skill = 0.0  # trivial_static : série plate

    # ── 4. Taux de falsification (erreurs "fortes" > seuil) ───────────────────
    strong_errors = sum(1 for e in errors if e > _FALSIF_THRESH)
    falsif_rate = round(100.0 * strong_errors / n, 1) if n > 0 else None

    # ── 5. Taux d'abstention (sur toute la fenêtre) ───────────────────────────
    window_total = len(window)
    abstention_rate = abstentions / window_total if window_total > 0 else 0.0

    # ── 6. Calcul des 4 scores de composantes ─────────────────────────────────
    mae_score    = _mae_to_score(mae)
    skill_score  = _skill_to_score(forecast_skill)
    falsif_score = _falsif_to_score(falsif_rate)
    abst_score   = _abstention_score(mae, abstention_rate, mae_improving)

    # ── 7. CIS final (formule canonique) ──────────────────────────────────────
    cis_raw = (
        _W_MAE    * mae_score
        + _W_ABST   * abst_score
        + _W_SKILL  * skill_score
        + _W_FALSIF * falsif_score
    )
    cis = round(cis_raw, 3)

    # ── 8. Label ──────────────────────────────────────────────────────────────
    if cis >= _CIS_TRUSTED:
        label = "trusted"
    elif cis >= _CIS_CALIBRATED:
        label = "calibrated"
    elif cis >= _CIS_LEARNING:
        label = "learning"
    else:
        label = "unreliable"

    should_abstain = label in ("unreliable",)

    return CISResult(
        cis=cis,
        label=label,
        n=n,
        mae=round(mae, 2),
        forecast_skill=forecast_skill,
        skill_label=_skill_label(forecast_skill),
        falsification_rate_pct=falsif_rate,
        abstention_rate=round(abstention_rate, 3),
        mae_improving=mae_improving,
        components={
            "mae_score":    mae_score,
            "abstention_score": abst_score,
            "skill_score":  skill_score,
            "falsif_score": falsif_score,
        },
        should_abstain=should_abstain,
        observation_backed=n >= _MIN_OUTCOMES,
    )


def _insufficient(n: int) -> CISResult:
    return CISResult(
        cis=0.0,
        label="insufficient_data" if n > 0 else "no_data",
        n=n,
        mae=None,
        forecast_skill=None,
        skill_label="insufficient",
        falsification_rate_pct=None,
        abstention_rate=0.0,
        mae_improving=None,
        components={"mae_score": 0.0, "abstention_score": 0.0, "skill_score": 0.0, "falsif_score": 0.0},
        should_abstain=True,
        observation_backed=False,
    )


__all__ = ["compute_cis_from_outcomes", "CISResult", "_CIS_LEARNING", "_CIS_CALIBRATED", "_CIS_TRUSTED"]
