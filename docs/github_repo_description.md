# GitHub repo description — ReliabilityGate

> Textes proposés pour les métadonnées du repo (à valider/coller par Riad lors de la création).
> Aucun repo n'est créé ici. Nom de repo proposé : `reliability-gate`.

## Description courte (champ "About", ≤ ~120 caractères)

> Anti-gameable permission-to-act layer for autonomous agents — measure real reliability, abstain when unreliable.

Variante :

> A decision gate for AI agents: predict→observe→measure→calibrate. Low reliability → the agent abstains.

## Topics (tags suggérés)

`ai-agents` · `llm` · `reliability` · `permission-to-act` · `abstention` · `calibration`
· `agent-governance` · `python` · `fastapi` · `ai-safety`

## README hero (déjà dans README.md)

Titre : **ReliabilityGate**
Tagline : *An anti-gameable permission-to-act layer for autonomous agents — not an observability
dashboard, not a hallucination detector: a decision gate.*
Sous-message : *Upgrade ordinary agents into Wayne Agents — agents that must prove reliability
before acting.*

## Ce qu'il faut vérifier avant de rendre public

- [ ] Nom du repo confirmé : `reliability-gate`
- [ ] Nom de package PyPI confirmé : `reliability-gate` (import `reliability_gate`)
- [ ] `LICENSE` appliquée (cf. license_decision.md) — sinon GitHub affiche "no license"
- [ ] `.gitignore` exclut `.venv/`, `data/`, `dist/`, `build/`, `*.egg-info`, secrets, `.env`
- [ ] Aucune branche/commit ne contient de secret ni de `data/` tenant
- [ ] Le repo ne contient PAS le code privé Wayne OS (projet séparé)

## Note positionnement (à NE PAS mettre dans la description)

Ne pas écrire « the only tool that… » ni « indispensable » : le marché est encombré
(Galileo, Arize, Langfuse, Patronus, Cleanlab, Braintrust). Le repo se distingue par l'angle
(porte de décision / permission-to-act anti-gameable), pas par un vide de marché.

« Wayne Agent » est un **label narratif**, pas un standard reconnu — ne pas le présenter comme
une catégorie établie tant que l'adoption ne l'a pas validé.
