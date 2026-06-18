# Décision de licence — ReliabilityGate

> Nom public : **ReliabilityGate** (codename interne / legacy : « Wayne Brain »).

## ✅ DÉCISION TRANCHÉE (Riad, 2026-06-18) : **Apache-2.0**

Licence **appliquée** : `LICENSE` (texte officiel Apache 2.0, © 2026 Riad Lahlou) ;
`pyproject.toml` (`license = {text = "Apache-2.0"}` + classifier OSI) ; README mis à jour.
`LICENSE.proposed` supprimé.

**Raison du choix (vs BSL recommandé ci-dessous) :** l'objectif immédiat est
**l'adoption**, pas la protection maximale contre la copie. Apache-2.0 maximise
l'adoption dev (permissive, clause brevets, standard reconnu). La protection
commerciale (BSL/hosted) pourra venir *après* traction, sur une couche séparée —
pas en bridant l'adoption du cœur open-source aujourd'hui.

> L'analyse comparative ci-dessous est conservée comme historique de décision.

---

> Décision **Level C, quasi-irréversible** : une fois une version publiée sous une licence,
> on ne peut pas la retirer pour cette version. À trancher par Riad avant tout lancement.
> Aucune licence n'est appliquée aujourd'hui (cf. `LICENSE.proposed`).

## Les 3 options

| Option | Ce que les autres peuvent faire | Protection commerciale | Adoption | Qui l'utilise |
|---|---|---|---|---|
| **Apache 2.0** | tout, y compris vendre une version concurrente | ❌ aucune | maximale | Kubernetes, TensorFlow |
| **BSL 1.1** | lire, tester, usage interne/non-prod ; prod commerciale → contacter le Licensor ; passe en Apache 2.0 après N ans | ✅ pendant la fenêtre | forte (code lisible) | Sentry, CockroachDB, Arize Phoenix |
| **Propriétaire** | rien sans accord écrit | ✅ totale | faible (les devs n'adoptent pas) | SaaS fermés |

## Recommandation : **BSL 1.1**

- **Adoption + protection** : les devs peuvent lire/tester (objectif awareness), mais un gros
  acteur ne peut pas reprendre le code en production commerciale sans contacter Riad → pipeline de leads.
- **Pas de vendor lock-in** : passage automatique en Apache 2.0 après la Change Date (rassure la communauté).
- **Précédent crédible** : Sentry, CockroachDB, Arize Phoenix l'utilisent.
- **Cohérent** avec un fondateur solo, sans VC derrière, sur un marché encombré.

## Paramètres BSL à fixer (par Riad)

- Licensor : Riad Lahlou
- Additional Use Grant : non-production / interne / évaluation
- Change Date : 3 ans après publication (valeur à confirmer)
- Change License : Apache 2.0

## Limites honnêtes

- Certains puristes open-source boudent la BSL (mais l'usage s'est normalisé).
- Le **texte juridique** doit être copié depuis la source officielle MariaDB BSL 1.1 et,
  idéalement, **relu par un juriste** avant application — je ne fournis pas de texte légal vérifié.
- Apache 2.0 reste une alternative valable si l'objectif est purement l'adoption et que la
  protection commerciale n'est pas prioritaire.

## Action requise

→ Riad tranche : **BSL 1.1** (recommandé) / Apache 2.0 / propriétaire.
Tant que non tranché, le fichier reste `LICENSE.proposed` et rien n'est publié.
