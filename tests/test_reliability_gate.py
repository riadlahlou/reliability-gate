"""
ReliabilityGate — Test Suite
=========================
Run: pytest tests/ -v

Couvre :
  - CIS engine (formule, seuils, composantes)
  - Outcome store (persistence, multi-tenant, concurrence)
  - API endpoints (health, observe, cis, calibrate, agents)
  - SDK (observe, cis(), should_act, @guard, AbstentionRequired)
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path

import pytest

# Assure que les imports locaux fonctionnent depuis la racine du projet
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 1 — CIS Engine (pure Python, aucune dépendance externe)
# ══════════════════════════════════════════════════════════════════════════════

class TestCISEngine:
    """Teste la formule CIS à 4 composantes — storage/cis_engine.py"""

    from storage.cis_engine import compute_cis_from_outcomes

    def _outcomes(self, pairs: list[tuple[float, float]]) -> list[dict]:
        return [{"prediction": p, "actual": a, "abstained": False} for p, a in pairs]

    def test_no_data_returns_zero(self):
        from storage.cis_engine import compute_cis_from_outcomes
        result = compute_cis_from_outcomes([])
        assert result.cis == 0.0
        assert result.label == "no_data"
        assert result.should_abstain is True

    def test_insufficient_data_below_3(self):
        from storage.cis_engine import compute_cis_from_outcomes
        result = compute_cis_from_outcomes(self._outcomes([(50, 20), (50, 80)]))
        assert result.cis == 0.0
        assert result.label == "insufficient_data"
        assert result.should_abstain is True

    def test_perfect_predictions_high_cis(self):
        from storage.cis_engine import compute_cis_from_outcomes
        # MAE = 0 → mae_score = 1.0
        perfect = self._outcomes([(50, 50)] * 20)
        result = compute_cis_from_outcomes(perfect)
        assert result.cis >= 0.65, f"Expected calibrated+, got {result.cis}"
        assert result.label in ("calibrated", "trusted")
        assert result.mae == 0.0

    def test_terrible_predictions_low_cis(self):
        from storage.cis_engine import compute_cis_from_outcomes
        # MAE ≈ 50 (maximum possible sur échelle 0-100)
        terrible = self._outcomes([(0, 100)] * 10 + [(100, 0)] * 10)
        result = compute_cis_from_outcomes(terrible)
        assert result.cis < 0.40, f"Expected unreliable, got {result.cis}"

    def test_cis_always_in_0_1(self):
        from storage.cis_engine import compute_cis_from_outcomes
        import random
        random.seed(42)
        for _ in range(50):
            outcomes = [
                {"prediction": random.uniform(0, 100), "actual": random.uniform(0, 100), "abstained": False}
                for _ in range(random.randint(3, 30))
            ]
            result = compute_cis_from_outcomes(outcomes)
            assert 0.0 <= result.cis <= 1.0, f"CIS out of bounds: {result.cis}"

    def test_four_components_present(self):
        from storage.cis_engine import compute_cis_from_outcomes
        result = compute_cis_from_outcomes(self._outcomes([(50, 52)] * 10))
        comps = result.components
        assert "mae_score" in comps
        assert "abstention_score" in comps
        assert "skill_score" in comps
        assert "falsif_score" in comps
        for k, v in comps.items():
            assert 0.0 <= v <= 1.0, f"Component {k}={v} out of [0,1]"

    def test_four_components_sum_is_cis(self):
        from storage.cis_engine import compute_cis_from_outcomes
        result = compute_cis_from_outcomes(self._outcomes([(50, 55)] * 15))
        expected = round(
            0.40 * result.components["mae_score"]
            + 0.25 * result.components["abstention_score"]
            + 0.20 * result.components["skill_score"]
            + 0.15 * result.components["falsif_score"],
            3,
        )
        assert abs(result.cis - expected) < 0.001, f"CIS {result.cis} ≠ sum {expected}"

    def test_abstention_penalizes_reckless_never_abstainer(self):
        """Régression : un agent à forte erreur qui ne s'abstient JAMAIS doit avoir
        une mauvaise qualité d'abstention (échec d'abstention), pas ~0.7 comme avant."""
        from storage.cis_engine import compute_cis_from_outcomes
        # forte erreur (pred loin de actual), 0 abstention → imprudent
        reckless = [{"prediction": 90.0, "actual": 20.0, "abstained": False}] * 12
        abst = compute_cis_from_outcomes(reckless).components["abstention_score"]
        assert abst < 0.4, f"abstention reckless={abst} doit être basse (était ~0.7)"

    def test_abstention_rewards_reliable_actor(self):
        """Un agent fiable (faible erreur sur ce qu'il agit) a une bonne abstention."""
        from storage.cis_engine import compute_cis_from_outcomes
        reliable = [{"prediction": 50.0, "actual": 51.0, "abstained": False}] * 12
        abst = compute_cis_from_outcomes(reliable).components["abstention_score"]
        assert abst > 0.5, f"abstention fiable={abst} doit être élevée"

    def test_abstention_discriminates(self):
        """La composante abstention doit DIFFÉRENCIER fiable vs imprudent (pas constante)."""
        from storage.cis_engine import compute_cis_from_outcomes
        reliable = compute_cis_from_outcomes(
            [{"prediction": 50.0, "actual": 51.0, "abstained": False}] * 12
        ).components["abstention_score"]
        reckless = compute_cis_from_outcomes(
            [{"prediction": 90.0, "actual": 20.0, "abstained": False}] * 12
        ).components["abstention_score"]
        assert reliable - reckless > 0.3, f"abstention non discriminante: {reliable} vs {reckless}"

    def test_labels_match_thresholds(self):
        from storage.cis_engine import compute_cis_from_outcomes, _CIS_TRUSTED, _CIS_CALIBRATED, _CIS_LEARNING
        # Agent précis → should reach calibrated or trusted
        good = self._outcomes([(50, 51)] * 30)
        r = compute_cis_from_outcomes(good)
        if r.cis >= _CIS_TRUSTED:
            assert r.label == "trusted"
        elif r.cis >= _CIS_CALIBRATED:
            assert r.label == "calibrated"
        elif r.cis >= _CIS_LEARNING:
            assert r.label == "learning"
        else:
            assert r.label == "unreliable"

    def test_forecast_skill_positive_when_beating_baseline(self):
        from storage.cis_engine import compute_cis_from_outcomes
        # Serie stable : persistence = 0 erreur. Agent légèrement imprécis → skill peut être négatif
        # Serie variable : agent précis → skill positif
        variable = self._outcomes([(i * 3, i * 3 + 1) for i in range(20)])
        result = compute_cis_from_outcomes(variable)
        assert result.forecast_skill is not None

    def test_abstention_outcomes_counted(self):
        from storage.cis_engine import compute_cis_from_outcomes
        outcomes = [{"prediction": None, "actual": None, "abstained": True}] * 5
        outcomes += [{"prediction": 50.0, "actual": 52.0, "abstained": False}] * 10
        result = compute_cis_from_outcomes(outcomes)
        assert result.abstention_rate > 0
        assert result.n == 10  # seuls les non-abstentions comptent dans MAE


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 2 — Outcome Store (persistence)
# ══════════════════════════════════════════════════════════════════════════════

class TestOutcomeStore:
    """Teste la persistence JSONL — storage/outcome_store.py"""

    def _make_store(self, tmp_path: Path):
        """Crée un store isolé dans un répertoire temporaire."""
        import os
        from storage.outcome_store import OutcomeStore
        store_dir = tmp_path / "test_tenant"
        store_dir.mkdir()
        # Patch DATA_ROOT en créant le store directement
        store = OutcomeStore.__new__(OutcomeStore)
        store.tenant_id = "test"
        store._dir = store_dir
        store._path = store_dir / "outcomes.jsonl"
        import threading
        store._lock = threading.Lock()
        return store

    def test_persist_and_load(self, tmp_path):
        store = self._make_store(tmp_path)
        store.persist_outcome(extra={"agent_id": "a1", "prediction": 50.0, "actual": 52.0})
        store.persist_outcome(extra={"agent_id": "a1", "prediction": 48.0, "actual": 50.0})
        loaded = store.load_outcomes()
        assert len(loaded) == 2
        assert loaded[0]["agent_id"] == "a1"
        assert loaded[1]["prediction"] == 48.0

    def test_file_is_valid_jsonl(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(5):
            store.persist_outcome(extra={"i": i})
        lines = store._path.read_text().splitlines()
        assert len(lines) == 5
        for line in lines:
            json.loads(line)  # must not raise

    def test_concurrent_writes_no_corruption(self, tmp_path):
        """10 threads écrivent simultanément — aucune corruption."""
        store = self._make_store(tmp_path)
        errors = []

        def write_100():
            try:
                for j in range(10):
                    store.persist_outcome(extra={"thread": threading.current_thread().name, "j": j})
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_100) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent write errors: {errors}"
        lines = store._path.read_text().splitlines()
        assert len(lines) == 100
        for line in lines:
            json.loads(line)  # aucune ligne corrompue

    def test_cold_restart_preserves_data(self, tmp_path):
        """Simule un restart : réinstancie le store, vérifie que les données sont là."""
        from storage.outcome_store import OutcomeStore
        import threading

        # Écriture
        store1 = OutcomeStore.__new__(OutcomeStore)
        store1.tenant_id = "cold"
        store1._dir = tmp_path
        store1._path = tmp_path / "outcomes.jsonl"
        store1._lock = threading.Lock()
        for i in range(5):
            store1.persist_outcome(extra={"prediction": float(i), "actual": float(i + 1)})

        # "Restart" — nouvelle instance, même path
        store2 = OutcomeStore.__new__(OutcomeStore)
        store2.tenant_id = "cold"
        store2._dir = tmp_path
        store2._path = tmp_path / "outcomes.jsonl"
        store2._lock = threading.Lock()
        loaded = store2.load_outcomes()
        assert len(loaded) == 5, f"Expected 5 outcomes after cold restart, got {len(loaded)}"

    def test_count(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.count() == 0
        for _ in range(7):
            store.persist_outcome(extra={})
        assert store.count() == 7


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 3 — API (integration tests — requires running API on :8001)
# ══════════════════════════════════════════════════════════════════════════════

import socket

def _api_available() -> bool:
    try:
        s = socket.create_connection(("localhost", 8001), timeout=1)
        s.close()
        return True
    except OSError:
        return False

requires_api = pytest.mark.skipif(
    not _api_available(),
    reason="ReliabilityGate API not running on localhost:8001 — start with ./start.sh"
)


@requires_api
class TestAPI:
    """Integration tests against a running API instance."""

    BASE = "http://localhost:8001"
    KEY  = "pytest-suite"

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        import urllib.request, urllib.error
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{self.BASE}{path}", data=data,
            headers={"Content-Type": "application/json", "X-API-Key": self.KEY},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise AssertionError(f"API {method} {path} → {e.code}: {e.read().decode()[:200]}")

    def test_health(self):
        r = self._call("GET", "/health")
        assert r["status"] == "ready"
        assert "service" in r

    def test_observe_increments_n(self):
        agent = "pytest-observe-counter"
        # Submit 3 outcomes
        for p, a in [(50.0, 52.0), (48.0, 50.0), (51.0, 51.5)]:
            r = self._call("POST", "/observe", {
                "agent_id": agent, "prediction": p, "actual": a
            })
            assert r["ok"] is True
            assert "cis_updated" in r

        cis = self._call("GET", f"/cis/{agent}")
        assert cis["n_outcomes"] >= 3

    def test_cis_response_has_required_fields(self):
        agent = "pytest-cis-fields"
        for p, a in [(50.0, 52.0), (49.0, 51.0), (51.0, 50.0)]:
            self._call("POST", "/observe", {"agent_id": agent, "prediction": p, "actual": a})

        cis = self._call("GET", f"/cis/{agent}")
        for field in ("cis", "verdict", "should_abstain", "n_outcomes", "advice", "last_updated"):
            assert field in cis, f"Missing field: {field}"
        assert 0.0 <= cis["cis"] <= 1.0
        assert cis["verdict"] in ("trusted", "calibrated", "learning", "unreliable", "insufficient_data", "no_data")
        assert isinstance(cis["should_abstain"], bool)

    def test_no_data_verdict(self):
        agent = f"pytest-nodata-{__import__('time').time_ns()}"
        cis = self._call("GET", f"/cis/{agent}")
        assert cis["verdict"] in ("no_data", "insufficient_data")
        assert cis["should_abstain"] is True

    def test_agents_list(self):
        r = self._call("GET", "/agents")
        assert "agents" in r
        assert isinstance(r["agents"], list)
        assert "total" in r

    def test_tenant_isolation(self):
        """Data from one tenant must not be visible in another."""
        import urllib.request
        agent = f"shared-{__import__('time').time_ns()}"

        # Write under KEY
        self._call("POST", "/observe", {"agent_id": agent, "prediction": 50.0, "actual": 20.0})
        self._call("POST", "/observe", {"agent_id": agent, "prediction": 50.0, "actual": 80.0})
        self._call("POST", "/observe", {"agent_id": agent, "prediction": 50.0, "actual": 50.0})

        # Read under different key
        other_key = "pytest-other-tenant-xyz"
        req = urllib.request.Request(
            f"{self.BASE}/cis/{agent}",
            headers={"Content-Type": "application/json", "X-API-Key": other_key},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            cis = json.loads(r.read())
        assert cis["verdict"] in ("no_data", "insufficient_data"), \
            f"Tenant isolation broken: {cis['verdict']}"


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 4 — SDK (unit tests with mock, no API required)
# ══════════════════════════════════════════════════════════════════════════════

class TestSDK:
    """Teste le client ReliabilityGate — reliability_gate/client.py"""

    def _make_brain(self, responses: dict[str, dict]) -> "ReliabilityGate":
        """Crée un ReliabilityGate avec un transport mocké."""
        from reliability_gate import ReliabilityGate

        class MockBrain(ReliabilityGate):
            def _do_request(self, method, url, body):
                path = url.replace("http://mock:8001", "")
                if path in responses:
                    return responses[path]
                raise AssertionError(f"Unexpected call: {method} {path}")

        return MockBrain(api_key="test", agent_id="test-agent", base_url="http://mock:8001")

    def test_observe_returns_dict(self):
        brain = self._make_brain({
            "/observe": {"ok": True, "cis_updated": 0.5, "verdict": "learning", "n_outcomes": 5}
        })
        r = brain.observe(prediction=50.0, actual=52.0)
        assert r["ok"] is True

    def test_cis_returns_cisresult(self):
        from reliability_gate import CISResult
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.72, "verdict": "calibrated",
                "should_abstain": False, "n_outcomes": 20,
                "advice": "Calibrated.", "last_updated": "2026-06-04T00:00:00Z"
            }
        })
        result = brain.cis()
        assert isinstance(result, CISResult)
        assert result.score == 0.72
        assert result.verdict == "calibrated"
        assert result.should_act is True

    def test_should_act_true_when_calibrated(self):
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.72, "verdict": "calibrated",
                "should_abstain": False, "n_outcomes": 20,
                "advice": "", "last_updated": ""
            }
        })
        assert brain.should_act() is True

    def test_should_act_false_when_unreliable(self):
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.25, "verdict": "unreliable",
                "should_abstain": True, "n_outcomes": 5,
                "advice": "", "last_updated": ""
            }
        })
        assert brain.should_act() is False

    def test_guard_raises_abstention_required(self):
        from reliability_gate import AbstentionRequired
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.25, "verdict": "unreliable",
                "should_abstain": True, "n_outcomes": 5,
                "advice": "Abstain.", "last_updated": ""
            }
        })

        @brain.guard(on_abstain="raise")
        def risky_fn():
            return "should not reach here"

        with pytest.raises(AbstentionRequired) as exc_info:
            risky_fn()
        assert exc_info.value.cis == 0.25
        assert exc_info.value.verdict == "unreliable"

    def test_guard_returns_none_on_abstain_none(self):
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.25, "verdict": "unreliable",
                "should_abstain": True, "n_outcomes": 5,
                "advice": "", "last_updated": ""
            }
        })

        @brain.guard(on_abstain="none")
        def fn():
            return "result"

        assert fn() is None

    def test_guard_lets_through_when_calibrated(self):
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.72, "verdict": "calibrated",
                "should_abstain": False, "n_outcomes": 20,
                "advice": "", "last_updated": ""
            }
        })

        @brain.guard()
        def fn():
            return "result"

        assert fn() == "result"

    def test_guard_with_min_cis_override(self):
        from reliability_gate import AbstentionRequired
        brain = self._make_brain({
            "/cis/test-agent": {
                "cis": 0.60, "verdict": "learning",
                "should_abstain": False, "n_outcomes": 10,
                "advice": "", "last_updated": ""
            }
        })

        # 0.60 is above default (should_abstain=False) but below min_cis=0.65
        @brain.guard(on_abstain="raise", min_cis=0.65)
        def strict_fn():
            return "result"

        with pytest.raises(AbstentionRequired):
            strict_fn()

    def test_connection_error_returns_false_for_should_act(self):
        from reliability_gate import ReliabilityGate, ConnectionError as WBConnError

        class FailingBrain(ReliabilityGate):
            def _do_request(self, method, url, body):
                raise OSError("Connection refused")

        brain = FailingBrain(api_key="k", agent_id="a", base_url="http://dead:9999", retries=0)
        # should_act returns False on connection error (fail-safe)
        assert brain.should_act() is False

    def test_cisresult_repr(self):
        from reliability_gate import CISResult
        r = CISResult({"cis": 0.72, "verdict": "calibrated", "should_abstain": False, "n_outcomes": 20, "advice": ""})
        assert "0.720" in repr(r)
        assert "calibrated" in repr(r)


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 4bis — Public API naming & legacy compat (no API required)
# ══════════════════════════════════════════════════════════════════════════════

class TestPublicNaming:
    """Vérifie que l'import public propre fonctionne et que le shim legacy
    `sdk` reste utilisable (déprécié) — couvre le rename Wayne Brain → ReliabilityGate."""

    def test_public_import_surface(self):
        import reliability_gate as rg
        # Surface publique attendue
        assert hasattr(rg, "ReliabilityGate")
        assert hasattr(rg, "ReliabilityGateClient")
        assert hasattr(rg, "AbstentionRequired")
        assert hasattr(rg, "APIError")
        assert hasattr(rg, "ReliabilityGateError")
        assert hasattr(rg, "ReliabilityDecision")
        assert rg.ReliabilityGateClient is rg.ReliabilityGate
        # ReliabilityDecision (verdict action-aware) est DISTINCT de CISResult (réponse CIS).
        assert rg.ReliabilityDecision is not rg.CISResult
        for f in ("allow", "mode", "reason", "recommendation", "sample_size", "required_sample_size"):
            assert f in rg.ReliabilityDecision.__dataclass_fields__

    def test_abstention_inherits_base_error(self):
        from reliability_gate import AbstentionRequired, ReliabilityGateError
        assert issubclass(AbstentionRequired, ReliabilityGateError)

    def test_legacy_sdk_shim_still_works_but_warns(self):
        import warnings
        import importlib
        import sys
        # Force un import frais du shim pour observer le DeprecationWarning
        for mod in ("sdk", "sdk.wayne_cog"):
            sys.modules.pop(mod, None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mod = importlib.import_module("sdk.wayne_cog")
        # Le shim ré-exporte bien la classe canonique
        from reliability_gate import ReliabilityGate
        assert mod.WayneBrain is ReliabilityGate
        assert any(issubclass(w.category, DeprecationWarning) for w in caught), \
            "Le shim sdk.wayne_cog doit émettre un DeprecationWarning"

    def test_legacy_class_aliases_point_to_new_class(self):
        from reliability_gate import ReliabilityGate, WayneBrain, CognitiveLayer
        assert WayneBrain is ReliabilityGate
        assert CognitiveLayer is ReliabilityGate


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 4ter — Action-aware gating (decide() pur, sans serveur)
# ══════════════════════════════════════════════════════════════════════════════

class TestDecidePure:
    """Teste la logique PURE decide() — permission-to-act par action.

    Aucun serveur requis : on injecte directement (cis_score, action_score,
    sample_size, risk_level, enforcement_mode).
    """

    def _d(self, **kw):
        from reliability_gate.decision import decide
        base = dict(
            agent_id="a", action="send_email", risk_level="customer_visible",
            cis_score=0.80, action_score=0.80, sample_size=15,
            enforcement_mode="hard_gate",
        )
        base.update(kw)
        return decide(**base)

    def test_returns_reliability_decision(self):
        from reliability_gate import ReliabilityDecision
        d = self._d()
        assert isinstance(d, ReliabilityDecision)
        for f in ("allow", "mode", "reason", "agent_id", "action", "risk_level",
                  "cis_score", "action_score", "sample_size", "required_sample_size",
                  "recommendation", "enforcement_mode"):
            assert hasattr(d, f)

    def test_observe_mode_never_blocks(self):
        # Même un agent catastrophique sur une action risquée → jamais bloqué en observe.
        d = self._d(cis_score=0.02, action_score=0.02, sample_size=30,
                    enforcement_mode="observe")
        assert d.allow is True
        assert d.mode == "OBSERVE_ONLY"
        # mais la recommandation reste honnête (block)
        assert d.recommendation == "block"

    def test_advisory_mode_recommends_without_blocking(self):
        d = self._d(cis_score=0.02, action_score=0.02, sample_size=30,
                    enforcement_mode="advisory")
        assert d.allow is True
        assert d.mode == "ADVISORY"
        assert d.recommendation == "block"

    def test_hard_gate_blocks_when_score_insufficient(self):
        # action prouvée non fiable (assez d'échantillons mais score faible) + agent faible
        d = self._d(cis_score=0.05, action_score=0.10, sample_size=30,
                    enforcement_mode="hard_gate")
        assert d.allow is False
        assert d.mode == "HARD_BLOCK"

    def test_insufficient_action_outcomes_reason(self):
        d = self._d(cis_score=0.80, action_score=None, sample_size=2,
                    enforcement_mode="advisory")
        assert "not enough action-specific outcomes" in d.reason
        assert d.recommendation == "gather_more_data"
        assert d.required_sample_size == 10  # customer_visible

    def test_globally_reliable_but_action_unproven_does_not_claim(self):
        # Agent globalement fiable, mais action pas assez échantillonnée :
        # en advisory → ADVISORY, allow=True, MAIS pas un ALLOW prouvé (recommande gather).
        d = self._d(cis_score=0.88, action_score=None, sample_size=1,
                    enforcement_mode="advisory")
        assert d.mode == "ADVISORY"
        assert d.allow is True
        assert d.recommendation == "gather_more_data"   # pas "allow" → aucune fausse fiabilité
        # en hard_gate, action risquée non prouvée → SOFT_BLOCK (précaution), pas ALLOW
        d2 = self._d(cis_score=0.88, action_score=None, sample_size=1,
                     enforcement_mode="hard_gate")
        assert d2.mode == "SOFT_BLOCK"
        assert d2.allow is False

    def test_weak_agent_risky_action_blocks(self):
        # liar-like : CIS global bas + action risquée → HARD_BLOCK en hard_gate
        d = self._d(cis_score=0.04, action_score=0.04, sample_size=30,
                    risk_level="customer_visible", enforcement_mode="hard_gate")
        assert d.allow is False
        assert d.mode == "HARD_BLOCK"

    def test_proven_action_allows(self):
        d = self._d(cis_score=0.84, action_score=0.82, sample_size=15,
                    enforcement_mode="hard_gate")
        assert d.allow is True
        assert d.mode == "ALLOW"
        assert d.recommendation == "allow"

    def test_low_risk_missing_data_does_not_block_hard_gate(self):
        # action peu risquée + données manquantes → on ne bloque pas même en hard_gate
        d = self._d(risk_level="low", cis_score=0.88, action_score=None,
                    sample_size=0, enforcement_mode="hard_gate")
        assert d.allow is True
        assert d.mode == "ALLOW"
        assert d.required_sample_size == 3

    def test_unknown_risk_is_fail_closed(self):
        from reliability_gate.decision import required_sample_size, is_risky
        assert is_risky("totally_unknown_risk") is True
        assert required_sample_size("totally_unknown_risk") == 20

    def test_destructive_stricter_than_low(self):
        from reliability_gate.decision import required_sample_size
        # plus le risque est élevé, plus le seuil d'échantillons est strict
        assert required_sample_size("destructive") > required_sample_size("low")
        assert required_sample_size("financial") > required_sample_size("normal")
        assert required_sample_size("normal") >= required_sample_size("low")

    def test_allow_vs_recommended_allow_semantics(self):
        # Cœur de la clarté API : en advisory, un agent dangereux donne
        # allow=True (NON enforced) MAIS recommended_allow=False (avis réel du gate).
        d = self._d(cis_score=0.02, action_score=0.02, sample_size=30,
                    risk_level="customer_visible", enforcement_mode="advisory")
        assert d.allow is True              # effective (non bloqué en advisory)
        assert d.enforced_allow is d.allow  # alias explicite
        assert d.recommended_allow is False  # le gate, lui, recommande de NE PAS agir
        assert d.recommendation == "block"

        # En observe : idem, allow=True mais recommended_allow=False.
        d_obs = self._d(cis_score=0.02, action_score=0.02, sample_size=30,
                        risk_level="customer_visible", enforcement_mode="observe")
        assert d_obs.allow is True and d_obs.recommended_allow is False

        # En hard_gate : allow suit le verdict → False, recommended_allow=False aussi.
        d_hard = self._d(cis_score=0.02, action_score=0.02, sample_size=30,
                         risk_level="customer_visible", enforcement_mode="hard_gate")
        assert d_hard.allow is False and d_hard.recommended_allow is False

        # Action prouvée : recommended_allow ET allow True.
        d_ok = self._d(cis_score=0.84, action_score=0.82, sample_size=15,
                       enforcement_mode="hard_gate")
        assert d_ok.allow is True and d_ok.recommended_allow is True

        # Données insuffisantes : recommended_allow=False (pas "safe"), même si allow=True en advisory.
        d_insuf = self._d(cis_score=0.88, action_score=None, sample_size=1,
                          enforcement_mode="advisory")
        assert d_insuf.allow is True and d_insuf.recommended_allow is False

    def test_advisory_never_raises(self):
        # advisory ne doit jamais lever d'exception, même sur un cas de blocage net
        try:
            d = self._d(cis_score=0.01, action_score=0.01, sample_size=30,
                        risk_level="destructive", enforcement_mode="advisory")
        except Exception as exc:  # noqa: BLE001
            assert False, f"advisory ne doit pas lever : {exc}"
        assert d.allow is True            # advisory ne bloque jamais
        assert d.recommendation == "block"  # mais recommande honnêtement le blocage

    def test_reason_is_human_readable(self):
        d = self._d(cis_score=0.04, sample_size=30, enforcement_mode="hard_gate")
        assert isinstance(d.reason, str) and len(d.reason) > 10

    def test_decision_is_truthy_iff_allow(self):
        allow_d = self._d(cis_score=0.84, action_score=0.82, sample_size=15,
                          enforcement_mode="hard_gate")
        block_d = self._d(cis_score=0.04, action_score=0.04, sample_size=30,
                          enforcement_mode="hard_gate")
        assert bool(allow_d) is True
        assert bool(block_d) is False


class TestShouldActWiring:
    """Teste le câblage client should_act(action=...) avec transport mocké."""

    def _gate(self, global_payload, action_payload, **kw):
        from reliability_gate import ReliabilityGate

        class MockGate(ReliabilityGate):
            def _do_request(self, method, url, body):
                # branche selon présence du filtre ?action= dans l'URL
                if "action=" in url:
                    return action_payload
                if "/cis/" in url:
                    return global_payload
                raise AssertionError(f"Unexpected call: {method} {url}")

        return MockGate(api_key="t", agent_id="ag", base_url="http://mock", **kw)

    def test_agent_only_should_act_returns_bool(self):
        # compat legacy : pas d'action → bool
        g = self._gate(
            {"cis": 0.72, "verdict": "calibrated", "should_abstain": False, "n_outcomes": 20},
            {},
        )
        r = g.should_act()
        assert r is True and isinstance(r, bool)

    def test_action_aware_returns_decision_block(self):
        from reliability_gate import ReliabilityDecision
        g = self._gate(
            {"cis": 0.04, "verdict": "unreliable", "should_abstain": True, "n_outcomes": 20},
            {"cis": 0.04, "verdict": "unreliable", "should_abstain": True, "n_outcomes": 20},
        )
        d = g.should_act(action="send_email", risk_level="customer_visible",
                         enforcement_mode="hard_gate")
        assert isinstance(d, ReliabilityDecision)
        assert d.allow is False
        assert d.mode == "HARD_BLOCK"
        assert d.action == "send_email"

    def test_action_aware_returns_decision_allow(self):
        g = self._gate(
            {"cis": 0.84, "verdict": "trusted", "should_abstain": False, "n_outcomes": 20},
            {"cis": 0.82, "verdict": "trusted", "should_abstain": False, "n_outcomes": 15},
        )
        d = g.should_act(action="send_email", risk_level="customer_visible",
                         enforcement_mode="hard_gate")
        assert d.allow is True
        assert d.mode == "ALLOW"

    def test_client_default_enforcement_is_advisory(self):
        g = self._gate(
            {"cis": 0.02, "verdict": "unreliable", "should_abstain": True, "n_outcomes": 20},
            {"cis": 0.02, "verdict": "unreliable", "should_abstain": True, "n_outcomes": 20},
        )
        d = g.should_act(action="send_email", risk_level="customer_visible")
        # défaut client = advisory → ne bloque pas
        assert d.allow is True
        assert d.mode == "ADVISORY"

    def test_insufficient_action_samples_wiring(self):
        g = self._gate(
            {"cis": 0.84, "verdict": "trusted", "should_abstain": False, "n_outcomes": 20},
            {"cis": 0.0, "verdict": "insufficient_data", "should_abstain": True, "n_outcomes": 2},
        )
        d = g.should_act(action="send_email", risk_level="customer_visible",
                         enforcement_mode="advisory")
        assert "not enough action-specific outcomes" in d.reason
        assert d.sample_size == 2


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 5 — SDK Integration (requires running API)
# ══════════════════════════════════════════════════════════════════════════════

@requires_api
class TestSDKIntegration:
    """SDK integration tests against live API."""

    def _brain(self, agent_suffix: str = "") -> "ReliabilityGate":
        from reliability_gate import ReliabilityGate
        return ReliabilityGate(
            api_key="pytest-sdk-integration",
            agent_id=f"sdk-test-agent{agent_suffix}",
            base_url="http://localhost:8001",
        )

    def test_observe_and_cis_roundtrip(self):
        brain = self._brain("-roundtrip")
        for p, a in [(50.0, 52.0), (49.0, 51.0), (51.0, 50.5)]:
            brain.observe(prediction=p, actual=a, domain="test")
        result = brain.cis()
        assert result.score >= 0.0
        assert result.verdict in ("trusted", "calibrated", "learning", "unreliable", "insufficient_data", "no_data")

    def test_guard_decorator_live(self):
        from reliability_gate import AbstentionRequired
        brain = self._brain("-guard-live")

        @brain.guard(on_abstain="none")
        def call() -> str | None:
            return "ok"

        # Avec 0 données, should_abstain=True → retourne None
        result = call()
        assert result is None  # pas assez de données → abstention

    def test_should_act_false_with_no_data(self):
        brain = self._brain(f"-nodata-{__import__('time').time_ns()}")
        assert brain.should_act() is False


# ══════════════════════════════════════════════════════════════════════════════
# BLOC 6 — Commit-Reveal (anti-triche)
# ══════════════════════════════════════════════════════════════════════════════

class TestCommitReveal:
    """Tests unitaires du mécanisme commit-reveal — purs, sans serveur."""

    def test_commit_reveal_honest(self):
        """Un client honnête : commit puis reveal avec la vraie prédiction → accepté."""
        import hashlib, secrets
        from api.main import _pending_commits, _commits_lock, _COMMIT_TTL_SECONDS

        nonce = secrets.token_hex(16)
        prediction = 72.5
        prediction_hash = hashlib.sha256(f"{prediction}|{nonce}".encode()).hexdigest()

        # Vérification : le hash recalculé doit matcher
        expected = hashlib.sha256(f"{prediction}|{nonce}".encode()).hexdigest()
        assert prediction_hash == expected, "Hash doit être déterministe"

    def test_commit_reveal_cheat_detected(self):
        """Un client tricheur change sa prédiction → hash mismatch."""
        import hashlib, secrets

        nonce = secrets.token_hex(16)
        real_prediction = 72.5
        cheated_prediction = 68.0  # le client essaie de mettre la valeur réelle

        real_hash = hashlib.sha256(f"{real_prediction}|{nonce}".encode()).hexdigest()
        cheat_hash = hashlib.sha256(f"{cheated_prediction}|{nonce}".encode()).hexdigest()

        assert real_hash != cheat_hash, "Les hash doivent être différents → triche détectée"

    def test_nonce_prevents_guessing(self):
        """Deux commits avec la même prédiction mais des nonces différents → hash différents."""
        import hashlib, secrets

        prediction = 50.0
        nonce1 = secrets.token_hex(16)
        nonce2 = secrets.token_hex(16)

        h1 = hashlib.sha256(f"{prediction}|{nonce1}".encode()).hexdigest()
        h2 = hashlib.sha256(f"{prediction}|{nonce2}".encode()).hexdigest()

        assert h1 != h2, "Le nonce doit rendre chaque hash unique"

    def test_hash_is_64_hex_chars(self):
        """SHA-256 produit exactement 64 caractères hexadécimaux."""
        import hashlib
        h = hashlib.sha256(b"test|nonce").hexdigest()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


@requires_api
class TestCommitRevealAPI:
    """Tests d'intégration commit-reveal contre l'API live."""

    BASE = "http://localhost:8001"
    KEY = "pytest-commit-reveal"

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        import urllib.request, urllib.error
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{self.BASE}{path}", data=data,
            headers={"Content-Type": "application/json", "X-API-Key": self.KEY},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise AssertionError(f"API {method} {path} → {e.code}: {e.read().decode()[:200]}")

    def test_commit_then_reveal_honest(self):
        """Flow complet honnête via API."""
        import hashlib, secrets

        prediction = 65.0
        nonce = secrets.token_hex(16)
        prediction_hash = hashlib.sha256(f"{prediction}|{nonce}".encode()).hexdigest()

        # Étape 1 : Commit
        commit_r = self._call("POST", "/commit", {
            "agent_id": "pytest-cr-honest",
            "prediction_hash": prediction_hash,
        })
        assert commit_r["ok"] is True
        assert "commit_id" in commit_r

        # Étape 2 : Reveal avec la bonne prédiction
        reveal_r = self._call("POST", "/reveal", {
            "commit_id": commit_r["commit_id"],
            "prediction": prediction,
            "nonce": nonce,
            "actual": 60.0,
        })
        assert reveal_r["ok"] is True
        assert reveal_r["verified"] is True
        assert reveal_r["abs_error"] == 5.0

    def test_commit_then_reveal_cheat_rejected(self):
        """Triche détectée : le client change sa prédiction après commit."""
        import hashlib, secrets, urllib.request, urllib.error

        nonce = secrets.token_hex(16)
        real_prediction = 72.5
        prediction_hash = hashlib.sha256(f"{real_prediction}|{nonce}".encode()).hexdigest()

        # Commit
        commit_r = self._call("POST", "/commit", {
            "agent_id": "pytest-cr-cheat",
            "prediction_hash": prediction_hash,
        })

        # Reveal avec une FAUSSE prédiction
        data = json.dumps({
            "commit_id": commit_r["commit_id"],
            "prediction": 60.0,  # ← triche
            "nonce": nonce,
            "actual": 60.0,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE}/reveal", data=data,
            headers={"Content-Type": "application/json", "X-API-Key": self.KEY},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            assert False, "Should have returned 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = e.read().decode()
            assert "mismatch" in body.lower()

    def test_reveal_unknown_commit_rejected(self):
        """Reveal avec un commit_id inexistant → 404."""
        import urllib.request, urllib.error

        data = json.dumps({
            "commit_id": "non-existent-id",
            "prediction": 50.0,
            "nonce": "abc",
            "actual": 50.0,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE}/reveal", data=data,
            headers={"Content-Type": "application/json", "X-API-Key": self.KEY},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            assert False, "Should have returned 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_commit_single_use(self):
        """Un commit ne peut être reveal qu'une seule fois."""
        import hashlib, secrets, urllib.request, urllib.error

        nonce = secrets.token_hex(16)
        prediction = 50.0
        prediction_hash = hashlib.sha256(f"{prediction}|{nonce}".encode()).hexdigest()

        commit_r = self._call("POST", "/commit", {
            "agent_id": "pytest-cr-single-use",
            "prediction_hash": prediction_hash,
        })

        # Premier reveal → OK
        self._call("POST", "/reveal", {
            "commit_id": commit_r["commit_id"],
            "prediction": prediction,
            "nonce": nonce,
            "actual": 48.0,
        })

        # Deuxième reveal avec le même commit_id → 404 (consommé)
        data = json.dumps({
            "commit_id": commit_r["commit_id"],
            "prediction": prediction,
            "nonce": nonce,
            "actual": 48.0,
        }).encode()
        req = urllib.request.Request(
            f"{self.BASE}/reveal", data=data,
            headers={"Content-Type": "application/json", "X-API-Key": self.KEY},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            assert False, "Should have returned 404 (commit already consumed)"
        except urllib.error.HTTPError as e:
            assert e.code == 404


@requires_api
class TestSDKCommitReveal:
    """Tests SDK commit-reveal contre l'API live."""

    def _brain(self, suffix: str = "") -> "ReliabilityGate":
        from reliability_gate import ReliabilityGate
        return ReliabilityGate(
            api_key="pytest-sdk-cr",
            agent_id=f"sdk-cr-agent{suffix}",
            base_url="http://localhost:8001",
        )

    def test_sdk_observe_verified(self):
        """SDK observe_verified fait commit+reveal en un appel."""
        brain = self._brain("-verified")
        result = brain.observe_verified(prediction=55.0, actual=58.0, domain="test")
        assert result["verified"] is True
        assert result["abs_error"] == 3.0

    def test_sdk_commit_then_reveal(self):
        """SDK commit puis reveal manuellement."""
        brain = self._brain("-manual")
        commit = brain.commit(prediction=72.5, domain="finance")
        assert "commit_id" in commit
        assert "nonce" in commit

        result = brain.reveal(
            commit_id=commit["commit_id"],
            prediction=72.5,
            nonce=commit["nonce"],
            actual=68.0,
        )
        assert result["verified"] is True
