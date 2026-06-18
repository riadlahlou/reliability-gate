# Risk Register — ReliabilityGate (pré-lancement)

> Nom public : **ReliabilityGate** (codename interne / legacy : « Wayne Brain »).

| # | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Marché encombré** (Galileo, Arize, Langfuse, Patronus, Cleanlab, Braintrust, certains financés + foundation models) | élevée | élevé | Positionnement étroit et tranchant (porte de décision / permission-to-act anti-gameable), pas frontal ; complément, pas remplacement |
| 2 | **Demande non prouvée** — « indispensable » est une hypothèse, 0 utilisateur | élevée | élevé | Lancer en awareness-first + advisory (observe first, gate later) ; mesurer l'adoption réelle avant d'investir ; ne rien affirmer sur la demande |
| 3 | **Licence irréversible** mal choisie | ~~moyenne~~ → **résolu** | élevé | **Tranché : Apache-2.0** appliqué (adoption first). Texte officiel Apache 2.0 dans `LICENSE`. cf. `license_decision.md` |
| 4 | **Exposition publique de l'identité de Riad** (repo, posts) | certaine si lancement | moyen | Décision consciente de Riad ; séparé de Wayne OS (privé) |
| 5 | **Fuite de secret / `.env` / data tenant** dans le repo/package | faible | critique | Wheel ne ship que `reliability_gate/` (vérifié) ; audit no-secret ; `.gitignore` à vérifier avant push |
| 6 | **Couplage résiduel Wayne OS** | faible | moyen | Vérifié : 0 `import wayne` ; entry-point `wayne.apps` retiré ; commentaires citant l'ADN doctrinal = cosmétique |
| 7 | **Sur-promesse abstention** (le claim que le code ne tient pas) | faible (corrigé) | élevé | Composante abstention rendue discriminante + tests de régression ; README explique « selective abstention » |
| 8 | **Bug packaging** (entry-point mort, module exclu, mauvais package shippé) | faible (corrigé) | moyen | Entry-point `api.main:app` retiré ; ship `reliability_gate` only ; build + install propre vérifiés |
| 9 | **Chiffres marché non sourcés** dans la com | moyenne | moyen | N'utiliser que des chiffres sourcés (ResearchAndMarkets, Gartner) ; éviter le nombre « $1.4B » non vérifié |
| 10 | **CIS limité aux "loop cells"** (modèle de données reality_cycle) | moyenne | moyen | L'API `/observe` gère l'ingestion ; documenter clairement le modèle attendu ; ne pas survendre le « drop-in » |
| 11 | **Maintenance solo** (issues, support) après awareness | moyenne | moyen | Cadrer le scope « narrow gate », pas une plateforme ; attentes réalistes en README |
| 12 | **Nom « ReliabilityGate » descriptif → marque faible** (terme SRE/quality-gate générique, peu défendable juridiquement) | moyenne | faible-moyen | Accepté comme compromis dispo+clair ; possible re-coin distinctif plus tard si traction ; pas un bloqueur de lancement |
| 13 | **Label « Wayne Agent » sur-vendu** comme standard reconnu alors que 0 adoption | moyenne | moyen | Toujours cadrer « label narratif, pas standard » ; sème le concept, ne l'affirme pas. Risque trademark « Wayne » (Wayne Enterprises/DC) en marque *publique* → garder ReliabilityGate comme raison sociale, Wayne Agent comme badge |

## Risques de lancement à NE PAS prendre

- ❌ Publier avec un pitch « personne ne fait ça » / « indispensable » (faux, vérifié).
- ❌ Présenter « Wayne Agent » comme une catégorie/standard déjà reconnu.
- ❌ Publier le serveur/core complet sur PyPI (client `reliability_gate` seulement).
- ❌ Appliquer une licence sans relecture du texte légal.
- ❌ Laisser un secret/`.env`/`data/` entrer dans le repo.
