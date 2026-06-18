# ReliabilityGate — Technical FAQ (honest)

> **Note interne (à NE PAS publier telle quelle) :** ce document a deux usages.
> (1) Pour Riad : les questions qu'un builder crédible posera, avec une réponse
> que tu peux **tenir sans bluffer**. Tu n'as pas à tout maîtriser — tu dois
> connaître ces réponses, *y compris les limites assumées*. Dire « ça, c'est une
> limite connue de la V0 » est plus crédible que feindre la maîtrise.
> (2) Le corps ci-dessous (à partir de « ## 1. ») est **publiable** tel quel
> (FAQ/`docs/`) — licence tranchée : Apache-2.0. Aucun chiffre marché non sourcé ;
> les nombres cités sont les **constantes réelles du code**, pas des affirmations
> externes.
>
> Règle de posture quand on te pousse au-delà de ce que tu sais :
> *« Bonne question — le détail exact est dans `storage/cis_engine.py` /
> `reliability_gate/decision.py` ; en court, c'est ceci… et voici la limite. »*
> Pointer vers du vrai code est une réponse légitime.

---

## 1. En une phrase, ça fait quoi ?

ReliabilityGate mesure, dans le temps, **si les prédictions d'un agent collent à
la réalité observée**, en tire un score (le **CIS**, Cognitive Integrity Score),
et s'en sert pour décider si l'agent a *mérité le droit d'exécuter une action
donnée*. C'est une **porte de décision** (permission-to-act), pas un dashboard et
pas un détecteur d'hallucination.

## 2. Qu'est-ce que le CIS mesure exactement ?

Une formule à 4 composantes (poids dans `storage/cis_engine.py`) :

```
CIS = 0.40 × mae_score      # erreur de prédiction vs réalité (calibration)
    + 0.25 × abstention_score # agit quand fiable / se tait quand il ne sait pas
    + 0.20 × skill_score     # bat la baseline naïve "répéter la dernière valeur"
    + 0.15 × falsif_score    # peu d'erreurs catastrophiques
```

Bandes : `[0.85,1]` trusted · `[0.65,0.85)` calibrated · `[0.40,0.65)` learning ·
`[0,0.40)` unreliable. Minimum 3 outcomes pour produire un score ; fenêtre
glissante de 20 outcomes récents.

## 3. ⭐ LA question : qu'est-ce que je donne à `observe()` pour une vraie action, et d'où vient la « vérité-terrain » ?

**Réponse honnête — c'est la friction principale, autant la dire franchement.**

Le signal de fiabilité est de la **calibration de prédiction numérique** :
l'agent produit une `prediction` (échelle 0-100), tu lui fournis ensuite la
valeur réelle `actual` (0-100), et ReliabilityGate mesure l'écart au fil du temps.

```python
gate.observe(prediction=80.0, actual=78.0, action="send_email")
```

Donc pour une action comme `send_email`, **tu dois définir un outcome mesurable
sur 0-100** et le fournir toi-même. ReliabilityGate **ne sait pas magiquement**
si un email était « bon ». Il mesure si l'auto-évaluation de l'agent correspond à
une vérité-terrain *que tu produis*.

Ça marche le mieux là où tu as déjà — ou peux produire à faible coût — un
**chiffre de vérité-terrain par action** :

| Domaine | `prediction` de l'agent | `actual` que tu observes |
|---|---|---|
| Email/outreach | score de qualité/déliverabilité estimé | taux d'ouverture/réponse réel, ou score humain |
| Support | probabilité de résolution | résolu / CSAT réel |
| Finance | prévision (revenu, risque) | valeur réalisée |
| SRE | sévérité/ETA estimé | impact/temps réel |

**Limite assumée :** pour une action *sans* outcome numérique naturel, c'est à
**toi** de définir un proxy (ex. un score de qualité a posteriori). Si tu ne peux
pas produire de vérité-terrain pour une action, ReliabilityGate n'a rien à
calibrer dessus — et il le dit (`not enough action-specific outcomes yet`) au
lieu de prétendre savoir.

## 4. Comment le verdict action-aware est-il calculé ?

Logique pure dans `reliability_gate/decision.py::decide()`, dans cet ordre :

1. **Agent globalement peu fiable (CIS < 0.40) + action risquée → blocage dur.**
   Il n'a pas mérité l'autonomie sur du risqué.
2. **Pas assez d'outcomes action-spécifiques** (vs le seuil du `risk_level`) →
   `gather_more_data`. **Jamais** un faux ALLOW.
3. **Assez de preuves + score d'action ≥ 0.65 → ALLOW.**
4. Assez de preuves mais score faible → blocage (dur si l'agent est globalement
   sous 0.40, sinon souple).

`risk_level` règle l'exigence de preuves : `low`=3, `normal`=5,
`customer_visible`=10, `destructive`/`financial`/`high`/`irreversible`=20 ;
**risque inconnu → traité comme le plus strict (fail-closed).**

> Question piège fréquente : *« c'est bloqué parce que l'agent est globalement
> mauvais ou parce que `send_email` a spécifiquement échoué ? »* — Réponse :
> en V0, la règle 1 bloque sur le score **global** ; le score **action-spécifique**
> joue aux règles 3-4. Les deux signaux sont distincts et exposés
> (`cis_score` vs `action_score`).

## 5. `allow` veut-il dire « safe » ?

**Non — et c'est explicite.** `allow` (= `enforced_allow`) est la décision
*effective selon le mode d'enforcement* :

- `observe` / `advisory` : `allow` est **toujours True** → « non-enforced », **pas**
  « safe ». L'avis réel du gate est dans `recommended_allow` / `recommendation`.
- `hard_gate` : `allow` suit le verdict (peut être False).

```python
d = gate.should_act(action="send_email", risk_level="customer_visible",
                    enforcement_mode="advisory")
d.allow              # True  → advisory ne bloque pas (pas une garantie de sûreté)
d.recommended_allow  # False → le gate recommande de NE PAS agir
```

Pour **enforcer**, mets `enforcement_mode="hard_gate"`. Pour lire l'**avis**,
utilise `recommended_allow`. C'est documenté pour qu'un `if decision.allow:` naïf
en advisory ne soit pas une surprise : advisory recommande, il ne bloque pas.

## 6. « Anti-gameable » — vraiment ?

Trois mécanismes concrets, pas un slogan :

- **Baseline de persistance** : le `skill_score` compare l'agent à « répéter la
  dernière valeur ». Impossible de gonfler le score sans réellement battre « ne
  rien faire ».
- **Abstention sélective** : récompense « agir quand fiable », **pénalise**
  l'agent qui agit avec confiance *en se trompant* sans jamais s'abstenir
  (cf. `_abstention_score`).
- **Commit/reveal** : `commit()` verrouille un hash `SHA-256(prediction|nonce)`
  *avant* de connaître le résultat ; `reveal()` vérifie le hash → pas
  d'antidatage.

**Limite honnête :** « anti-gameable » porte sur le *scoring*. Ça n'empêche pas
quelqu'un qui contrôle le pipeline d'injecter de faux `actual`. C'est une aide à
la gouvernance, pas une preuve cryptographique de la réalité des outcomes.

## 7. En quoi est-ce différent de Langfuse / Arize / Galileo / Cleanlab ?

Elles disent **ce qui s'est passé** (traces, evals, dashboards). ReliabilityGate
décide **si l'agent doit agir maintenant**. Elles sont en amont (observabilité),
lui à la **porte de décision**. **Complément, pas remplacement** — beaucoup
d'équipes feront tourner les deux. Le marché de la fiabilité des agents est réel
et encombré ; ReliabilityGate vit en étant **plus tranchant sur un créneau
étroit**, pas en prétendant l'espace vide.

## 8. Les seuils (0.40, 0.65, tailles d'échantillon) sont-ils calibrés empiriquement ?

**Non. Ce sont des défauts V0, pas des valeurs validées sur données.** Les bandes
CIS reprennent les seuils canoniques du moteur ; les tailles d'échantillon par
risque sont des points de départ raisonnables. Ils sont **faits pour être ajustés**
avec de l'usage réel. Le dire est plus crédible que prétendre une calibration
qu'on n'a pas.

## 9. Est-ce une frontière de sécurité ?

**Non.** En V0, la logique de décision est **côté client** : un appelant
déterminé peut l'ignorer. C'est une **aide à la gouvernance** (décider/router/
logguer), pas un sandbox qui empêche techniquement une action. À traiter comme un
garde-fou, pas comme un contrôle d'accès.

## 10. Mes données partent-elles chez vous ?

**Non. Zéro télémétrie par défaut.** Tout tourne en local ; les outcomes sont
stockés par tenant dans `data/{tenant}/outcomes.jsonl`, chez toi. Il n'y a
*aucun* code d'envoi de données vers l'extérieur. Pas de prompts, pas de payloads,
pas de données client qui sortent.

## 11. Empreinte / dépendances ?

Le client (`reliability_gate/`) a **zéro dépendance requise** (utilise `httpx`
s'il est présent, sinon `urllib` de la stdlib). Le serveur de référence
(FastAPI, optionnel) tourne en local sur le port 8001. Aucune dépendance à un
quelconque code privé tiers.

## 12. Limites connues (consolidées, V0)

- Le signal est de la **calibration numérique** : il faut une vérité-terrain 0-100
  par action (cf. §3) — c'est sur l'utilisateur.
- Ce n'est **pas** un classifieur de contenu/sûreté : il ne « lit » pas l'email,
  il calibre des prédictions dans le temps.
- Seuils **non calibrés empiriquement** (§8).
- Décision **côté client**, pas une frontière de sécurité (§9).
- Fenêtre de 20 outcomes : seul le passé récent compte.
- Multi-tenant = clé API comme tenant (MVP, pas une vraie auth).
- Marché **encombré** : complément, pas « personne ne fait ça ».

## 13. Qui a construit ça, et comment ?

Construit par un fondateur solo **avec une forte assistance IA**, pas par une
équipe d'ingénieurs. C'est assumé et cohérent avec le produit : un outil qui dit
*« ne te déclare pas fiable, prouve-le »* est lancé par quelqu'un qui ne
sur-déclare pas non plus son expertise. Le code, les tests et la démo sont réels
et vérifiables — c'est ce qui compte pour un dev tool. Je cherche justement des
relecteurs techniques pour le challenger.

## 14. Ce que la V0 N'EST PAS (roadmap honnête)

Pas de dashboard, pas de version hébergée, pas de télémétrie, pas de policy engine
complexe, pas de module entreprise. V0 = un noyau étroit : mesurer la fiabilité
réelle d'un agent et gouverner *par action* le droit d'agir. La suite dépendra de
l'usage réel et des retours — pas d'une feuille de route fantasmée.
