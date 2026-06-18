"""
ReliabilityGate — Python client
================================
An anti-gameable permission-to-act layer for autonomous agents.
Plug into any LLM in 3 lines — measure real reliability, abstain when unreliable.

Quickstart:
    from reliability_gate import ReliabilityGate, AbstentionRequired

    gate = ReliabilityGate(api_key="my-project", agent_id="gpt-4o")

    # After each LLM decision — submit the real outcome
    gate.observe(prediction=72.0, actual=68.5, domain="finance")

    # Before each decision — automatic gate
    if not gate.should_act():
        return route_to_human(task)

    # Or use the decorator — raises AbstentionRequired if unreliable
    @gate.guard()
    def call_llm(prompt: str) -> str:
        return llm.complete(prompt)

Advisory usage (no hard gating): call should_act()/cis() and log the verdict
without enforcing it, or use @gate.guard(on_abstain="log") which warns but lets
the call through. Switch to on_abstain="raise" once you trust the signal.

Requires: httpx (pip install httpx) or stdlib urllib as fallback.

Historical note: this package was prototyped internally under the codename
"Wayne Brain". The public name is ReliabilityGate; the legacy `sdk.wayne_cog`
import path and the `WayneBrain` class name remain as deprecated aliases only.
"""
from __future__ import annotations

import functools
import json
import time
from typing import Any, Callable
from urllib.parse import quote

from reliability_gate.decision import ReliabilityDecision, decide, ADVISORY

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

# ── Exceptions ────────────────────────────────────────────────────────────────

class ReliabilityGateError(Exception):
    """Base client error."""


class AbstentionRequired(ReliabilityGateError):
    """Raised by @gate.guard() when the agent should not act.

    Catch this to route the task to a human reviewer.

    Example:
        try:
            result = call_llm(prompt)
        except AbstentionRequired as e:
            route_to_human(task, cis=e.cis, reason=e.verdict)
    """
    def __init__(self, agent_id: str, cis: float, verdict: str, advice: str = "") -> None:
        self.agent_id = agent_id
        self.cis      = cis
        self.verdict  = verdict
        self.advice   = advice
        super().__init__(
            f"Agent '{agent_id}' must abstain — CIS={cis:.3f} ({verdict}). {advice}"
        )


class APIError(ReliabilityGateError):
    """ReliabilityGate API returned an error."""
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail      = detail
        super().__init__(f"ReliabilityGate API {status_code}: {detail}")


class ConnectionError(ReliabilityGateError):  # noqa: A001
    """Cannot reach the ReliabilityGate API."""


# ── CIS Result dataclass (dict-compatible) ────────────────────────────────────

class CISResult(dict):
    """CIS response with typed accessors.

    Behaves like a regular dict (JSON-serializable) but also provides
    attribute access for the most common fields.

    Example:
        result = gate.cis()
        print(result.score)       # 0.712
        print(result.verdict)     # "calibrated"
        print(result.should_act)  # True
    """

    @property
    def score(self) -> float:
        return float(self.get("cis", 0.0))

    @property
    def verdict(self) -> str:
        return str(self.get("verdict", "no_data"))

    @property
    def should_act(self) -> bool:
        return not self.get("should_abstain", True)

    @property
    def n_outcomes(self) -> int:
        return int(self.get("n_outcomes", 0))

    @property
    def advice(self) -> str:
        return str(self.get("advice", ""))

    @property
    def components(self) -> dict[str, float]:
        return self.get("components", {})

    def __repr__(self) -> str:
        return (
            f"CISResult(score={self.score:.3f}, verdict={self.verdict!r}, "
            f"n_outcomes={self.n_outcomes}, should_act={self.should_act})"
        )


# NB : `ReliabilityDecision` (verdict action-aware) est défini dans
# `reliability_gate.decision` et importé en tête de module. `CISResult` reste le
# type de réponse du score CIS — ce sont deux objets distincts.


# ── Main client ───────────────────────────────────────────────────────────────

class ReliabilityGate:
    """ReliabilityGate client — permission-to-act layer for autonomous agents.

    Args:
        api_key:  Your API key (= tenant ID in the MVP).
        agent_id: Unique identifier for this agent.
        base_url: ReliabilityGate API URL (default: http://localhost:8001).
        timeout:  HTTP timeout in seconds (default: 5s — keep low for gate calls).
        retries:  Number of retries on transient errors (default: 2).

        enforcement_mode: Default enforcement for action gating
                          ("observe" | "advisory" | "hard_gate").
                          Default "advisory" — never blocks; surfaces a
                          recommendation (observe-first friendly).

    Example:
        gate = ReliabilityGate(api_key="my-company", agent_id="gpt-4o-finance")
    """

    def __init__(
        self,
        api_key: str,
        agent_id: str,
        base_url: str = "http://localhost:8001",
        timeout: float = 5.0,
        retries: int = 2,
        enforcement_mode: str = ADVISORY,
    ) -> None:
        self.api_key  = api_key
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout
        self.retries  = retries
        self.enforcement_mode = enforcement_mode
        self._headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                return self._do_request(method, url, body)
            except (APIError, AbstentionRequired):
                raise  # ne pas retenter les erreurs métier
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(0.3 * (2 ** attempt))  # backoff exponentiel

        raise ConnectionError(f"Cannot reach ReliabilityGate API at {url}: {last_exc}") from last_exc

    def _do_request(self, method: str, url: str, body: dict | None) -> dict:
        data = json.dumps(body).encode() if body else None

        if _HAS_HTTPX:
            fn = httpx.post if method == "POST" else httpx.get
            kwargs: dict[str, Any] = {"headers": self._headers, "timeout": self.timeout}
            if method == "POST":
                kwargs["content"] = data
            resp = fn(url, **kwargs)
            if resp.status_code >= 400:
                raise APIError(resp.status_code, resp.text[:200])
            return resp.json()

        # Fallback stdlib (zero dependencies)
        import urllib.request as _urllib
        import urllib.error as _urlerr
        req = _urllib.Request(url, data=data, headers=self._headers, method=method)
        try:
            with _urllib.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except _urlerr.HTTPError as e:
            raise APIError(e.code, e.read().decode()[:200]) from e
        except OSError as e:
            raise ConnectionError(str(e)) from e

    # ── Public API ────────────────────────────────────────────────────────────

    def observe(
        self,
        prediction: float | None = None,
        actual: float | None = None,
        domain: str = "general",
        source: str = "",
        abstained: bool = False,
        action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Submit a real outcome after an agent interaction.

        Call this every time your agent makes a prediction and you later
        observe the ground truth. ReliabilityGate uses these outcomes to
        continuously recalibrate the agent's CIS.

        Args:
            prediction: Value the agent predicted (0–100 scale).
            actual:     Real observed value (0–100 scale).
            domain:     Business domain (e.g. "finance", "legal", "support").
            source:     Source identifier (URL, document ID, etc.).
            abstained:  True if the agent chose not to predict.
            action:     Action type this outcome relates to (e.g. "send_email").
                        Enables action-aware gating via should_act(action=...).
            metadata:   Any additional key-value pairs to store.

        Returns:
            Dict with updated CIS: {"cis_updated": 0.72, "verdict": "calibrated", ...}

        Example:
            gate.observe(prediction=72.0, actual=68.5, domain="finance")
            gate.observe(prediction=80.0, actual=78.0, action="send_email")
            gate.observe(abstained=True, domain="legal")
        """
        return self._request("POST", "/observe", {
            "agent_id": self.agent_id,
            "prediction": prediction,
            "actual": actual,
            "domain": domain,
            "source": source,
            "abstained": abstained,
            "action": action,
            "metadata": metadata or {},
        })

    def cis(self) -> CISResult:
        """Return the current Cognitive Integrity Score for this agent.

        Returns a CISResult with typed accessors:
            result.score      → float ∈ [0, 1]
            result.verdict    → "trusted" | "calibrated" | "learning" | "unreliable"
            result.should_act → bool (False = agent should abstain)
            result.components → {"mae_score": 0.81, "skill_score": 0.67, ...}

        Example:
            result = gate.cis()
            print(f"CIS: {result.score} ({result.verdict})")
            if not result.should_act:
                route_to_human(task)
        """
        raw = self._request("GET", f"/cis/{self.agent_id}")
        return CISResult(raw)

    def cis_for_action(self, action: str) -> CISResult:
        """Return the CIS computed over outcomes filtered to a single action type.

        Example:
            gate.cis_for_action("send_email").score
        """
        raw = self._request("GET", f"/cis/{self.agent_id}?action={quote(action, safe='')}")
        return CISResult(raw)

    def should_act(
        self,
        action: str | None = None,
        risk_level: str = "medium",
        enforcement_mode: str | None = None,
        min_cis: float | None = None,
    ) -> "bool | ReliabilityDecision":
        """Gate check — has the agent earned the right to act?

        Two modes (backward compatible):

        - **Agent-only (legacy)** — `should_act()` with no `action` returns a
          plain ``bool``: True if the agent is globally reliable enough.
        - **Action-aware** — `should_act(action="send_email", ...)` returns a
          :class:`ReliabilityDecision` (truthy iff ``allow``) that says whether
          the agent has earned the right to perform *that specific action*.

        Args:
            action:           Action type to gate (e.g. "send_email"). None →
                              legacy agent-only bool.
            risk_level:       "low" | "medium" | "customer_visible" | "high" |
                              "irreversible" | "destructive" | "financial".
                              Unknown → treated as high (fail-closed).
            enforcement_mode: "observe" | "advisory" | "hard_gate". Defaults to
                              the client's enforcement_mode ("advisory"). Only
                              "hard_gate" can return allow=False.
            min_cis:          (legacy path only) optional CIS threshold override.

        Example (action-aware):
            decision = gate.should_act(action="send_email",
                                       risk_level="customer_visible",
                                       enforcement_mode="hard_gate")
            if decision.allow:
                send_email()
            else:
                print(decision.reason)
        """
        # ── Legacy agent-only path → bool ──────────────────────────────────────
        if action is None:
            try:
                result = self.cis()
                if min_cis is not None:
                    return result.score >= min_cis
                return result.should_act
            except ConnectionError:
                return False  # fail-safe: API unreachable → do not act

        # ── Action-aware path → ReliabilityDecision ────────────────────────────
        mode = (enforcement_mode or self.enforcement_mode)
        try:
            global_cis = self.cis()
            action_cis = self.cis_for_action(action)
            cis_score = global_cis.score
            action_score = action_cis.score if action_cis.n_outcomes > 0 else None
            sample_size = action_cis.n_outcomes
        except ConnectionError:
            # Fail-safe : API injoignable → 0 preuve. En hard_gate cela bloque les
            # actions risquées (CIS 0 < seuil) ; en observe/advisory, ne bloque pas.
            cis_score, action_score, sample_size = 0.0, None, 0

        return decide(
            agent_id=self.agent_id,
            action=action,
            risk_level=risk_level,
            cis_score=cis_score,
            action_score=action_score,
            sample_size=sample_size,
            enforcement_mode=mode,
        )

    def guard(
        self,
        on_abstain: str = "raise",
        min_cis: float | None = None,
    ) -> Callable:
        """Decorator — automatically gates the function on agent reliability.

        Args:
            on_abstain: What to do when agent should abstain:
                "raise"  → raises AbstentionRequired (default — hard gate)
                "none"   → returns None silently
                "log"    → logs a warning, lets the call through (advisory mode)
            min_cis:    Optional CIS threshold override.

        Advisory usage: start with on_abstain="log" to observe the gate's
        verdicts without enforcing them; switch to "raise" once trusted.

        Example:
            @gate.guard()
            def call_llm(prompt: str) -> str:
                return openai.complete(prompt)

            # Advisory (logs but does not block):
            @gate.guard(on_abstain="log", min_cis=0.65)
            def risky_decision(data: dict) -> dict:
                ...
        """
        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                result = self.cis()
                should = result.score >= min_cis if min_cis is not None else result.should_act

                if not should:
                    if on_abstain == "raise":
                        raise AbstentionRequired(
                            agent_id=self.agent_id,
                            cis=result.score,
                            verdict=result.verdict,
                            advice=result.advice,
                        )
                    elif on_abstain == "none":
                        return None
                    elif on_abstain == "log":
                        import warnings
                        warnings.warn(
                            f"[ReliabilityGate] Agent '{self.agent_id}' is unreliable "
                            f"(CIS={result.score:.3f}, {result.verdict}) — proceeding anyway.",
                            stacklevel=2,
                        )

                return fn(*args, **kwargs)
            return wrapper
        return decorator

    def calibrate(self, url: str, domain: str = "web") -> dict:
        """Run a full real calibration cycle on a public URL.

        ReliabilityGate will:
        1. Predict extraction yield based on past history
        2. Fetch the URL (read-only, no login, no writes)
        3. Measure real extraction yield
        4. Persist outcome and return updated CIS

        Example:
            gate.calibrate("https://news.ycombinator.com", domain="tech")
        """
        return self._request("POST", "/calibrate", {
            "agent_id": self.agent_id,
            "url": url,
            "domain": domain,
        })

    # ── Commit-Reveal (anti-triche) ──────────────────────────────────────────
    #
    # QUAND UTILISER ?
    #   Utilisez commit-reveal quand la vérifiabilité est critique :
    #   finance, compliance, audit. Pour du dev/test, POST /observe suffit.
    #
    # FLOW EN 3 ÉTAPES :
    #   1. gate.commit(prediction=72.5)    → verrouille la prédiction
    #   2. ... observer le résultat réel ...
    #   3. gate.reveal(actual=68.0)        → ReliabilityGate vérifie et persiste
    #
    # RACCOURCI :
    #   gate.observe_verified(prediction=72.5, actual=68.0)
    #   → fait le commit + reveal en un seul appel (pour les cas simples)

    def commit(self, prediction: float, domain: str = "general") -> dict:
        """Lock a prediction BEFORE observing the real outcome (anti-cheat).

        Computes SHA-256(prediction|nonce) and sends the hash to ReliabilityGate.
        The server stores the hash; the prediction cannot be changed after this call.

        Args:
            prediction: The value your agent predicted (0-100 scale).
            domain:     Business domain (e.g. "finance", "legal").

        Returns:
            Dict with commit_id and nonce — you'll need both for reveal().

        Example:
            commit = gate.commit(prediction=72.5, domain="finance")
            # ... wait for the real outcome ...
            gate.reveal(commit_id=commit["commit_id"], nonce=commit["nonce"],
                        prediction=72.5, actual=68.0)
        """
        import hashlib
        import secrets

        # Génère un nonce aléatoire (32 hex chars = 128 bits d'entropie)
        # Le nonce empêche quiconque (même le serveur) de deviner la prédiction
        nonce = secrets.token_hex(16)

        # Hash la prédiction avec le nonce — c'est ce hash qui est envoyé au serveur
        # Format : sha256("72.5|a1b2c3d4e5f6...")
        prediction_hash = hashlib.sha256(
            f"{prediction}|{nonce}".encode("utf-8")
        ).hexdigest()

        result = self._request("POST", "/commit", {
            "agent_id": self.agent_id,
            "prediction_hash": prediction_hash,
            "domain": domain,
        })

        # On retourne le nonce au client pour qu'il puisse faire le reveal
        # IMPORTANT : le client DOIT conserver le nonce, le serveur ne le connaît pas
        result["nonce"] = nonce
        result["prediction"] = prediction
        return result

    def reveal(
        self,
        commit_id: str,
        prediction: float,
        nonce: str,
        actual: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Reveal a committed prediction and submit the real outcome.

        The server verifies that SHA-256(prediction|nonce) matches the stored hash.
        If it matches → verified outcome persisted. If not → rejected (cheat detected).

        Args:
            commit_id:  The ID returned by commit().
            prediction: The SAME prediction you committed (must match the hash).
            nonce:      The SAME nonce returned by commit().
            actual:     The real observed value (0-100 scale).
            metadata:   Optional additional key-value pairs.

        Returns:
            Dict with verified=True and updated CIS.

        Raises:
            APIError(400): If the hash doesn't match (cheat detected).
            APIError(404): If the commit_id is expired or invalid.
        """
        return self._request("POST", "/reveal", {
            "commit_id": commit_id,
            "prediction": prediction,
            "nonce": nonce,
            "actual": actual,
            "metadata": metadata or {},
        })

    def observe_verified(
        self,
        prediction: float,
        actual: float,
        domain: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Shortcut: commit + reveal in one call (verified outcome).

        Combines commit() and reveal() for cases where the prediction and
        actual values are both known at the same time (e.g. batch processing,
        historical data ingestion with proof).

        The outcome will be flagged as verified=True.

        Args:
            prediction: Value the agent predicted (0-100 scale).
            actual:     Real observed value (0-100 scale).
            domain:     Business domain.
            metadata:   Optional additional data.

        Example:
            # Simple — one line, cryptographically verified
            gate.observe_verified(prediction=72.5, actual=68.0, domain="finance")
        """
        commit = self.commit(prediction=prediction, domain=domain)
        return self.reveal(
            commit_id=commit["commit_id"],
            prediction=prediction,
            nonce=commit["nonce"],
            actual=actual,
            metadata=metadata,
        )

    def agents(self) -> list[dict]:
        """List all agents in your tenant with their current CIS.

        Returns:
            List of dicts: [{"agent_id": "...", "cis": 0.72, "verdict": "calibrated"}, ...]
        """
        raw = self._request("GET", "/agents")
        return raw.get("agents", [])

    def __repr__(self) -> str:
        return f"ReliabilityGate(agent_id={self.agent_id!r}, base_url={self.base_url!r})"


# ── Aliases ───────────────────────────────────────────────────────────────────
# `ReliabilityGateClient` : alias explicite pour ceux qui préfèrent un nom suffixé.
ReliabilityGateClient = ReliabilityGate

# Aliases legacy (codename interne "Wayne Brain") — dépréciés, conservés pour
# compatibilité ; les docs publiques n'utilisent que ReliabilityGate.
WayneBrain = ReliabilityGate
CognitiveLayer = ReliabilityGate
WayneBrainError = ReliabilityGateError


# ── CLI demo ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Quick demo — run with: python -m reliability_gate.client"""
    import sys

    print("ReliabilityGate — SDK demo\n" + "=" * 40)

    gate = ReliabilityGate(
        api_key="sdk-demo",
        agent_id="demo-agent",
        base_url="http://localhost:8001",
    )

    print("\n1. Submitting 10 outcomes (agent learning)...")
    scenarios = [
        (50, 20), (50, 80), (45, 55),
        (48, 52), (50, 53), (51, 52),
        (52, 53), (52, 52), (53, 53),
        (53, 54),
    ]
    for i, (pred, actual) in enumerate(scenarios, 1):
        r = gate.observe(prediction=float(pred), actual=float(actual), domain="demo")
        print(f"  [{i:2d}] pred={pred} actual={actual} → CIS={r['cis_updated']:.3f} ({r['verdict']})")

    print("\n2. Current CIS:")
    result = gate.cis()
    print(f"  {result}")
    print(f"  Should act autonomously: {result.should_act}")

    print("\n3. Testing @guard decorator...")

    @gate.guard(on_abstain="none")
    def risky_llm_call(prompt: str) -> str | None:
        return f"Response to: {prompt}"

    output = risky_llm_call("What is the market outlook?")
    if output is None:
        print("  → Agent abstained (CIS too low). Task routed to human.")
    else:
        print(f"  → Agent acted: {output!r}")

    print("\n✅ Demo complete.")
    sys.exit(0)
