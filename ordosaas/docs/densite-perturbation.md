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
| dense | 1.0 | 674 | 68.6 % | 240 | M1:0 M2:70 M3:170 | 3012.84 | 8/10 |
| moderee | 1.4 | 916 | 50.5 % | 792 | M1:169 M2:264 M3:359 | 3764.71 | 7/10 |
| detendue | 2.0 | 1278 | 36.2 % | 1616 | M1:422 M2:553 M3:641 | 4961.98 | 7/10 |

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
| dense | 68.6 % | panne machine (M1, 20 u.) | 2 | 8 | 25 % | **oui** | non | 2 | oui |
| dense | 68.6 % | job urgent (2 op.) | 2 | 9 | 22 % | **oui** | non | 2 | oui |
| dense | 68.6 % | depassement duree (x1.5) | 2 | 8 | 25 % | **oui** | non | 2 | oui |
| moderee | 50.5 % | panne machine (M1, 20 u.) | 1 | 8 | 12 % | **oui** | non | 1 | oui |
| moderee | 50.5 % | job urgent (2 op.) | 2 | 9 | 22 % | **oui** | non | 2 | oui |
| moderee | 50.5 % | depassement duree (x1.5) | 2 | 8 | 25 % | **oui** | non | 2 | oui |
| detendue | 36.2 % | panne machine (M1, 20 u.) | 1 | 8 | 12 % | **oui** | non | 1 | oui |
| detendue | 36.2 % | job urgent (2 op.) | 1 | 9 | 11 % | non | non | 1 | oui |
| detendue | 36.2 % | depassement duree (x1.5) | 1 | 8 | 12 % | non | non | 1 | oui |

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
| dense | 68.6 % | panne machine (M1, 20 u.) | 4 | 8 | 50 % | non | non | 4 | oui |
| dense | 68.6 % | job urgent (2 op.) | 7 | 9 | 78 % | non | **oui** | 7 | oui |
| dense | 68.6 % | depassement duree (x1.5) | 6 | 8 | 75 % | non | **oui** | 6 | oui |
| moderee | 50.5 % | panne machine (M1, 20 u.) | 2 | 8 | 25 % | non | non | 2 | oui |
| moderee | 50.5 % | job urgent (2 op.) | 3 | 9 | 33 % | non | non | 3 | oui |
| moderee | 50.5 % | depassement duree (x1.5) | 2 | 8 | 25 % | non | non | 2 | oui |
| detendue | 36.2 % | panne machine (M1, 20 u.) | 1 | 8 | 12 % | non | non | 1 | oui |
| detendue | 36.2 % | job urgent (2 op.) | 1 | 9 | 11 % | non | non | 1 | oui |
| detendue | 36.2 % | depassement duree (x1.5) | 1 | 8 | 12 % | non | non | 1 | oui |

## Lecture

**Régime production** :

- **dense** (68.6 % d'utilisation) : part des jobs futurs touchés de 22 % à 25 %, 0 repli(s) et 3 zone(s) tronquée(s) sur 3 perturbation(s).
- **moderee** (50.5 % d'utilisation) : part des jobs futurs touchés de 12 % à 25 %, 0 repli(s) et 3 zone(s) tronquée(s) sur 3 perturbation(s).
- **detendue** (36.2 % d'utilisation) : part des jobs futurs touchés de 11 % à 12 %, 0 repli(s) et 1 zone(s) tronquée(s) sur 3 perturbation(s).

**Régime cascade_naturelle** :

- **dense** (68.6 % d'utilisation) : part des jobs futurs touchés de 50 % à 78 %, 2 repli(s) et 0 zone(s) tronquée(s) sur 3 perturbation(s).
- **moderee** (50.5 % d'utilisation) : part des jobs futurs touchés de 25 % à 33 %, 0 repli(s) et 0 zone(s) tronquée(s) sur 3 perturbation(s).
- **detendue** (36.2 % d'utilisation) : part des jobs futurs touchés de 11 % à 12 %, 0 repli(s) et 0 zone(s) tronquée(s) sur 3 perturbation(s).

- En cascade naturelle, la part moyenne des jobs futurs touchés diminue entre la variante *dense* (68 %) et la variante *detendue* (12 %).
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
