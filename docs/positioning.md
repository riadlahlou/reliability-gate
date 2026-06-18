# Positioning — ReliabilityGate

> Prototypé en interne sous le codename « Wayne Brain ». Nom public : **ReliabilityGate**.

## Architecture de marque

| Couche | Nom | Rôle |
|---|---|---|
| **Product / package / SDK** | **ReliabilityGate** | le nom public, le `pip install`, l'import `reliability_gate` |
| **Category** | **permission-to-act layer** | ce que c'est : une porte de décision, pas un dashboard |
| **Marketing label** | **Wayne Agent** | un agent qui tourne derrière ReliabilityGate (badge narratif, pas standard reconnu) |
| **Technical core** | CIS + abstention sélective + persistence baseline + commit/reveal | le moteur sous le capot |
| **Adoption path** | observe → advisory → soft gate → hard gate | on ne bloque rien au début |

> **Deux noms publics, pas trois.** ReliabilityGate (produit) et Wayne Agent (badge). « Wayne Brain » disparaît de la surface commerciale (codename interne / legacy uniquement).

## En une phrase

**An anti-gameable permission-to-act layer for autonomous agents** — il empêche un agent
d'agir quand sa fiabilité *mesurée* n'est pas suffisante. Pas un dashboard d'observabilité,
pas un détecteur d'hallucination : une **porte de décision**.

## Le problème

Les agents autonomes agissent avec une confiance constante, qu'ils aient zéro contexte ou dix
mille exemples. Ils ne savent pas ce qu'ils ne savent pas, et ne le disent jamais. Résultat :
ils agissent même quand ils sont peu fiables.

## La solution

Une boucle fermée **predict → observe → measure → calibrate** autour de n'importe quel agent,
produisant un score unique, le **Cognitive Integrity Score (CIS)**. CIS bas → l'agent ne doit
pas agir. CIS haut → décisions renforcées. Mesuré contre la réalité, pas auto-déclaré.

## Le concept « Wayne Agent »

Un **Wayne Agent** est un agent autonome connecté à ReliabilityGate : il n'est **pas fiable par
défaut**, il **mérite** le droit d'agir via fiabilité mesurée, abstention sélective, baseline
anti-gameable et commit/reveal. Message : *« upgrade your agent into a Wayne Agent »*.

⚠️ Cadrage honnête : « Wayne Agent » est un **label narratif**, pas un standard reconnu (0
adoption à ce jour). On le **sème**, on ne le présente pas comme une catégorie établie.

## Ce que ReliabilityGate N'EST PAS (cadrage honnête)

- ❌ une plateforme d'observabilité (Langfuse, Arize Phoenix, Braintrust)
- ❌ un détecteur d'hallucination généraliste (Galileo, Patronus, Cleanlab)
- ❌ « indispensable » / « personne ne fait ça » — le marché est **réel et encombré**
- ❌ « plus fiable que tout autre agent » — non prouvé, donc jamais affirmé

## Différenciateurs (tenus par le code, vérifiés)

- **Anti-gameable** : le skill est mesuré contre une baseline de **persistance** (répéter la
  dernière valeur) — impossible de gonfler le CIS sans réellement battre « ne rien faire ».
- **Abstention sélective** : récompense « agir quand on est fiable », **pénalise** l'agent
  imprudent (forte erreur + jamais d'abstention). *Composante vérifiée discriminante* (régression testée).
- **Commit/reveal** : une prédiction peut être verrouillée (hash) avant de connaître l'outcome —
  impossible à antidater.
- **Permission-to-act** : le CIS *gouverne* la décision suivante (`should_act` / `@guard`), il ne
  fait pas qu'observer.
- **Action-aware (V0 livré)** : `should_act(action="send_email", risk_level="customer_visible")`
  renvoie une `ReliabilityDecision` — l'agent doit avoir mérité le droit d'exécuter *cette action*,
  pas seulement être fiable globalement. Croise score global + score action-spécifique + taille
  d'échantillon vs requis ; un risque plus élevé exige plus de preuves action-spécifiques. La démo
  `demo_action_gating.py` est soutenue littéralement par le code (aucune API marketing inexistante).

## Observe first, gate later (advisory usage)

Les devs acceptent l'observabilité, résistent au hard-gating. Donc l'adoption commence en
**advisory** : on logge le verdict (`should_act()` / `cis()` / `@guard(on_abstain="log")`) sans
l'appliquer, puis on passe en soft gate (`on_abstain="none"`) puis en hard gate (`raise`) une fois
le signal de confiance établi.

> Honnêteté code : il n'y a **pas** de toggle « observe mode » séparé. L'usage advisory = appeler
> le verdict et choisir de ne pas l'imposer. Pas présenté comme une feature inexistante.

## Complément, pas remplacement

Les plateformes d'observabilité/eval disent *ce qui s'est passé* ; ReliabilityGate décide *si
l'agent doit agir ensuite*. Elles sont en amont, ReliabilityGate à la porte de décision.
**Beaucoup d'équipes feront tourner les deux.** ReliabilityGate vit en étant plus tranchant sur un
créneau étroit, pas en prétendant l'espace vide.

## Marché (sourcé)

Marché LLM observability ~**2,69 Md$ en 2026**, CAGR ~**36%** (ResearchAndMarkets) ; Gartner
prévoit une forte montée de l'observabilité IA d'ici 2028. → le **besoin de catégorie** est validé ;
la dépendance à *ce* produit (« indispensable ») reste, elle, à prouver par l'adoption.

## ICP (hypothèse, non validée)

Équipes déployant des **agents autonomes en production** (multi-agents, tool-use) qui ont besoin
d'une porte de fiabilité avant d'agir — pas seulement de logs. À valider par les premiers retours.
