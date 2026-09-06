# Densité du planning × perturbation — réordonnancement incrémental

> Généré par `python -m tests.densite_report` (livrable 2 de la Discussion 2).
> **Document exploratoire et descriptif** : il fournit les données factuelles
> de la question produit restée ouverte, il ne la tranche pas.

## Les trois variantes

Obtenues en étirant le planning CP-SAT optimal d'un facteur `s` : toutes les
dates de début (opérations et setups) sont multipliées par `s`, les durées
restent inchangées, les deadlines suivent le même facteur. Voir
`tests/densite_variants.py` pour la justification de ce levier — desserrer les
deadlines ou raccourcir les durées ne change **pas** la densité sur cette
instance, et réduire le nombre de jobs fausserait les pourcentages.

| Densité | Facteur `s` | Horizon | Utilisation machine | Temps mort interne | Détail par machine | TWT | Jobs en retard |
|---|---|---|---|---|---|---|---|
| dense | 1.0 | 673 | 88.3 % | 45 | M1:0 M2:43 M3:2 | 4422.64 | 8/10 |
| moderee | 1.4 | 937 | 69.1 % | 553 | M1:162 M2:246 M3:145 | 5619.86 | 8/10 |
| detendue | 2.0 | 1332 | 54.5 % | 1322 | M1:411 M2:550 M3:361 | 7415.40 | 8/10 |

Le temps mort compté est **interne** — les trous entre deux occupations
consécutives d'une machine. C'est lui, et lui seul, qui peut absorber un retard.
Noter qu'en variante dense, la machine goulot M1 a **zéro** temps mort : elle est
saturée, donc structurellement incapable d'absorber quoi que ce soit.

## Protocole

Perturbations appliquées en valeur **absolue**, identiques d'une variante à
l'autre : panne de 20 unités sur la machine goulot, job urgent de
2 opérations, dépassement de durée ×1.5. T_now = un tiers de
l'horizon de la variante. C'est le cœur de la mesure : une panne de 20 unités
reste une panne de 20 unités, que le planificateur se soit gardé de la marge ou
non — la question posée est donc bien « cette marge absorbe-t-elle la
perturbation ? ».

Deux régimes de bornes sont mesurés séparément, et c'est **indispensable** pour
lire les chiffres correctement.

## Régime 1 — comportement de production (bornes relatives par défaut, cf. D7)

Ce que fera réellement le worker : bornes à 0.15 de l'horizon restant et 0.20
des jobs futurs.

| Densité | Utilisation | Perturbation | Jobs zone | Jobs futurs | % futurs touchés | Zone tronquée | Repli déclenché | Jobs replanifiés | Planning valide |
|---|---|---|---|---|---|---|---|---|---|
| dense | 88.3 % | panne machine (M1, 20 u.) | 2 | 7 | 29 % | **oui** | non | 2 | oui |
| dense | 88.3 % | job urgent (2 op.) | 1 | 8 | 12 % | non | non | 1 | oui |
| dense | 88.3 % | depassement duree (x1.5) | 2 | 7 | 29 % | **oui** | non | 2 | oui |
| moderee | 69.1 % | panne machine (M1, 20 u.) | 2 | 7 | 29 % | **oui** | non | 2 | oui |
| moderee | 69.1 % | job urgent (2 op.) | 1 | 8 | 12 % | non | non | 1 | oui |
| moderee | 69.1 % | depassement duree (x1.5) | 2 | 7 | 29 % | **oui** | non | 2 | oui |
| detendue | 54.5 % | panne machine (M1, 20 u.) | 1 | 7 | 14 % | **oui** | non | 1 | oui |
| detendue | 54.5 % | job urgent (2 op.) | 1 | 8 | 12 % | non | non | 1 | oui |
| detendue | 54.5 % | depassement duree (x1.5) | 1 | 7 | 14 % | **oui** | non | 1 | oui |

**Lecture — attention au piège.** Avec 8 à 9 jobs futurs, le plafond relatif de
0.20 vaut 1 à 2 jobs. La zone est donc **tronquée par le plafond dans presque
toutes les cellules**, quelle que soit la densité. Ce régime montre que
l'incrémental reste borné et que le garde-fou ne se déclenche jamais — mais il
ne dit **rien** sur l'effet de la densité, que le plafond masque entièrement.
C'est le régime 2 qui répond à cette question.

## Régime 2 — cascade naturelle (bornes relâchées)

Bornes volontairement relevées (`search_horizon=10 000`,
`max_impacted_jobs=50`) pour observer jusqu'où la perturbation se propage
réellement. C'est cette propagation-là que la densité influence, et c'est elle
qui détermine si le seuil de repli serait franchi sans plafond.

| Densité | Utilisation | Perturbation | Jobs zone | Jobs futurs | % futurs touchés | Zone tronquée | Repli déclenché | Jobs replanifiés | Planning valide |
|---|---|---|---|---|---|---|---|---|---|
| dense | 88.3 % | panne machine (M1, 20 u.) | 5 | 7 | 71 % | non | **oui** | 5 | oui |
| dense | 88.3 % | job urgent (2 op.) | 1 | 8 | 12 % | non | non | 1 | oui |
| dense | 88.3 % | depassement duree (x1.5) | 7 | 7 | 100 % | non | **oui** | 5 | oui |
| moderee | 69.1 % | panne machine (M1, 20 u.) | 3 | 7 | 43 % | non | non | 3 | oui |
| moderee | 69.1 % | job urgent (2 op.) | 1 | 8 | 12 % | non | non | 1 | oui |
| moderee | 69.1 % | depassement duree (x1.5) | 3 | 7 | 43 % | non | non | 3 | oui |
| detendue | 54.5 % | panne machine (M1, 20 u.) | 3 | 7 | 43 % | non | non | 3 | oui |
| detendue | 54.5 % | job urgent (2 op.) | 1 | 8 | 12 % | non | non | 1 | oui |
| detendue | 54.5 % | depassement duree (x1.5) | 1 | 7 | 14 % | non | non | 1 | oui |

## Lecture

**Régime production** :

- **dense** (88.3 % d'utilisation) : part des jobs futurs touchés de 12 % à 29 %, 0 repli(s) et 2 zone(s) tronquée(s) sur 3 perturbation(s).
- **moderee** (69.1 % d'utilisation) : part des jobs futurs touchés de 12 % à 29 %, 0 repli(s) et 2 zone(s) tronquée(s) sur 3 perturbation(s).
- **detendue** (54.5 % d'utilisation) : part des jobs futurs touchés de 12 % à 14 %, 0 repli(s) et 2 zone(s) tronquée(s) sur 3 perturbation(s).

**Régime cascade_naturelle** :

- **dense** (88.3 % d'utilisation) : part des jobs futurs touchés de 12 % à 100 %, 2 repli(s) et 0 zone(s) tronquée(s) sur 3 perturbation(s).
- **moderee** (69.1 % d'utilisation) : part des jobs futurs touchés de 12 % à 43 %, 0 repli(s) et 0 zone(s) tronquée(s) sur 3 perturbation(s).
- **detendue** (54.5 % d'utilisation) : part des jobs futurs touchés de 12 % à 43 %, 0 repli(s) et 0 zone(s) tronquée(s) sur 3 perturbation(s).

- En cascade naturelle, la part moyenne des jobs futurs touchés diminue entre la variante *dense* (61 %) et la variante *detendue* (23 %).
- Tous les plannings fusionnés sont valides, dans les deux régimes et à toutes les densités : la cascade reste correcte y compris sur des zones larges non tronquées.

## Ce que ce rapport ne dit pas

Il ne tranche pas entre **conserver de la marge à l'optimisation initiale** et
**relever le seuil de repli**. Les deux lectures restent ouvertes :

- garder de la marge a un coût direct et chiffrable — l'horizon s'allonge et le
  retard pondéré augmente, ce que la colonne TWT du premier tableau quantifie ;
- relever le seuil ne coûte rien à l'optimisation initiale, mais fait tourner
  l'incrémental sur des zones plus larges, là où une résolution complète serait
  peut-être plus pertinente.

Une troisième lecture apparaît dans les chiffres et mérite d'être posée : le
plafond relatif de D7 borne déjà la zone bien avant que le seuil de repli n'entre
en jeu. Sur cette instance, le garde-fou de repli ne se déclenche donc jamais en
régime de production — ce qui interroge son rôle réel, sans que ce rapport
tranche non plus cette question.

Le choix appartient à Khalid.
