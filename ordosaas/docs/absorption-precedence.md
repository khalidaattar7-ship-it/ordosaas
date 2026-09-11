# Revalidation de la matrice après l'absorption sur la précédence — D14

> Généré par `python -m tests.absorption_report` (livrable 3 de la session D14).

## Ce qui est comparé

L'absorption sur la cascade de précédence arrête la propagation dès que le
temps mort interne d'un job a épuisé le retard. Les cascades mesurées peuvent
donc se réduire. Ce rapport recalcule les 9 cellules en **cascade naturelle**
(bornes relâchées, comme la mesure d'origine) et les compare aux valeurs
publiées à la fin de la session D13.

## Résultat, cellule par cellule

| Densité | Perturbation | Avant D14 | Après D14 | Écart |
|---|---|---|---|---|
| dense | panne machine (M1, 20 u.) | 71 % | 71 % (5/7) | — |
| dense | job urgent (2 op.) | 12 % | 12 % (1/8) | — |
| dense | depassement duree (x1.5) | 100 % | 100 % (7/7) | — |
| moderee | panne machine (M1, 20 u.) | 29 % | 14 % (1/7) | **-15 pts** |
| moderee | job urgent (2 op.) | 38 % | 25 % (2/8) | **-13 pts** |
| moderee | depassement duree (x1.5) | 29 % | 14 % (1/7) | **-15 pts** |
| detendue | panne machine (M1, 20 u.) | 14 % | 14 % (1/7) | — |
| detendue | job urgent (2 op.) | 25 % | 25 % (2/8) | — |
| detendue | depassement duree (x1.5) | 14 % | 14 % (1/7) | — |

## Lecture

- **3 cellule(s) sur 9 ont changé.** Toutes dans le sens d'une RÉDUCTION : l'absorption ne peut, par construction, qu'arrêter la propagation plus tôt.

Moyenne par densité, avant → après :

- **dense** : 61 % → **61 %**
- **moderee** : 32 % → **18 %**
- **detendue** : 18 % → **18 %**

- La marge **réduit toujours** la cascade sur les aléas subis (panne : 71 % → 14 % → 14 % ; dépassement : 100 % → 14 % → 14 %).
- Sur les **insertions**, la marge n'aide toujours pas : job urgent à 12 % / 25 % / 25 % — la cellule la plus favorable reste le planning saturé.
- Le **seuil de repli** distingue toujours le planning dense des autres : il se déclenche sur ['dense'].
- En cascade naturelle, 0 cellule(s) restent tronquées (les bornes y sont relâchées, donc c'est attendu).

## Les conclusions qualitatives tiennent-elles ?

Elles ont été **revérifiées**, pas supposées :

1. **La marge aide sur les aléas subis** — toujours vrai, et l'écart reste net
   entre le planning saturé et les autres.
2. **La marge n'aide pas sur les insertions** — toujours vrai : le job urgent
   reste le moins coûteux sur le planning dense.
3. **Le seuil de repli distingue dense des autres** — toujours vrai.

**Une nuance nouvelle**, en revanche : modérée et détendue donnent désormais
des cascades **identiques**. Une fois qu'un planning comporte assez de marge
pour que la cascade converge d'elle-même, en ajouter davantage ne change plus
rien. L'effet de la densité n'est donc pas graduel — il y a un seuil, au-delà
duquel la marge supplémentaire est sans effet sur l'ampleur de la cascade.

C'est une information utile pour l'arbitrage produit encore ouvert : le coût
de la marge, lui, continue de croître linéairement.
