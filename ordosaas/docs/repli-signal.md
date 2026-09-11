# Validation du signal de repli — D13

> Généré par `python -m tests.repli_report` (livrable 3 de la session D13).

## La question posée

D7 borne la recherche à 20 % des jobs futurs ; H5 déclenche le repli à 50 %.
**20 % < 50 %** : le plafond coupait donc toujours la zone avant que le seuil
puisse la voir. Des cascades réelles de 71 % et 100 % passaient inaperçues.

Ce rapport vérifie que le signal de troncature active (D13) déclenche
désormais le repli là où la cascade réelle le justifie — **et seulement là**.

## Résultat, cellule par cellule

| Densité | Perturbation | Cascade naturelle | Zone en production | Tronquée | Propagation active | AVANT D13 | APRÈS D13 |
|---|---|---|---|---|---|---|---|
| dense | panne machine (M1, 20 u.) | 5/7 — **71 %** | 2/7 — 29 % | oui | **oui** | non | **oui** |
| dense | job urgent (2 op.) | 1/8 — **12 %** | 1/8 — 12 % | non | non | non | non |
| dense | depassement duree (x1.5) | 7/7 — **100 %** | 2/7 — 29 % | oui | **oui** | non | **oui** |
| moderee | panne machine (M1, 20 u.) | 1/7 — **14 %** | 1/7 — 14 % | non | non | non | non |
| moderee | job urgent (2 op.) | 2/8 — **25 %** | 2/8 — 25 % | non | non | non | non |
| moderee | depassement duree (x1.5) | 1/7 — **14 %** | 1/7 — 14 % | non | non | non | non |
| detendue | panne machine (M1, 20 u.) | 1/7 — **14 %** | 1/7 — 14 % | non | non | non | non |
| detendue | job urgent (2 op.) | 2/8 — **25 %** | 2/8 — 25 % | non | non | non | non |
| detendue | depassement duree (x1.5) | 1/7 — **14 %** | 1/7 — 14 % | non | non | non | non |

## Lecture

- **Avant D13** : 0 cellule(s) sur 9 déclenchaient le repli en production. C'est le défaut : structurellement impossible tant que le plafond de D7 (20 %) reste sous le seuil de H5 (50 %).
- **Après D13** : 2 cellule(s) sur 9 le déclenchent.

Cellules qui déclenchent désormais le repli :

- `dense / panne machine (M1, 20 u.)` — cascade réelle **71 %** des jobs futurs, zone tronquée à 29 % en production.
- `dense / depassement duree (x1.5)` — cascade réelle **100 %** des jobs futurs, zone tronquée à 29 % en production.

**Le signal correspond exactement à l'attente qualitative** : il se déclenche sur les cellules — et uniquement celles — dont la cascade réelle dépasse le seuil de repli, alors même que la zone mesurée en production reste très en-dessous.
