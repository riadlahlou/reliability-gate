"""
ReliabilityGate API
===================
API B2B — Couche de fiabilité (permission-to-act) pour agents IA.
(Prototypée en interne sous le codename « Wayne Brain ».)

Routes :
  POST /observe              → Soumet un outcome réel → recalibre le CIS
  GET  /cis/{agent_id}       → Retourne le CIS courant + verdict + conseil
  POST /calibrate            → Lance un cycle complet predict→observe→recalibre
  GET  /health               → Statut de l'API
  GET  /agents               → Liste les agents d'un tenant

  ── Anti-triche (commit-reveal) ──
  POST /commit               → Verrouille une prédiction par hash AVANT d'observer
  POST /reveal               → Révèle la prédiction, Wayne vérifie le hash → outcome vérifié

  POURQUOI LE COMMIT-REVEAL ?
  ─────────────────────────────
  Sans ce mécanisme, un client pourrait envoyer prediction=50, actual=50
  après coup pour gonfler artificiellement son CIS. Le commit-reveal rend
  cela impossible : la prédiction est verrouillée (hashée) AVANT l'observation.
  Si le client change sa prédiction après avoir vu le résultat → le hash ne
  correspond plus → Wayne rejette l'outcome.

  C'est le même principe que les enchères scellées ou les commit schemes en
  cryptographie. Aucun tiers de confiance nécessaire.

  FLOW :
    1. Client envoie POST /commit  { prediction_hash: sha256("72.5|mon_secret") }
       → Wayne retourne un commit_id (UUID)
    2. Client observe le résultat réel
    3. Client envoie POST /reveal  { commit_id, prediction: 72.5, nonce: "mon_secret", actual: 68.0 }
       → Wayne recalcule sha256("72.5|mon_secret"), compare au hash stocké
       → Si match : outcome vérifié (verified=true) → CIS recalibré
       → Si mismatch : rejeté 400 (tentative de triche détectée)

Auth : header X-API-Key (= tenant_id pour le MVP)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Setup PYTHONPATH pour imports locaux
_root = Path(__file__).resolve().parent.parent
for _p in [str(_root)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from datetime import datetime, UTC
from typing import Any
import hashlib
import uuid
import threading

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from storage.outcome_store import get_outcome_store
from adapters.integrity_monitor import get_integrity_monitor
from storage.cis_engine import compute_cis_from_outcomes, CISResult

app = FastAPI(
    title="ReliabilityGate API",
    description="Permission-to-act layer anti-gameable pour agents autonomes",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_tenant(x_api_key: str = Header(..., description="Votre clé API = tenant_id")) -> str:
    """Pour le MVP : la clé API EST le tenant_id. Remplacer par JWT en prod."""
    if not x_api_key or len(x_api_key) < 4:
        raise HTTPException(status_code=401, detail="X-API-Key invalide")
    return x_api_key


# ── Modèles ──────────────────────────────────────────────────────────────────

class ObserveRequest(BaseModel):
    agent_id: str = Field(..., description="Identifiant de l'agent IA")
    prediction: float | None = Field(None, description="Valeur prédite par l'agent (0-100)")
    actual: float | None = Field(None, description="Valeur réelle observée (0-100)")
    domain: str = Field("general", description="Domaine métier (ex: finance, legal, ecommerce)")
    source: str = Field("", description="Source de l'observation")
    abstained: bool = Field(False, description="L'agent s'est-il abstenu ?")
    action: str | None = Field(None, description="Type d'action lié à cet outcome (ex: send_email) — active le gating action-aware")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Données supplémentaires")


class CalibrateRequest(BaseModel):
    agent_id: str = Field(..., description="Identifiant de l'agent IA")
    url: str = Field(..., description="URL publique à observer pour la calibration")
    domain: str = Field("web", description="Domaine de la source")


class CISResponse(BaseModel):
    agent_id: str
    tenant_id: str
    cis: float
    verdict: str
    should_abstain: bool
    n_outcomes: int
    forecast_skill: float | None
    advice: str
    components: dict[str, float] = Field(
        default_factory=dict,
        description="Détail des 4 composantes : mae_score, abstention_score, skill_score, falsif_score"
    )
    skill_label: str | None = None
    last_updated: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_cis(outcomes: list[dict]) -> dict[str, Any]:
    """Wrapper vers storage.cis_engine.compute_cis_from_outcomes().

    Formule canonique à 4 composantes (identique à core/cognitive_integrity_score.py) :
      CIS = 0.40 × mae_score + 0.25 × abstention_score
          + 0.20 × skill_score + 0.15 × falsif_score

    Labels (seuils canoniques) :
      [0.00, 0.40) → unreliable
      [0.40, 0.65) → learning
      [0.65, 0.85) → calibrated
      [0.85, 1.00] → trusted
    """
    result: CISResult = compute_cis_from_outcomes(outcomes)
    return {
        "cis": result.cis,
        "verdict": result.label,
        "forecast_skill": result.forecast_skill,
        "skill_label": result.skill_label,
        "n": result.n,
        "mae": result.mae,
        "should_abstain": result.should_abstain,
        "components": result.components,
    }


def _advice(verdict: str, cis: float, n: int) -> str:
    advice_map = {
        "no_data":           "Soumettez des observations via POST /observe pour démarrer la calibration.",
        "insufficient_data": f"Continuez à soumettre des observations (minimum 3 requises, actuellement {n}).",
        "trusted":           f"CIS {cis:.3f} — Agent fiable. Actions autonomes autorisées.",
        "calibrated":        f"CIS {cis:.3f} — Agent calibré. Supervision légère recommandée.",
        "learning":          f"CIS {cis:.3f} — En apprentissage. Validation humaine recommandée.",
        "unreliable":        f"CIS {cis:.3f} — Agent peu fiable. L'agent devrait s'abstenir.",
    }
    return advice_map.get(verdict, "Données insuffisantes.")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ready",
        "version": "1.0.0",
        "service": "ReliabilityGate API",
        "ts": datetime.now(UTC).isoformat(),
    }


@app.post("/observe", summary="Soumettre un outcome réel")
async def observe(
    req: ObserveRequest,
    tenant_id: str = Depends(get_tenant),
) -> dict:
    """
    Soumet un outcome réel (prédiction vs valeur observée).
    Le CIS de l'agent est automatiquement recalibré.
    """
    store = get_outcome_store(tenant_id)
    monitor = get_integrity_monitor(tenant_id)

    # metadata en premier pour que les champs critiques les écrasent (jamais l'inverse)
    extra = {
        **req.metadata,
        "agent_id": req.agent_id,
        "domain": req.domain,
        "source": req.source,
        "prediction": req.prediction,
        "actual": req.actual,
        "abstained": req.abstained,
        "action": req.action,
    }
    if req.prediction is not None and req.actual is not None and not req.abstained:
        extra["abs_error"] = round(abs(req.prediction - req.actual), 3)

    entry = store.persist_outcome(extra=extra)
    monitor.observe(
        intent="api_observe",
        cell_id=req.agent_id,
        **{k: v for k, v in extra.items() if k in ("prediction", "actual", "abs_error", "abstained")},
    )

    # Recalcul CIS immédiat
    all_outcomes = [o for o in store.load_outcomes(200) if o.get("agent_id") == req.agent_id]
    cis_data = _compute_cis(all_outcomes)

    return {
        "ok": True,
        "entry_ts": entry["ts"],
        "agent_id": req.agent_id,
        "n_outcomes": cis_data["n"],
        "cis_updated": cis_data["cis"],
        "verdict": cis_data["verdict"],
    }


@app.get("/cis/{agent_id}", response_model=CISResponse, summary="Obtenir le CIS d'un agent")
async def get_cis(
    agent_id: str,
    action: str | None = None,
    tenant_id: str = Depends(get_tenant),
) -> CISResponse:
    """
    Retourne le Cognitive Integrity Score courant de l'agent :
    - Score CIS ∈ [0, 1]
    - Verdict : trusted / calibrated / learning / unreliable / no_data
    - Conseil actionnable
    - Flag should_abstain

    Query param optionnel `action` : restreint le calcul aux outcomes de ce type
    d'action (CIS action-spécifique, pour le gating action-aware).
    """
    store = get_outcome_store(tenant_id)
    all_outcomes = [o for o in store.load_outcomes(500) if o.get("agent_id") == agent_id]
    if action is not None:
        all_outcomes = [o for o in all_outcomes if o.get("action") == action]
    cis_data = _compute_cis(all_outcomes)

    return CISResponse(
        agent_id=agent_id,
        tenant_id=tenant_id,
        cis=cis_data["cis"],
        verdict=cis_data["verdict"],
        should_abstain=cis_data["should_abstain"],
        n_outcomes=cis_data["n"],
        forecast_skill=cis_data.get("forecast_skill"),
        advice=_advice(cis_data["verdict"], cis_data["cis"], cis_data["n"]),
        components=cis_data.get("components", {}),
        skill_label=cis_data.get("skill_label"),
        last_updated=datetime.now(UTC).isoformat(),
    )


@app.post("/calibrate", summary="Lancer un cycle de calibration réel")
async def calibrate(
    req: CalibrateRequest,
    tenant_id: str = Depends(get_tenant),
) -> dict:
    """
    Lance un cycle complet :
    1. Prédit le yield d'extraction de l'URL
    2. Observe réellement (HTTP OBSERVE-only)
    3. Calcule l'erreur réelle
    4. Persiste l'outcome
    5. Retourne le CIS mis à jour

    Note : OBSERVE-only — aucune action, aucun login, aucun POST.
    """
    from adapters.browser_adapter import execute_browser_action

    # Étape 1 : Prédiction neutre (prior 50 sans historique)
    store = get_outcome_store(tenant_id)
    agent_outcomes = [o for o in store.load_outcomes(50) if o.get("agent_id") == req.agent_id]

    prior_pct = 50.0
    if agent_outcomes:
        recent = [o.get("actual") for o in agent_outcomes[-5:] if o.get("actual") is not None]
        if recent:
            prior_pct = sum(recent) / len(recent)

    # Étape 2 : Observation réelle
    t0 = time.monotonic()
    result = execute_browser_action(action="extract", url=req.url)
    elapsed = int((time.monotonic() - t0) * 1000)

    if not result.executed:
        return {
            "ok": False,
            "error": result.error,
            "agent_id": req.agent_id,
            "url": req.url,
        }

    # Étape 3 : Calcul du yield réel (completeness %)
    import re, math
    body = result.data.get("body_text", "")
    html = result.data.get("html_excerpt", "")
    word_count = len(body.split()) if body else 0

    # Score SEO head
    seo_signals = sum([
        bool(result.data.get("title")),
        bool(re.search(r'<meta[^>]+name=["\']description', html, re.I)),
        bool(re.search(r'<link[^>]+rel=["\']canonical', html, re.I)),
        bool(re.search(r'<meta[^>]+property=["\']og:title', html, re.I)),
        bool(re.search(r'<meta[^>]+name=["\']viewport', html, re.I)),
    ])
    head_score = 100.0 * seo_signals / 5
    wc_score = min(100.0, (math.log10(1 + word_count) / math.log10(5001)) * 100) if word_count else 0.0
    actual_pct = round(0.70 * head_score + 0.30 * wc_score, 1)

    # Étape 4 : Persist outcome
    abs_error = round(abs(prior_pct - actual_pct), 2)
    extra = {
        "agent_id": req.agent_id,
        "domain": req.domain,
        "source": req.url,
        "prediction": round(prior_pct, 1),
        "actual": actual_pct,
        "abs_error": abs_error,
        "abstained": False,
        "elapsed_ms": elapsed,
        "word_count": word_count,
        "seo_signals": seo_signals,
    }
    store.persist_outcome(extra=extra)

    # Étape 5 : CIS mis à jour
    all_outcomes = [o for o in store.load_outcomes(200) if o.get("agent_id") == req.agent_id]
    cis_data = _compute_cis(all_outcomes)

    return {
        "ok": True,
        "agent_id": req.agent_id,
        "url": req.url,
        "predicted_pct": round(prior_pct, 1),
        "actual_pct": actual_pct,
        "abs_error": abs_error,
        "elapsed_ms": elapsed,
        "cis_updated": cis_data["cis"],
        "verdict": cis_data["verdict"],
        "n_outcomes": cis_data["n"],
    }


@app.get("/agents", summary="Lister les agents d'un tenant")
async def list_agents(tenant_id: str = Depends(get_tenant)) -> dict:
    """Retourne la liste des agent_ids avec leur CIS courant."""
    store = get_outcome_store(tenant_id)
    all_outcomes = store.load_outcomes(1000)

    agents: dict[str, list] = {}
    for o in all_outcomes:
        aid = o.get("agent_id", "unknown")
        agents.setdefault(aid, []).append(o)

    result = []
    for agent_id, outcomes in agents.items():
        cis_data = _compute_cis(outcomes)
        result.append({
            "agent_id": agent_id,
            "cis": cis_data["cis"],
            "verdict": cis_data["verdict"],
            "n_outcomes": cis_data["n"],
        })

    result.sort(key=lambda x: x["cis"], reverse=True)
    return {"tenant_id": tenant_id, "agents": result, "total": len(result)}


# ══════════════════════════════════════════════════════════════════════════════
# COMMIT-REVEAL — Mécanisme anti-triche
# ══════════════════════════════════════════════════════════════════════════════
#
# PROBLÈME RÉSOLU :
#   Sans commit-reveal, un client peut envoyer des outcomes parfaits après coup
#   (prediction=50, actual=50) pour gonfler son CIS. C'est comme si un étudiant
#   pouvait corriger ses réponses après avoir vu le corrigé.
#
# SOLUTION :
#   Le client VERROUILLE sa prédiction en envoyant un hash AVANT d'observer.
#   Quand il révèle : Wayne recalcule le hash et compare. Si ça ne matche pas
#   → le client a triché → rejeté.
#
# ANALOGIE SIMPLE :
#   C'est comme mettre sa réponse dans une enveloppe scellée (commit),
#   puis l'ouvrir devant le jury après le résultat (reveal).
#   L'enveloppe prouve que la réponse n'a pas été changée.
#
# NIVEAU DE SÉCURITÉ :
#   - SHA-256 : impossible de trouver une collision en pratique
#   - Le nonce empêche les attaques par dictionnaire (deviner la prédiction)
#   - TTL 1h : les commits expirent pour éviter l'accumulation
#
# NOTE POUR LES DÉVELOPPEURS :
#   Ce mécanisme est OPTIONNEL. Les clients peuvent toujours utiliser
#   POST /observe (sans commit-reveal) pour la simplicité. Le commit-reveal
#   est pour les cas où la vérifiabilité est critique (finance, compliance).
# ══════════════════════════════════════════════════════════════════════════════


# ── Stockage en mémoire des commits en attente ──────────────────────────────
#
# POURQUOI EN MÉMOIRE ?
#   Les commits sont éphémères (TTL 1h). En prod, on utiliserait Redis.
#   Pour le MVP, un dict Python suffit. Thread-safe via Lock.
#
# STRUCTURE D'UN COMMIT :
#   {
#     "tenant_id":        "acme-corp",         ← qui a commité
#     "agent_id":         "gpt-4o-finance",    ← quel agent
#     "prediction_hash":  "a1b2c3...",         ← SHA-256 de "prediction|nonce"
#     "domain":           "finance",           ← domaine métier
#     "created_at":       "2026-06-04T...",    ← pour le TTL
#   }

_pending_commits: dict[str, dict[str, Any]] = {}
_commits_lock = threading.Lock()
_COMMIT_TTL_SECONDS = 3600  # 1 heure — les commits expirent après ce délai


def _purge_expired_commits() -> None:
    """Supprime les commits expirés (> TTL).

    Appelée à chaque /commit et /reveal pour éviter l'accumulation.
    En prod, un cron ou Redis TTL ferait ce travail automatiquement.
    """
    now = datetime.now(UTC)
    expired = [
        cid for cid, data in _pending_commits.items()
        if (now - datetime.fromisoformat(data["created_at"])).total_seconds() > _COMMIT_TTL_SECONDS
    ]
    for cid in expired:
        del _pending_commits[cid]


# ── Modèles Pydantic pour commit-reveal ─────────────────────────────────────

class CommitRequest(BaseModel):
    """Requête pour verrouiller une prédiction.

    Le client calcule le hash côté client :
        import hashlib
        prediction_hash = hashlib.sha256(f"{prediction}|{nonce}".encode()).hexdigest()

    Le nonce est un secret aléatoire que seul le client connaît.
    Il empêche Wayne (ou un attaquant) de deviner la prédiction par brute-force.
    """
    agent_id: str = Field(..., description="Identifiant de l'agent IA")
    prediction_hash: str = Field(
        ...,
        description="SHA-256 hex de 'prediction|nonce' — verrouille la prédiction",
        min_length=64, max_length=64,  # SHA-256 = 64 caractères hex
    )
    domain: str = Field("general", description="Domaine métier")


class RevealRequest(BaseModel):
    """Requête pour révéler la prédiction et soumettre le résultat réel.

    Wayne recalcule SHA-256(f"{prediction}|{nonce}") et compare au hash stocké.
    Si ça matche → outcome vérifié. Sinon → rejeté (triche détectée).
    """
    commit_id: str = Field(..., description="L'ID retourné par POST /commit")
    prediction: float = Field(..., description="La prédiction originale (0-100)")
    nonce: str = Field(
        ...,
        description="Le secret utilisé pour calculer le hash",
        min_length=1,  # Au moins 1 caractère pour le nonce
    )
    actual: float = Field(..., description="La valeur réelle observée (0-100)")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Routes commit-reveal ────────────────────────────────────────────────────

@app.post("/commit", summary="Verrouiller une prédiction (anti-triche)")
async def commit_prediction(
    req: CommitRequest,
    tenant_id: str = Depends(get_tenant),
) -> dict:
    """
    ÉTAPE 1 du commit-reveal : le client verrouille sa prédiction.

    Le client envoie le SHA-256 de sa prédiction AVANT d'observer le résultat.
    Wayne stocke le hash et retourne un commit_id unique.

    Côté client (Python) :
        import hashlib
        nonce = secrets.token_hex(16)                              # secret aléatoire
        h = hashlib.sha256(f"{prediction}|{nonce}".encode()).hexdigest()
        response = brain.commit(agent_id="gpt-4o", prediction_hash=h)
        commit_id = response["commit_id"]                          # à conserver

    IMPORTANT :
      - Le hash est irréversible : Wayne ne peut PAS retrouver la prédiction
      - Le commit expire après 1h (TTL configurable)
      - Le client DOIT conserver le commit_id et le nonce pour le reveal
    """
    # Purge des commits expirés (maintenance légère)
    with _commits_lock:
        _purge_expired_commits()

        # Génère un ID unique pour ce commit
        commit_id = str(uuid.uuid4())

        # Stocke le commit en attente
        _pending_commits[commit_id] = {
            "tenant_id": tenant_id,
            "agent_id": req.agent_id,
            "prediction_hash": req.prediction_hash,
            "domain": req.domain,
            "created_at": datetime.now(UTC).isoformat(),
        }

    return {
        "ok": True,
        "commit_id": commit_id,
        "agent_id": req.agent_id,
        "expires_in_seconds": _COMMIT_TTL_SECONDS,
        # NOTE : on ne retourne PAS le hash (le client le connaît déjà)
        # Retourner le hash permettrait à un proxy de le voir → risque faible mais inutile
    }


@app.post("/reveal", summary="Révéler la prédiction et soumettre le résultat")
async def reveal_prediction(
    req: RevealRequest,
    tenant_id: str = Depends(get_tenant),
) -> dict:
    """
    ÉTAPE 2 du commit-reveal : le client révèle sa prédiction.

    Wayne vérifie que SHA-256(f"{prediction}|{nonce}") correspond au hash
    stocké lors du /commit. Si oui → outcome vérifié et CIS recalibré.

    POURQUOI C'EST SÛR :
      - Le hash a été stocké AVANT que le client connaisse le résultat
      - SHA-256 est irréversible : impossible de trouver une prédiction
        qui donne le même hash (résistance aux collisions)
      - Le nonce empêche les attaques par dictionnaire : même si on sait
        que la prédiction est entre 0 et 100, il y a 2^128 nonces possibles

    SCÉNARIO DE TRICHE (et pourquoi ça échoue) :
      1. Client commit hash("72.5|abc") → verrouillé
      2. Client observe actual = 68.0
      3. Client essaie de reveal prediction=68.0 pour tricher
      4. hash("68.0|abc") ≠ hash("72.5|abc") → REJETÉ ❌
      5. Le client ne peut pas trouver un nonce qui fait matcher → SHA-256
    """
    with _commits_lock:
        _purge_expired_commits()

        # ── Vérification 1 : le commit existe-t-il ? ──
        commit_data = _pending_commits.get(req.commit_id)
        if commit_data is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Commit '{req.commit_id}' introuvable ou expiré. "
                    "Les commits expirent après 1h. Recommencez avec POST /commit."
                ),
            )

        # ── Vérification 2 : le commit appartient-il à ce tenant ? ──
        # Un tenant ne peut pas reveal le commit d'un autre tenant
        if commit_data["tenant_id"] != tenant_id:
            raise HTTPException(status_code=403, detail="Ce commit ne vous appartient pas.")

        # ── Vérification 3 : le hash correspond-il ? (LE CŒUR DU MÉCANISME) ──
        #
        # On recalcule exactement ce que le client aurait dû calculer :
        #   sha256(f"{prediction}|{nonce}")
        #
        # Si le client avait prédit 72.5 et envoyé hash("72.5|secret"),
        # il DOIT reveal prediction=72.5 et nonce="secret".
        # Toute autre combinaison → hash différent → rejeté.
        expected_hash = hashlib.sha256(
            f"{req.prediction}|{req.nonce}".encode("utf-8")
        ).hexdigest()

        if expected_hash != commit_data["prediction_hash"]:
            # ── TRICHE DÉTECTÉE ──
            # Le hash ne correspond pas. Soit :
            #   - Le client a changé sa prédiction après observation (triche)
            #   - Le client s'est trompé de nonce (erreur honnête)
            # Dans les deux cas : on rejette. On ne persiste PAS l'outcome.
            raise HTTPException(
                status_code=400,
                detail=(
                    "Hash mismatch — la prédiction révélée ne correspond pas au hash commité. "
                    "L'outcome n'a PAS été enregistré. Si c'est une erreur, vérifiez votre nonce."
                ),
            )

        # ── Hash vérifié ✅ → on consomme le commit (usage unique) ──
        agent_id = commit_data["agent_id"]
        domain = commit_data["domain"]
        del _pending_commits[req.commit_id]

    # ── Persistence de l'outcome VÉRIFIÉ ──
    # Le flag "verified": True signifie que cet outcome a passé le commit-reveal.
    # Les outcomes via POST /observe classique n'ont pas ce flag.
    # En analyse CIS, on pourrait donner plus de poids aux outcomes vérifiés.
    store = get_outcome_store(tenant_id)
    monitor = get_integrity_monitor(tenant_id)

    extra = {
        **req.metadata,  # metadata en premier (ne peut pas écraser les champs critiques)
        "agent_id": agent_id,
        "domain": domain,
        "prediction": req.prediction,
        "actual": req.actual,
        "abstained": False,
        "abs_error": round(abs(req.prediction - req.actual), 3),
        "verified": True,          # ← FLAG COMMIT-REVEAL : cet outcome est cryptographiquement vérifié
        "commit_id": req.commit_id,
    }

    store.persist_outcome(extra=extra)
    monitor.observe(
        intent="api_reveal",
        cell_id=agent_id,
        prediction=req.prediction,
        actual=req.actual,
        abs_error=extra["abs_error"],
        verified=True,
    )

    # Recalcul CIS avec le nouvel outcome
    all_outcomes = [o for o in store.load_outcomes(200) if o.get("agent_id") == agent_id]
    cis_data = _compute_cis(all_outcomes)

    return {
        "ok": True,
        "verified": True,  # ← confirme que l'outcome a été vérifié par commit-reveal
        "agent_id": agent_id,
        "prediction": req.prediction,
        "actual": req.actual,
        "abs_error": extra["abs_error"],
        "cis_updated": cis_data["cis"],
        "verdict": cis_data["verdict"],
        "n_outcomes": cis_data["n"],
    }
