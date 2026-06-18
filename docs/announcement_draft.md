# Announcement draft — ReliabilityGate

> Brouillon sobre, sans hype. À relire/poster par Riad sous son identité, après le GO public.
> Pas de « revolutionary », pas de promesse massive, pas de chiffre marché non sourcé.
> Nom public : **ReliabilityGate** (prototypé en interne sous le codename « Wayne Brain » — à ne
> PAS mettre au centre de l'annonce).

---

## Version courte (X / HN title)

**ReliabilityGate — an anti-gameable permission-to-act layer for autonomous agents (open-source SDK)**

Most agents act with the same confidence whether they're reliable or not. ReliabilityGate measures
an agent's reliability against ground truth and tells it to abstain when it isn't reliable enough.

The goal is simple: **before an agent acts, it should prove it has earned the right to act.**

---

## Version moyenne (Show HN / Dev.to intro)

**The problem.** Autonomous agents act with constant confidence — full context or none. They
don't know what they don't know, and they don't tell you. So they act even when unreliable.

**What ReliabilityGate does.** It closes a predict → observe → measure → calibrate loop around any
agent and produces one number, the Cognitive Integrity Score (CIS), measured against real
outcomes. Low CIS → the agent is told to abstain. High CIS → decisions are trusted. The point is a
**permission-to-act layer**: before an agent acts, it should prove it has earned the right to. It
gates **per action** (`send_email`, `delete_file`, `transfer_money`…), not just per agent — a risky
action requires more action-specific evidence before it's allowed autonomously.

**Upgrade an agent into a "Wayne Agent".** A Wayne Agent is just an ordinary agent running behind
ReliabilityGate — not trusted by default, earning the right to act through measured reliability,
selective abstention, anti-gameable baselines and commit/reveal. (It's a way of describing the
behavior, not an industry standard.)

**What it is not.** Not an observability dashboard (Langfuse, Arize), not a general hallucination
detector (Galileo, Patronus). It's a *decision gate* — a complement to those tools, not a
replacement. They tell you what happened; ReliabilityGate decides whether the agent should act next.

**Why "anti-gameable".**
- Skill is measured against a naive persistence baseline (repeat the last value) — you can't
  inflate the score without genuinely beating "do nothing".
- The abstention score rewards acting only when reliable and penalizes acting confidently while wrong.
- `commit`/`reveal` lets a prediction be hash-locked before the outcome is known — no backdating.

**Observe first, gate later.** You don't have to block anything on day one: log the verdict without
enforcing it, then move to soft gating, then hard gating once you trust the signal.

**Honest scope.** The agent-reliability space is real and crowded. ReliabilityGate is a small,
opinionated gate, not a platform. Try it where an agent must decide whether it's reliable enough
to act, and tell me where it breaks.

```bash
pip install reliability-gate
```

```python
from reliability_gate import ReliabilityGate

gate = ReliabilityGate(api_key="my-project", agent_id="support_agent")
gate.observe(prediction=80.0, actual=78.0, action="send_email")   # teach it over time

decision = gate.should_act(action="send_email",
                           risk_level="customer_visible",
                           enforcement_mode="hard_gate")
if decision.allow:
    send_email()
else:
    print(decision.reason)   # the agent hasn't earned the right to this action yet
```

Repo: <github.com/riadlahlou/reliability-gate> · License: Apache-2.0

---

## ✅ À écrire (vrai, tenu par le code)

- « anti-gameable reliability scoring »
- « permission-to-act layer »
- « selective abstention »
- « commit/reveal outcomes »
- « advisory usage before hard gating » (observe first, gate later)
- « a Wayne Agent must prove reliability before acting »

## ❌ À NE PAS écrire

- « more reliable than any agent » (non prouvé)
- « guaranteed safe » / « fully autonomous safety »
- « indispensable » / « the only tool » / « nobody else does this » (faux, marché encombré)
- « revolutionary », « 10x », « massive »
- chiffres marché non sourcés (ex. « $1.4B »)
- promesses de résultat garanti
- comparatif dénigrant les concurrents (rester factuel : complément, pas remplacement)
- présenter « Wayne Agent » comme un standard reconnu (c'est un label, 0 adoption à ce jour)
