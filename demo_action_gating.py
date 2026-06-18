#!/usr/bin/env python3
"""
ReliabilityGate — Démo "dangerous action blocked" (réelle, soutenue par le code)
================================================================================
Montre la permission-to-act layer en action : un agent ne peut exécuter une
action que s'il a *mérité le droit de l'exécuter*.

Chaque verdict ci-dessous est produit LITTÉRALEMENT par le code :
  1. on soumet de vrais outcomes tagués par action (gate.observe(..., action=...)) ;
  2. on demande la permission (gate.should_act(action=..., risk_level=...)) ;
  3. on imprime la ReliabilityDecision renvoyée par le moteur.

Aucune phrase ne décrit une API inexistante.

Prérequis : l'API ReliabilityGate doit tourner sur http://localhost:8001
    → ./start.sh
Usage : python demo_action_gating.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BASE_URL = "http://localhost:8001"

# Séquences d'outcomes DÉTERMINISTES (pred, actual) — reproductibles.
# "abstain" = l'agent s'est abstenu (pas de prédiction).
SCENARIOS = [
    # (label, icon, action, risk_level, enforcement, outcomes)
    (
        "precise-agent", "🎯", "send_email", "customer_visible", "hard_gate",
        [(70, 71), (55, 54), (80, 82), (60, 59), (75, 76), (50, 51),
         (65, 64), (72, 73), (58, 57), (68, 69), (62, 61), (77, 78)],
    ),
    (
        "liar-agent", "🤥", "send_email", "customer_visible", "hard_gate",
        [(90, 20), (85, 15), (95, 25), (80, 10), (88, 18), (92, 22),
         (83, 12), (96, 28), (81, 30), (89, 19), (94, 24), (82, 14)],
    ),
    (
        "guesser-agent", "🎲", "delete_file", "destructive", "hard_gate",
        [(10, 80), (90, 30), (20, 70), (85, 25), (15, 75), (95, 35),
         (30, 60), (70, 20), (25, 65), (88, 28), (12, 72), (78, 18)],
    ),
    (
        "abstainer-agent", "🧘", "call_api", "medium", "advisory",
        [(60, 61), (55, 54), "abstain", (70, 71), (65, 66), "abstain",
         (58, 59), (72, 73), (62, 63), (68, 67), (75, 74), (57, 58)],
    ),
]

# ── Couleurs ────────────────────────────────────────────────────────────────
GREEN, RED, YELLOW, BLUE, DIM, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[34m", "\033[2m", "\033[1m", "\033[0m"
)


def colored(s: str, c: str) -> str:
    return f"{c}{s}{RESET}"


def check_api() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    from reliability_gate import ReliabilityGate

    print(colored("\n  ReliabilityGate — permission-to-act layer (démo réelle)", BOLD))
    print(colored("  An agent should earn the right to act.\n", DIM))

    if not check_api():
        print(colored("  ✗ API non accessible sur http://localhost:8001 — lancez ./start.sh\n", RED))
        return 1

    # suffixe unique → isolation entre exécutions (le store persiste)
    run = str(time.time_ns())[-6:]

    rows = []
    for label, icon, action, risk, enforcement, outcomes in SCENARIOS:
        agent_id = f"{label}-{run}"
        gate = ReliabilityGate(api_key="demo-action-gating", agent_id=agent_id, base_url=BASE_URL)

        # 1) on enseigne de vrais outcomes tagués par action
        for o in outcomes:
            if o == "abstain":
                gate.observe(abstained=True, action=action, domain="demo")
            else:
                pred, actual = o
                gate.observe(prediction=float(pred), actual=float(actual),
                             action=action, domain="demo")

        # 2) on demande la permission d'exécuter l'action
        decision = gate.should_act(action=action, risk_level=risk, enforcement_mode=enforcement)

        rows.append((icon, label, action, risk, enforcement, decision))

    # 3) affichage des verdicts RÉELS
    sep = colored("  " + "─" * 96, DIM)
    print(f"  {BOLD}{'Agent':<19}{'Action':<14}{'Risk':<17}{'Enforce':<10}{'Allow':<7}{'Mode':<13}{'CIS':<7}{RESET}")
    print(sep)
    for icon, label, action, risk, enforcement, d in rows:
        # pad le texte AVANT coloration (sinon les codes ANSI faussent la largeur)
        allow_cell = colored(f"{'ALLOW' if d.allow else 'BLOCK':<6}", GREEN if d.allow else RED)
        mode_col = {
            "HARD_BLOCK": RED, "SOFT_BLOCK": YELLOW, "ALLOW": GREEN,
            "ADVISORY": BLUE, "OBSERVE_ONLY": DIM,
        }.get(d.mode, RESET)
        mode_cell = colored(f"{d.mode:<13}", mode_col)
        print(f"  {icon} {label:<16}{action:<14}{risk:<17}{enforcement:<10}"
              f"{allow_cell} {mode_cell}{d.cis_score:.3f}")
        print(colored(f"       └ {d.reason}", DIM))
    print(sep)

    print(colored("\n  Lecture :", BOLD))
    print(colored("  • liar-agent / guesser-agent : action risquée + agent peu fiable → HARD_BLOCK (allow=False).", DIM))
    print(colored("  • precise-agent : send_email prouvé fiable → ALLOW (allow=True).", DIM))
    print(colored("  • abstainer-agent : enforcement=advisory → ADVISORY (allow=True, recommandation seulement).", DIM))
    print(colored("\n  Chaque verdict est produit par gate.should_act(action=...) — rien n'est scénarisé.\n", DIM))
    return 0


if __name__ == "__main__":
    sys.exit(main())
