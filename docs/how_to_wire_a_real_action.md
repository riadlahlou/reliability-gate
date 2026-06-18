# How to wire a real action

> The honest one-pager that answers the question every builder asks first:
> *"What do I feed `observe()` for a real action, and where does the ground-truth
> number come from?"* — Short answer: **you define a 0-100 outcome you can measure,
> and you feed it back when it lands.** ReliabilityGate calibrates the agent's
> self-assessment against that number over time. It does not guess whether an
> email was "good".

## The contract (3 numbers)

ReliabilityGate needs, per action:

1. a **`prediction`** (0-100) — the agent's *own* estimate, made **before** acting;
2. an **`actual`** (0-100) — the *real* outcome, observed **after**, which **you** supply;
3. enough of these pairs to calibrate (more for riskier actions).

The whole loop is: **predict → gate → act → observe the real outcome → recalibrate.**
The `actual` almost always arrives *later* (a reply, a CSAT, a resolved flag), so
you wire it in two places.

## Worked example — a customer-support agent that sends replies

```python
from reliability_gate import ReliabilityGate

gate = ReliabilityGate(api_key="acme", agent_id="support_agent")
pending: dict[str, float] = {}   # ticket_id -> the prediction we made

# ── 1. At decision time: predict, gate, act ────────────────────────────────
def handle_ticket(ticket):
    draft, self_score = agent.draft_reply(ticket)   # self_score: agent's 0-100 confidence

    decision = gate.should_act(
        action="send_reply",
        risk_level="customer_visible",
        enforcement_mode="advisory",   # start advisory: recommend, don't block
    )

    # In advisory/observe, read recommended_allow (the gate's real opinion),
    # NOT allow (which is always True when not enforcing).
    if decision.recommended_allow:
        send(draft)
        pending[ticket.id] = self_score        # remember the prediction
    else:
        route_to_human(ticket, reason=decision.reason)

# ── 2. Later, when the real outcome lands: observe it ──────────────────────
def on_resolution_feedback(ticket_id: str, resolved: bool):
    self_score = pending.pop(ticket_id, None)
    if self_score is None:
        return
    actual = 100.0 if resolved else 0.0        # ← YOUR ground truth, on a 0-100 scale
    gate.observe(prediction=self_score, actual=actual, action="send_reply")
```

That's the whole integration. The agent says "I'm 85% sure this reply resolves
the ticket" (`prediction=85`), you later learn it did/didn't (`actual=100/0`), and
ReliabilityGate tracks whether that confidence is *earned* — per action.

## Where does `actual` come from? (4 honest patterns)

| Your situation | How to produce `actual` (0-100) |
|---|---|
| **Binary outcome** (resolved/not, delivered/bounced, approved/rejected) | `100.0` or `0.0` |
| **A metric you already have** | rescale to 0-100 (CSAT 1-5 → `csat * 20`; open-rate % → as-is) |
| **No automatic signal** | a human or an LLM-judge score, 0-100 (slower, more subjective — but real) |
| **No producible ground-truth at all** | don't gate that action with ReliabilityGate. It can't calibrate what it can't observe — and it will honestly say `not enough action-specific outcomes yet` rather than fake a verdict |

Pick the cheapest *real* signal. A noisy binary outcome you actually capture beats
a perfect score you never collect.

## Cold start: the first calls have no data

Until you've fed enough `send_reply` outcomes (10 for `customer_visible`), the
decision is `recommendation="gather_more_data"` / `mode` `ADVISORY` or
`OBSERVE_ONLY` — **never a false ALLOW**. So the natural rollout is:

1. **`enforcement_mode="observe"`** — log `decision` next to your own choices; ship nothing differently.
2. Accumulate outcomes; watch whether `recommended_allow` tracks reality.
3. **`enforcement_mode="advisory"`** — start routing low-confidence cases to humans.
4. **`enforcement_mode="hard_gate"`** — once you trust the signal, let it block (then read `allow`).

This is "observe first, gate later" — not a slogan, the actual adoption path.

## Honest caveats

- The `actual` is **on you**. ReliabilityGate measures calibration against the
  number you provide; garbage `actual` → garbage CIS.
- It is **not** a content/safety classifier — it won't read the email and judge
  it. It tracks whether the agent's *predictions* match *reality* over time.
- `risk_level` only changes how much evidence is required (`low`=3 … `customer_visible`=10 …
  `destructive`/`financial`=20; unknown → strictest). It doesn't read the action's meaning.
- The decision is computed client-side (V0): a governance aid, not a security boundary.

> Rule of thumb: **if you can name a 0-100 outcome for an action and capture it
> within a reasonable delay, you can gate that action. If you can't, ReliabilityGate
> will tell you it doesn't know — which is the point.**
