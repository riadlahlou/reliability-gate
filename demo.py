#!/usr/bin/env python3
"""
ReliabilityGate — Démo interactive
================================
Lance 5 agents avec des profils de fiabilité différents, soumet 15 outcomes
chacun, puis affiche un tableau comparatif des CIS.

Usage :
    python demo.py

Prérequis :
    L'API ReliabilityGate doit tourner sur http://localhost:8001
    → ./start.sh
"""
from __future__ import annotations

import random
import sys
import time

# ── ANSI couleurs (zéro dépendance externe) ──────────────────────────────────

BOLD      = "\033[1m"
DIM       = "\033[2m"
RESET     = "\033[0m"
RED       = "\033[31m"
GREEN     = "\033[32m"
YELLOW    = "\033[33m"
BLUE      = "\033[34m"
MAGENTA   = "\033[35m"
CYAN      = "\033[36m"
WHITE     = "\033[37m"
BG_RED    = "\033[41m"
BG_GREEN  = "\033[42m"
BG_BLUE   = "\033[44m"


def colored(text: str, color: str) -> str:
    """Applique une couleur ANSI à un texte."""
    return f"{color}{text}{RESET}"


# ── Bannière ASCII ───────────────────────────────────────────────────────────

BANNER = f"""{CYAN}{BOLD}
 ╦ ╦╔═╗╦ ╦╔╗╔╔═╗  ╔╗ ╦═╗╔═╗╦╔╗╔
 ║║║╠═╣╚╦╝║║║║╣   ╠╩╗╠╦╝╠═╣║║║║
 ╚╩╝╩ ╩ ╩ ╝╚╝╚═╝  ╚═╝╩╚═╩ ╩╩╝╚╝
{RESET}{DIM} Cognitive Reliability Layer for AI Agents{RESET}
{DIM} ─────────────────────────────────────────{RESET}
"""

# ── Configuration des 5 agents ───────────────────────────────────────────────

AGENTS = {
    "precise-agent": {
        "desc": "Prédictions proches de la réalité",
        "color": GREEN,
        "icon": "🎯",
    },
    "noisy-agent": {
        "desc": "Prédictions avec bruit aléatoire",
        "color": YELLOW,
        "icon": "📡",
    },
    "liar-agent": {
        "desc": "Prédictions systématiquement fausses",
        "color": RED,
        "icon": "🤥",
    },
    "abstainer-agent": {
        "desc": "S'abstient quand incertain",
        "color": BLUE,
        "icon": "🧘",
    },
    "guesser-agent": {
        "desc": "Prédictions complètement aléatoires",
        "color": MAGENTA,
        "icon": "🎲",
    },
}

N_OUTCOMES = 15
API_KEY = "demo-bench"
BASE_URL = "http://localhost:8001"


def generate_outcomes(agent_name: str, seed: int = 42) -> list[dict]:
    """Génère N_OUTCOMES paires (prediction, actual) réalistes selon le profil."""
    rng = random.Random(seed + hash(agent_name))
    outcomes: list[dict] = []

    for i in range(N_OUTCOMES):
        # Valeur réelle : signal de base avec variation naturelle
        base = 50.0 + 15.0 * rng.gauss(0, 1)
        actual = max(0.0, min(100.0, round(base, 1)))

        if agent_name == "precise-agent":
            # Très proche de la réalité : erreur ±2
            noise = rng.gauss(0, 2.0)
            prediction = round(max(0.0, min(100.0, actual + noise)), 1)
            outcomes.append({"prediction": prediction, "actual": actual, "abstained": False})

        elif agent_name == "noisy-agent":
            # Bruit modéré : erreur ±12
            noise = rng.gauss(0, 12.0)
            prediction = round(max(0.0, min(100.0, actual + noise)), 1)
            outcomes.append({"prediction": prediction, "actual": actual, "abstained": False})

        elif agent_name == "liar-agent":
            # Systématiquement opposé : prédit haut quand bas, bas quand haut
            prediction = round(max(0.0, min(100.0, 100.0 - actual + rng.gauss(0, 3.0))), 1)
            outcomes.append({"prediction": prediction, "actual": actual, "abstained": False})

        elif agent_name == "abstainer-agent":
            # Bon quand il prédit, mais s'abstient ~30% du temps (quand incertain)
            uncertainty = abs(actual - 50.0)  # plus c'est loin de 50, plus c'est clair
            if uncertainty < 10 and rng.random() < 0.4:
                # Zone incertaine → s'abstient intelligemment
                outcomes.append({"prediction": None, "actual": actual, "abstained": True})
            else:
                noise = rng.gauss(0, 3.0)
                prediction = round(max(0.0, min(100.0, actual + noise)), 1)
                outcomes.append({"prediction": prediction, "actual": actual, "abstained": False})

        elif agent_name == "guesser-agent":
            # Complètement aléatoire : aucun lien entre prediction et actual
            prediction = round(rng.uniform(0, 100), 1)
            outcomes.append({"prediction": prediction, "actual": actual, "abstained": False})

    return outcomes


def check_api_available() -> bool:
    """Vérifie que l'API ReliabilityGate est accessible."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/health",
            headers={"X-API-Key": API_KEY},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_demo() -> None:
    """Boucle principale de la démo."""

    # ── Import du SDK ────────────────────────────────────────────────────────
    # Ajoute le répertoire racine au PYTHONPATH pour l'import local
    from pathlib import Path
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    from reliability_gate import ReliabilityGate

    print(BANNER)
    print(colored("  Vérification de l'API...", DIM), end=" ", flush=True)

    if not check_api_available():
        print(colored("✗ ÉCHEC", RED))
        print()
        print(colored("  ╔══════════════════════════════════════════════════════════╗", RED))
        print(colored("  ║  L'API ReliabilityGate n'est pas accessible port 8001.  ║", RED))
        print(colored("  ║                                                          ║", RED))
        print(colored("  ║  Lancez d'abord le serveur :                             ║", RED))
        print(colored("  ║    ./start.sh                                            ║", RED))
        print(colored("  ║                                                          ║", RED))
        print(colored("  ║  Ou manuellement :                                       ║", RED))
        print(colored("  ║    uvicorn api.main:app --port 8001                      ║", RED))
        print(colored("  ╚══════════════════════════════════════════════════════════╝", RED))
        print()
        sys.exit(1)

    print(colored("✓ API prête", GREEN))
    print()

    # ── Phase 1 : Soumission des outcomes ────────────────────────────────────

    separator = colored("  ─" * 28, DIM)
    print(colored(f"  ▶ PHASE 1 : Soumission de {N_OUTCOMES} outcomes par agent", BOLD))
    print(separator)
    print()

    results: dict[str, dict] = {}

    for agent_name, config in AGENTS.items():
        gate = ReliabilityGate(api_key=API_KEY, agent_id=agent_name, base_url=BASE_URL)
        icon = config["icon"]
        color = config["color"]

        print(f"  {icon} {colored(agent_name, color + BOLD)}")
        print(f"     {colored(config['desc'], DIM)}")

        outcomes = generate_outcomes(agent_name)
        last_cis = 0.0
        last_verdict = "..."

        for i, outcome in enumerate(outcomes, 1):
            try:
                if outcome["abstained"]:
                    resp = gate.observe(
                        actual=outcome["actual"],
                        abstained=True,
                        domain="demo",
                    )
                    marker = colored("ABS", BLUE)
                    detail = f"actual={outcome['actual']:5.1f}"
                else:
                    resp = gate.observe(
                        prediction=outcome["prediction"],
                        actual=outcome["actual"],
                        domain="demo",
                    )
                    error = abs(outcome["prediction"] - outcome["actual"])
                    if error < 5:
                        marker = colored("●", GREEN)
                    elif error < 15:
                        marker = colored("●", YELLOW)
                    else:
                        marker = colored("●", RED)
                    detail = f"pred={outcome['prediction']:5.1f} actual={outcome['actual']:5.1f} err={error:5.1f}"

                last_cis = resp.get("cis_updated", 0.0)
                last_verdict = resp.get("verdict", "?")

                # Barre de progression compacte
                bar_len = 20
                filled = int(i / N_OUTCOMES * bar_len)
                bar = colored("█" * filled, color) + colored("░" * (bar_len - filled), DIM)
                sys.stdout.write(f"\r     [{bar}] {i:2d}/{N_OUTCOMES} {marker} {detail}")
                sys.stdout.flush()

            except Exception as exc:
                print(f"\n     {colored(f'ERREUR: {exc}', RED)}")
                sys.exit(1)

        # Résultat final pour cet agent
        try:
            cis_result = gate.cis()
            results[agent_name] = {
                "cis": cis_result.score,
                "verdict": cis_result.verdict,
                "should_act": cis_result.should_act,
                "n_outcomes": cis_result.n_outcomes,
                "components": cis_result.components,
                "icon": icon,
                "color": color,
            }
        except Exception:
            results[agent_name] = {
                "cis": last_cis,
                "verdict": last_verdict,
                "should_act": last_verdict in ("trusted", "calibrated"),
                "n_outcomes": N_OUTCOMES,
                "components": {},
                "icon": icon,
                "color": color,
            }

        # Score final sur la même ligne
        verdict_color = {
            "trusted": GREEN,
            "calibrated": CYAN,
            "learning": YELLOW,
            "unreliable": RED,
        }.get(results[agent_name]["verdict"], WHITE)

        print(f"  → CIS={colored(f'{results[agent_name]['cis']:.3f}', verdict_color)}")
        print()

    # ── Phase 2 : Tableau comparatif ─────────────────────────────────────────

    print()
    print(colored(f"  ▶ PHASE 2 : Tableau comparatif des agents", BOLD))
    print(separator)
    print()

    # En-tête du tableau
    hdr = (
        f"  {'Agent':<20s} │ {'CIS':>7s} │ {'Verdict':<12s} │ {'Act?':>5s} │ {'N':>3s}"
    )
    print(colored(hdr, BOLD))
    print(f"  {'─' * 20}─┼─{'─' * 7}─┼─{'─' * 12}─┼─{'─' * 5}─┼─{'─' * 3}")

    # Tri par CIS décroissant
    sorted_agents = sorted(results.items(), key=lambda x: x[1]["cis"], reverse=True)

    for agent_name, data in sorted_agents:
        cis_val = data["cis"]
        verdict = data["verdict"]
        should_act = data["should_act"]
        icon = data["icon"]
        color = data["color"]

        # Couleur selon le verdict
        verdict_color = {
            "trusted": GREEN,
            "calibrated": CYAN,
            "learning": YELLOW,
            "unreliable": RED,
        }.get(verdict, WHITE)

        act_str = colored(" YES", GREEN) if should_act else colored("  NO", RED)
        cis_str = colored(f"{cis_val:7.3f}", verdict_color)
        verdict_str = colored(f"{verdict:<12s}", verdict_color)

        print(f"  {icon} {colored(agent_name, color):<29s} │ {cis_str} │ {verdict_str} │ {act_str} │ {data['n_outcomes']:3d}")

    print(f"  {'─' * 20}─┴─{'─' * 7}─┴─{'─' * 12}─┴─{'─' * 5}─┴─{'─' * 3}")

    # ── Détail des composantes ───────────────────────────────────────────────

    print()
    print(colored("  ▶ Détail des composantes CIS", BOLD))
    print(separator)
    print()

    comp_hdr = f"  {'Agent':<20s} │ {'MAE':>6s} │ {'Abst.':>6s} │ {'Skill':>6s} │ {'Falsif':>6s}"
    print(colored(comp_hdr, BOLD))
    print(f"  {'─' * 20}─┼─{'─' * 6}─┼─{'─' * 6}─┼─{'─' * 6}─┼─{'─' * 6}")

    for agent_name, data in sorted_agents:
        comp = data.get("components", {})
        icon = data["icon"]
        color = data["color"]

        mae_s   = f"{comp.get('mae_score', 0.0):6.3f}"
        abst_s  = f"{comp.get('abstention_score', 0.0):6.3f}"
        skill_s = f"{comp.get('skill_score', 0.0):6.3f}"
        fals_s  = f"{comp.get('falsif_score', 0.0):6.3f}"

        print(f"  {icon} {colored(agent_name, color):<29s} │ {mae_s} │ {abst_s} │ {skill_s} │ {fals_s}")

    print(f"  {'─' * 20}─┴─{'─' * 6}─┴─{'─' * 6}─┴─{'─' * 6}─┴─{'─' * 6}")

    # ── Message final ────────────────────────────────────────────────────────

    print()
    print(separator)
    print()
    print(colored("  💡 ", YELLOW) + colored(
        "The agent that knows it doesn't know is more valuable "
        "than the one that doesn't know it doesn't know.",
        BOLD + WHITE,
    ))
    print()
    print(colored(f"  ReliabilityGate — https://github.com/riadlahlou/reliability-gate", DIM))
    print()


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        print(colored("\n\n  Démo interrompue.", DIM))
        sys.exit(0)
