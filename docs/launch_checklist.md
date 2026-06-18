# Launch Checklist — ReliabilityGate

> Préparation à 100%, publication à 0%. Toutes les étapes "monde externe" sont des **actes de
> Riad** (comptes, identité, irréversibles). Wayne/Claude ne franchit rien sans GO explicite.
> Nom public : **ReliabilityGate** (codename interne / legacy : « Wayne Brain »).

## ✅ Prêt (préparé localement, vérifié)

- [x] **Rename d'import public propre** : `from reliability_gate import ReliabilityGate`
      (l'ancien `from sdk.wayne_cog import WayneBrain` reste un shim **déprécié** qui warn)
- [x] Package public `reliability_gate` (client.py + exceptions.py + __init__.py)
- [x] `sdk/` rétrogradé en shim déprécié, **exclu du wheel**
- [x] Cœur corrigé : abstention discriminante (régression testée)
- [x] Anti-gameable (baseline persistance) + commit/reveal
- [x] Tests verts (unit + naming + compat legacy ; intégration skipped sans serveur)
- [x] `python -m build` → wheel OK
- [x] `pip install dist/*.whl` dans venv propre → OK (ship `reliability_gate` uniquement, 0 dépendance)
- [x] README repositionné (permission-to-act ; What is a Wayne Agent? ; observe first, gate later ;
      complément pas concurrent ; pas d'overclaim ; wrapper CDATA malformé retiré)
- [x] `pyproject.toml` : name=`reliability-gate`, packages=`reliability_gate*`, urls proposées
- [x] Audit : pas de secret, pas de `.env`, pas de dépendance Wayne OS dans le wheel
- [x] Docs : positioning, licence, risques, pypi/github descriptions, annonce — tous renommés
- [x] **Licence tranchée + appliquée : Apache-2.0** (`LICENSE` officiel, pyproject + classifier OSI, README) — `LICENSE.proposed` supprimé

## ⏳ Décisions & actes manuels de Riad (Level C, irréversibles)

- [x] **Licence** → **Apache-2.0** (tranché 2026-06-18, appliqué localement)
- [ ] **Relire le README public** une dernière fois
- [ ] **Créer / autoriser le repo GitHub** (sous identité Riad)
- [ ] **Créer / autoriser un token PyPI** (compte Riad)
- [ ] **Autoriser la publication**

## Séquence de publication (UNIQUEMENT après les validations ci-dessus)

1. ~~Appliquer la licence~~ ✅ fait (Apache-2.0)
2. `git init` + premier commit + `.gitignore` vérifié (exclut `.venv`, `data/`, `build/`, `dist/`, secrets)
3. Créer le repo GitHub + `git push`
4. `python -m build` (sdist + wheel)
5. `twine upload dist/*` vers PyPI (token Riad)
6. `pip install reliability-gate` depuis PyPI → smoke test
7. Publier l'annonce (`announcement_draft.md`) — posts sous identité Riad

## Garde-fous permanents

- Aucune publication automatique. Chaque acte externe = GO explicite de Riad.
- Vérifier à chaque étape : pas de secret, pas de `.env`, pas de `data/` tenant dans le commit.
- Ne jamais inclure le serveur/core dans le package PyPI public (`reliability_gate` seulement, déjà configuré).
