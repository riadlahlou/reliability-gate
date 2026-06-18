<!-- Badges -->
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)
![API Port](https://img.shields.io/badge/API-port%208001-orange)

# ReliabilityGate

> **An anti-gameable permission-to-act layer for autonomous agents** — it stops an agent from acting when its *measured* reliability isn't high enough. Not an observability dashboard, not a hallucination detector: a decision gate.

> **Upgrade ordinary agents into Wayne Agents** — agents that aren't trusted by default and must *prove* reliability before they act.

<sub>(Prototyped internally under the codename **Wayne Brain**. The public name is ReliabilityGate; legacy import paths remain only as deprecated aliases.)</sub>

### Your AI agent is confident. But is it *right*?

Every LLM answers with the same unwavering confidence — whether it has zero context or ten thousand examples. It doesn't know what it doesn't know. And it will **never tell you**.

ReliabilityGate fixes this. It closes a **predict → observe → measure → calibrate** loop around any AI agent and produces a single, un-gameable number: the **Cognitive Integrity Score (CIS)**. When CIS is low, the agent is told to abstain. When CIS is high, decisions are trusted.

No self-reported confidence. No vibes. Just math against ground truth.

---

## ⚡ 3-Line Quickstart

```python
from reliability_gate import ReliabilityGate

gate = ReliabilityGate(api_key="my-project", agent_id="gpt-4o")
gate.observe(prediction=72.0, actual=68.5, domain="finance")  # teach it
gate.should_act()  # → True/False — governs the next decision
```

---

## What is a Wayne Agent?

A **Wayne Agent** is an autonomous agent connected to ReliabilityGate. It is **not trusted by default**. It earns permission to act through **measured reliability, selective abstention, anti-gameable baselines, and commit/reveal outcomes**.

ReliabilityGate can be used to *upgrade an ordinary agent into a Wayne Agent*: instead of acting because it was told to, the agent acts only once it has earned the right to.

> A Wayne Agent is not declared reliable — it has to prove it before acting.

*"Wayne Agent" is a narrative label for this pattern, not (yet) an industry standard. It describes how an agent behaves once it runs behind ReliabilityGate.*

---

## Action-aware gating: has the agent earned the right to *this* action?

ReliabilityGate doesn't just score an agent globally — it answers a concrete question: **should this agent perform this specific action right now?**

```python
from reliability_gate import ReliabilityGate

gate = ReliabilityGate(api_key="my-project", agent_id="support_agent")

# Teach it real outcomes, tagged by action:
gate.observe(prediction=80.0, actual=78.0, action="send_email")   # ...repeat over time

# Ask permission before the action:
decision = gate.should_act(
    action="send_email",
    risk_level="customer_visible",
    enforcement_mode="hard_gate",   # actually block when unreliable
)

if decision.allow:
    send_email()
else:
    print(decision.reason)
    # → "agent global reliability too low (CIS=0.04 < 0.40) for a customer_visible action 'send_email'"
```

`should_act(action=...)` returns a **`ReliabilityDecision`**:

| field | meaning |
|---|---|
| `allow` (= `enforced_allow`) | **effective** decision under the current `enforcement_mode` — what `if decision.allow:` runs (truthy: `if decision: ...` works too) |
| `recommended_allow` | what the gate **thinks** you should do, independent of mode (`False` if it recommends blocking *or* lacks evidence) |
| `mode` | `OBSERVE_ONLY` · `ADVISORY` · `SOFT_BLOCK` · `HARD_BLOCK` · `ALLOW` |
| `reason` | human-readable explanation |
| `recommendation` | `allow` · `block` · `gather_more_data` |
| `cis_score` | the agent's global reliability |
| `action_score` | reliability for *this* action (None if not enough data) |
| `sample_size` / `required_sample_size` | action-specific evidence vs what this risk level requires |

> **⚠️ `allow` vs `recommended_allow` — read this once.**
> In `observe` and `advisory` modes, **`allow` is always `True`** — it means *"not enforced"*, **not** *"safe to act"*. Only `hard_gate` ever sets `allow=False`. So this is correct and intended:
> ```python
> d = gate.should_act(action="send_email", risk_level="customer_visible",
>                     enforcement_mode="advisory")
> d.allow              # True  → advisory never blocks (NOT a safety claim)
> d.recommended_allow  # False → the gate actually recommends NOT acting
> d.recommendation     # "block"
> ```
> **To enforce**, use `enforcement_mode="hard_gate"` (then `allow` reflects the verdict). **To read the gate's real opinion** regardless of mode, use `recommended_allow` / `recommendation`. A naive `if decision.allow: send_email()` under advisory will send — by design; advisory recommends, it doesn't block.

**How the verdict is reached (V0):**
1. A **globally unreliable** agent attempting a **risky** action → blocked (it hasn't earned risky autonomy).
2. **Not enough action-specific outcomes** → no reliability claim (`gather_more_data`), never a false ALLOW.
3. **Enough evidence + action proven reliable** → ALLOW.
4. Enough evidence but **weak** → blocked.

Higher `risk_level` requires more action-specific evidence (`low`→3, `customer_visible`→10, `irreversible`/`destructive`→20; unknown risk fails closed). Calling `should_act()` **without** an `action` keeps the legacy agent-only behaviour and returns a plain `bool`.

> Try it live: `python demo_action_gating.py` (server running) — liar/guesser agents get `HARD_BLOCK`, the precise agent gets `ALLOW`. Every verdict is produced by the code, not scripted.

---

## The Problem

LLMs hallucinate. Everyone knows this. The current fix? Hope. Or maybe a prompt that says "be careful."

Here's what's actually broken:

- **No feedback loop.** The model never learns it was wrong yesterday.
- **No calibration.** Confidence is always 100%, whether the answer is right or invented.
- **No governance.** Nothing stops an unreliable agent from making the next decision.

The result: your agent is a coin flip dressed in a suit.

---

## The Solution

A closed loop. Predict, observe reality, measure the gap, recalibrate trust.

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│    │ PREDICT  │───▶│ OBSERVE  │───▶│ MEASURE  │          │
│    │ (agent)  │    │ (reality)│    │ (error)  │          │
│    └──────────┘    └──────────┘    └────┬─────┘          │
│         ▲                               │                │
│         │         ┌──────────┐          │                │
│         └─────────│CALIBRATE │◀─────────┘                │
│                   │  (CIS)   │                           │
│                   └──────────┘                           │
│                        │                                 │
│                   ┌────▼─────┐                           │
│                   │  GOVERN  │ → act / abstain / human   │
│                   └──────────┘                           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

The agent doesn't grade itself. **ReliabilityGate grades it** — against observed reality the agent cannot fabricate.

---

## Cognitive Integrity Score (CIS)

```
CIS = 0.40 × mae_score         # prediction error vs reality
    + 0.25 × abstention_score   # knows when to stay silent
    + 0.20 × skill_score        # beats the "repeat last value" naive baseline
    + 0.15 × falsif_score       # few catastrophically wrong predictions
```

| CIS Range | Label | What happens |
|-----------|-------|--------------|
| `[0.85, 1.0]` | **trusted** | Autonomous decisions allowed |
| `[0.65, 0.85)` | **calibrated** | Light supervision recommended |
| `[0.40, 0.65)` | **learning** | Human-in-the-loop required |
| `[0.00, 0.40)` | **unreliable** | Agent must abstain |

**Anti-gaming property:** the baseline for `skill_score` is *persistence* — "just repeat yesterday's number." If the agent can't beat that, its skill score is 0. The CIS is derived from real outcomes the agent cannot fabricate.

---

## Advisory usage: observe first, gate later

Teams adopt observability easily but resist hard gates. So you don't have to start by blocking anything.

**Start by logging the verdict without enforcing it. Turn hard gating on only after you trust the signal.**

```python
# 1. ADVISORY — log the verdict, never block (observe the signal)
@gate.guard(on_abstain="log")     # warns when unreliable, lets the call through
def call_llm(prompt: str) -> str:
    return openai.complete(prompt)

# ...or just read the verdict and decide for yourself:
verdict = gate.cis()
log.info("reliability", cis=verdict.score, should_act=verdict.should_act)

# 2. SOFT GATE — route to a human when unreliable, no exception
@gate.guard(on_abstain="none")
def call_llm(prompt: str) -> str | None:
    return openai.complete(prompt)

# 3. HARD GATE — refuse to act when unreliable
@gate.guard()                      # raises AbstentionRequired
def call_llm(prompt: str) -> str:
    return openai.complete(prompt)
```

For **action-aware** gating, the same progression is a first-class argument — `should_act(action=..., enforcement_mode=...)`:

- `enforcement_mode="observe"` → never blocks (`allow=True`), `mode=OBSERVE_ONLY`; the verdict rides in `recommendation`.
- `enforcement_mode="advisory"` (**client default**) → never blocks, `mode=ADVISORY`; surfaces `allow`/`block` advice.
- `enforcement_mode="hard_gate"` → actually blocks (`allow=False`) when the verdict is a block.

> **Honest note:** for the agent-only path there is no separate "observe mode" toggle — advisory usage *is* calling `should_act()`/`cis()` (or `guard(on_abstain="log")`) and choosing not to enforce. For the action-aware path, `enforcement_mode` makes that progression explicit, and only `hard_gate` ever sets `allow=False`.

---

## What Makes This Different

| Tool | What it does | ReliabilityGate |
|------|-------------|-----------------|
| **Cleanlab TLM** | Scores individual responses | Tracks **calibration over time** across many decisions |
| **Vectara HHEM** | Detects hallucination in RAG | Works on **any prediction domain**, not just text retrieval |
| **Arize Phoenix** | Observability & tracing | **Governs future decisions** based on past reliability |
| **Langfuse** | LLM analytics & prompt management | Measures **real prediction error**, not token-level metrics |
| **Galileo** | Evaluation & guardrails for GenAI | Computes **continuous calibration**, not per-run evals |
| **Patronus AI** | LLM evaluation & red-teaming | **Closed-loop recalibration** — the score evolves with evidence |

**The core difference:** they all *observe*. ReliabilityGate **governs**. The CIS doesn't just tell you something went wrong — it *gates the next decision*.

**Not a replacement — a complement.** ReliabilityGate is *not* a frontal competitor to observability/eval platforms (Langfuse, Arize, Galileo, Braintrust…). Those tell you *what happened* (traces, evals, dashboards). ReliabilityGate decides *whether the agent should act next*. They sit upstream; ReliabilityGate sits at the decision gate. Many teams will run both. The honest scope: it is a narrow, opinionated reliability **gate**, not a platform — and the market for agent reliability is real and crowded, so this lives by being sharper, not by claiming the space is empty.

**Why "anti-gameable":** the skill score is measured against a naive *persistence* baseline (repeat the last value), so an agent can't inflate its CIS without genuinely beating "do nothing"; the abstention score rewards *selective* reliability (acting only when accurate) and penalizes acting confidently while wrong; and `/commit`+`/reveal` let a prediction be hash-locked before the outcome is known, so it can't be backdated.

---

## API Reference (7 Routes)

Base URL: `http://localhost:8001` · Auth: `X-API-Key` header (= tenant ID)

### `POST /observe` — Submit a real outcome

```bash
curl -X POST http://localhost:8001/observe \
  -H "X-API-Key: my-project" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"gpt-4o","prediction":72.0,"actual":68.5,"domain":"finance"}'
```

```json
{"ok":true, "agent_id":"gpt-4o", "cis_updated":0.712, "verdict":"calibrated", "n_outcomes":15}
```

### `GET /cis/{agent_id}` — Get current CIS

```bash
curl http://localhost:8001/cis/gpt-4o -H "X-API-Key: my-project"
```

```json
{
  "agent_id":"gpt-4o", "cis":0.712, "verdict":"calibrated",
  "should_abstain":false, "forecast_skill":0.34, "n_outcomes":15,
  "components":{"mae_score":0.81,"abstention_score":0.65,"skill_score":0.67,"falsif_score":0.92}
}
```

### `POST /calibrate` — Full predict→observe→measure cycle

```bash
curl -X POST http://localhost:8001/calibrate \
  -H "X-API-Key: my-project" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"gpt-4o","url":"https://news.ycombinator.com/"}'
```

ReliabilityGate predicts the extraction yield → fetches the URL (read-only) → measures real yield → returns updated CIS.

### `GET /agents` — List all agents in your tenant

```bash
curl http://localhost:8001/agents -H "X-API-Key: my-project"
```

### `GET /health` — API status

```bash
curl http://localhost:8001/health
```

### `POST /commit` — Lock a prediction (anti-cheat)

```bash
# Step 1: Hash your prediction client-side, send the hash
HASH=$(python3 -c "import hashlib; print(hashlib.sha256(b'72.5|my_secret').hexdigest())")

curl -X POST http://localhost:8001/commit \
  -H "X-API-Key: my-project" \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"gpt-4o\",\"prediction_hash\":\"$HASH\",\"domain\":\"finance\"}"
```

```json
{"ok":true, "commit_id":"550e8400-e29b-41d4-a716-446655440000", "expires_in_seconds":3600}
```

### `POST /reveal` — Reveal prediction & submit outcome

```bash
# Step 2: Reveal your prediction + the real value. The server verifies the hash.
curl -X POST http://localhost:8001/reveal \
  -H "X-API-Key: my-project" \
  -H "Content-Type: application/json" \
  -d '{
    "commit_id":"550e8400-e29b-41d4-a716-446655440000",
    "prediction":72.5, "nonce":"my_secret", "actual":68.0
  }'
```

```json
{"ok":true, "verified":true, "cis_updated":0.689, "verdict":"calibrated"}
```

If the hash doesn't match → `400 Hash mismatch` → cheat detected, outcome rejected.

---

## SDK Usage

**Zero required dependencies.** Uses `httpx` if installed, falls back to `urllib`.

### Basic: observe + gate

```python
from reliability_gate import ReliabilityGate

gate = ReliabilityGate(api_key="my-project", agent_id="gpt-4o")

# After each decision — submit the real outcome
gate.observe(prediction=72.0, actual=68.5, domain="finance")

# Before each decision — check if the agent should act
if gate.should_act():
    result = llm.complete(prompt)
else:
    result = ask_human(prompt)
```

### Decorator: `@gate.guard()`

Three modes for when the agent is unreliable:

```python
# Mode 1: raise (default) — raises AbstentionRequired (hard gate)
@gate.guard()
def call_llm(prompt: str) -> str:
    return openai.complete(prompt)

# Mode 2: none — returns None silently (soft gate)
@gate.guard(on_abstain="none")
def maybe_call(prompt: str) -> str | None:
    return openai.complete(prompt)

# Mode 3: log — warns but lets it through (advisory)
@gate.guard(on_abstain="log", min_cis=0.65)
def risky_call(prompt: str) -> str:
    return openai.complete(prompt)
```

Catch `AbstentionRequired` to route to humans:

```python
from reliability_gate import AbstentionRequired

try:
    result = call_llm("What's the revenue forecast?")
except AbstentionRequired as e:
    route_to_human(task, cis=e.cis, reason=e.verdict)
```

### Commit-Reveal: anti-cheat for high-stakes domains

```python
# Lock the prediction BEFORE observing reality
commit = gate.commit(prediction=72.5, domain="finance")

# ... time passes, you observe the real outcome ...

# Reveal — the server verifies the hash matches
result = gate.reveal(
    commit_id=commit["commit_id"],
    nonce=commit["nonce"],
    prediction=72.5,
    actual=68.0,
)
# result["verified"] == True → cryptographically proven honest prediction

# Or use the shortcut for batch/historical ingestion:
gate.observe_verified(prediction=72.5, actual=68.0, domain="finance")
```

> **Legacy import (deprecated):** `from sdk.wayne_cog import WayneBrain` still works as a thin shim that emits a `DeprecationWarning` and re-exports `ReliabilityGate`. Use `from reliability_gate import ReliabilityGate` in new code.

---

## Domains

ReliabilityGate is domain-agnostic. Anywhere an AI predicts a number, it can grade it.

| Domain | What the agent predicts | What is observed |
|--------|------------------------|---------------------|
| **Finance** | Stock price, revenue forecast, risk score | Market data, actual revenue, realized losses |
| **SRE / DevOps** | Incident severity, deployment risk, ETA | Real incident impact, actual downtime, resolution time |
| **Medical** | Diagnosis confidence, treatment outcome | Lab results, patient outcome, follow-up data |
| **Content Moderation** | Toxicity score, policy violation likelihood | Human reviewer decisions, appeal outcomes |
| **Supply Chain** | Demand forecast, delivery ETA, stock levels | Actual sales, real delivery time, inventory count |
| **Legal** | Case outcome probability, contract risk | Court decisions, actual disputes |
| **Sales** | Deal close probability, lead score | Closed/lost outcome, actual revenue |
| **Customer Support** | Resolution likelihood, satisfaction score | Actual resolution, CSAT survey |

---

## Architecture

```
reliability-gate/
├── reliability_gate/            # PUBLIC package (this is what ships)
│   ├── __init__.py              # public API: ReliabilityGate, ReliabilityDecision, …
│   ├── client.py                # Python client — zero required deps
│   ├── decision.py              # action-aware decide() — pure permission-to-act logic
│   └── exceptions.py            # AbstentionRequired, APIError, ConnectionError
│
├── sdk/                         # DEPRECATED legacy shim (not shipped) → reliability_gate
│
├── api/
│   └── main.py                  # 7 routes: /observe /cis /calibrate /agents
│                                #           /health /commit /reveal
├── storage/
│   ├── cis_engine.py            # THE ENGINE — 4-component CIS formula (pure stdlib)
│   ├── outcome_store.py         # Append-only JSONL store, per-tenant, thread-safe
│   └── experience_store.py      # Belief memory (causal resolution)
│
├── adapters/
│   ├── browser_adapter.py       # OBSERVE-only HTTP extractor (no login, no write)
│   └── integrity_monitor.py     # RCIL: timestamps each observation cycle
│
├── core/                        # Full cognitive engine (15 modules)
│   ├── reality_cycle.py         # Main loop: predict → observe → persist
│   ├── self_competence.py       # Abstention gate: will_hold / will_break
│   ├── falsification_test.py    # Maps failure boundaries (Popper-style)
│   └── ...                      # more modules
│
├── data/                        # Per-tenant JSONL (auto-created)
│   └── {tenant_id}/
│       ├── outcomes.jsonl
│       └── rcil_observations.jsonl
│
├── tests/
│   └── test_reliability_gate.py # Unit + integration tests
│
├── requirements.txt
└── start.sh                     # One-command launch
```

**Key constraint:** `api/` and `storage/` have **zero dependency on Wayne OS**. The client (`reliability_gate/`) has **zero required dependencies** (httpx is optional). Everything works standalone.

---

## Running

### Quick start

```bash
git clone <repo-url> reliability-gate && cd reliability-gate
./start.sh
# → http://localhost:8001
# → http://localhost:8001/docs  (Swagger UI)
```

### Manual

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

### Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

```bash
docker build -t reliability-gate . && docker run -p 8001:8001 reliability-gate
```

---

## Multi-Tenant Isolation

Each `X-API-Key` is a separate tenant. Data is never shared.

```
data/
  acme-corp/          ← X-API-Key: acme-corp
    outcomes.jsonl
  another-tenant/     ← X-API-Key: another-tenant
    outcomes.jsonl
```

---

## Contributing

ReliabilityGate is open-source under Apache 2.0. Feedback, bug reports, and feature discussions are welcome.

1. **Issues** — Report bugs or request features via GitHub Issues.
2. **Discussions** — Architecture ideas, use cases, integration patterns.
3. **Pull Requests** — Fork and experiment freely; PRs are reviewed on a best-effort basis.

If you're building on ReliabilityGate or integrating it into your agent stack, [reach out](mailto:contact@wayne.ai). We want to hear from you.

---

## Compliance note

ReliabilityGate is **not** a legal compliance product and does **not** make an AI system compliant by itself. It provides local, auditable permission-to-act decisions that can *support* risk-management, human-oversight and traceability workflows. **Compliance-aware, not compliance-certified.**

## License

[Apache License 2.0](LICENSE) — © 2026 Riad Lahlou. Free to use, modify and distribute (including commercially) under the terms of the license.
