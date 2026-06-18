# PyPI long_description — ReliabilityGate

> Texte proposé pour le champ `readme` / long_description sur PyPI. Sobre, sans hype.
> (Le `pyproject.toml` pointe déjà `readme = "README.md"` ; ce fichier sert de version
> condensée/relue si on veut un long_description distinct.)
> Nom public : **ReliabilityGate** (prototypé en interne sous le codename « Wayne Brain »).

---

# ReliabilityGate

**An anti-gameable permission-to-act layer for autonomous agents.**

Your AI agent answers with the same confidence whether it has full context or none.
ReliabilityGate closes a **predict → observe → measure → calibrate** loop around any agent and
produces one number — the **Cognitive Integrity Score (CIS)** — measured against ground truth.
When the CIS is low, the agent is told to abstain. When it's high, decisions are trusted.

It is **not** an observability dashboard and **not** a hallucination detector. It is a
**decision gate** that complements tools like Langfuse, Arize or Galileo: they tell you what
happened; ReliabilityGate decides whether the agent should act next.

**Upgrade ordinary agents into Wayne Agents** — agents that aren't trusted by default and must
prove reliability before they act. (A "Wayne Agent" is a narrative label for an agent running
behind ReliabilityGate, not an industry standard.)

## Install

```bash
pip install reliability-gate
```

## Quickstart — action-aware gating

```python
from reliability_gate import ReliabilityGate

gate = ReliabilityGate(api_key="my-project", agent_id="support_agent")
gate.observe(prediction=80.0, actual=78.0, action="send_email")  # teach it over time

decision = gate.should_act(action="send_email",
                           risk_level="customer_visible",
                           enforcement_mode="hard_gate")
if decision.allow:
    send_email()
else:
    print(decision.reason)
```

`should_act(action=...)` returns a `ReliabilityDecision` (`allow`/`enforced_allow`,
`recommended_allow`, `mode`, `reason`, `recommendation`, `cis_score`, `action_score`,
`sample_size`/`required_sample_size`). Note: in `observe`/`advisory` modes `allow` is always
`True` ("not enforced", not "safe") — read `recommended_allow`/`recommendation` for the gate's
real opinion, or use `enforcement_mode="hard_gate"` to enforce. Calling `should_act()` without an
`action` keeps the legacy agent-only `bool` behaviour.

## Why "anti-gameable"

- **Persistence baseline** — skill is measured against "repeat the last value", so an agent
  can't inflate its score without genuinely beating doing nothing.
- **Selective abstention** — rewards acting only when reliable; penalizes acting confidently
  while wrong.
- **Commit/reveal** — a prediction can be hash-locked before the outcome is known, so it can't
  be backdated.

## Observe first, gate later

You don't have to block anything on day one. Log the gate's verdict without enforcing it
(`should_act()` / `@guard(on_abstain="log")`), then move to soft gating, then hard gating once you
trust the signal. There is no separate "observe mode" toggle — advisory usage is simply choosing
not to enforce the verdict yet.

## What you get

A small client (zero required dependencies) that talks to the ReliabilityGate API: `observe`,
`should_act`, `@guard` decorator (raises `AbstentionRequired` when unreliable), `commit`/`reveal`.

> Legacy import `from sdk.wayne_cog import WayneBrain` still works as a deprecated shim; use
> `from reliability_gate import ReliabilityGate`.

---

*Honest scope: the agent-reliability market is real and crowded. ReliabilityGate is a narrow,
opinionated reliability gate — not a platform, not "indispensable". Try it where an agent must
decide whether it's reliable enough to act.*
