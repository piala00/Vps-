# État comparatif et rapprochement des ventes CR / Sage

## Contenu (modèle de la feuille RECAP du rapport commercial)
Un grand tableau par mois, une ligne par jour :

| Colonne | Calcul |
|---|---|
| VENTE COMPTANT | somme de la colonne H (FACTURE COMPTANT) des lignes du CR |
| VENTE À CRÉDIT | somme de la colonne I (FACTURE VAT, ventes en compte / BP) |
| TOTAL VENTES | vente comptant + vente à crédit (= cellule du CR qui calcule la vente totale, 2ᵉ ligne « TOTAL VENTES ») |
| RECOUVREMENTS | somme des reçus (RECOUVREMENTS) |
| **RECETTE TOTALE** | **recouvrements + vente comptant** (règle GTC) |

**L'état comparatif s'arrête à la RECETTE TOTALE.** Le rapprochement avec Sage et les contrôles sont présentés à part :
onglet « Rapprochement des ventes avec Sage » dans l'application, et feuilles `RAPPROCHEMENT VENTES SAGE` et
`CONTROLES` dans l'export Excel (TOTAL M-1 saisi dans RECAP comparé au M-1 calculé, acompte du mois, cellule
« vente totale » du CR).

Puis, comme dans RECAP : **TOTAL M**, **TOTAL M-1** (calculé sur le mois précédent chargé), **ÉVOLUTION**, **TOTAL N-1**
(calculé si l'année précédente est chargée, sinon repris de la ligne saisie dans RECAP, avec la mention « saisi dans
RECAP »), **ÉCART N-(N-1)**.

> Le modèle RECAP actuel calcule `RECETTE = ACOMPTE + RECOUVREMENTS`. La règle demandée par la comptabilité est
> `RECOUVREMENTS + VENTE COMPTANT`. Le paramètre `etat_comparatif.recette` permet de revenir à la formule du modèle
> (`"acompte+recouvrement"`).

## Modèle « ETAT CHIFFRE D'AFFAIRE » (feuilles mensuelles de l'export)
Chaque mois est exporté au format exact de l'état fourni par la comptabilité (exemples 2025) :
- titre `ETAT CHIFFRE D'AFFAIRE MOIS <MOIS> <ANNEE>` (A1:G1), en-têtes `DATES` / `CHIFFRE D'AFFAIRE` ;
- colonnes `TOTAL`, `COMPTANT`, `CREDIT`, `RECOUVREMENT`, `TOTAL RECETTE` ;
- une ligne par jour du mois (jours sans CR à zéro) ; formules Excel vivantes : `CREDIT = TOTAL - COMPTANT`,
  `TOTAL RECETTE = COMPTANT + RECOUVREMENT`, `TOTAL = SOMME` ;
- lignes de pied : `TOTAL`, `Total <mois-1>`, `VARIATION`, `Total <mois> <année-1>`, `VARIATION`,
  `CREANCE AU <fin du mois>`, `CREANCE AU <fin du mois précédent>`, `VARIATION`.

Le Total M-1 et le Total N-1 sont **calculés** à partir des mois chargés ; à défaut, le N-1 saisi (RECAP ou état
importé) est repris avec la mention « (saisi) ». Les **créances** sont calculées : somme des soldes Sage en fin de
mois (lecture seule), sinon somme des fiches clients si tous les soldes d'ouverture sont connus, sinon `n/d`
(jamais de chiffre inventé).

## Dernière feuille : ETAT COMPARATIF de l'année
La dernière feuille du classeur (`ETAT COMPARATIF <année>`) récapitule l'année : **une ligne par mois** (JANVIER →
DÉCEMBRE), avec les mêmes colonnes TOTAL, COMPTANT, CREDIT, RECOUVREMENT et TOTAL RECETTE. Chaque ligne reprend
**par formule** la ligne TOTAL de la feuille du mois (ex. `='OCTOBRE 2026'!B35`), puis vient le TOTAL de l'année.

En bas, la **comparaison du dernier mois avec le mois précédent** : les deux lignes de totaux, puis VARIATION
(montant) et VARIATION % pour chaque colonne. La comparaison avec le même mois de l'année précédente n'est
ajoutée que si les rapports de cette année-là sont chargés. Sinon, la mention « données non disponibles » est
affichée. Un chiffre recopié à la main dans RECAP n'est pas repris.

Dans l'application : onglet « Etat comparatif annuel » du module État comparatif (comparaison du mois sélectionné
avec le mois précédent).

## Import d'un état chiffre d'affaires existant
Bouton « Importer un état chiffre d'affaires existant… » (module État comparatif). Contrôles automatiques :
- libellé de créance incohérent avec le mois (ex. « CREANCE AU 01-01-25 » en février) ;
- même créance saisie avec deux montants différents sur deux feuilles ;
- `Total M-1` saisi différent du `TOTAL` de la feuille du mois précédent ;
- créances **non mises à jour** (libellés et montants du mois précédent recopiés).

Sur les deux exemples 2025 fournis : 5 erreurs détectées (libellé de février, créance au 31-03-25 différente de
300 020, « Total AOUT 2025 » et recouvrement négatif en septembre, créances d'octobre non mises à jour avec un écart
de −1 126 200).

## Rapprochement quotidien des ventes avec Sage
**Le total des ventes du CR d'un jour doit être égal aux ventes comptabilisées dans Sage ce jour-là** (factures
comptant + factures à crédit, avoirs déduits, après la mise à jour comptable). Sinon, il y a une erreur dans le CR ou
un problème à la mise à jour.

Pour chaque jour, le logiciel interroge Sage en lecture seule (requête `ventes_jour`, journaux de ventes
`sage.journaux_ventes`, comptes clients) et compare **pièce par pièce** :
- pièce du CR absente de Sage : non mise à jour, ou n° faux dans le CR ;
- pièce Sage absente du CR : facture oubliée dans le CR, ou saisie sous un autre n° ;
- montants différents.

Statut du jour : `CONCORDANT`, `ECART`, `SAGE_INDISPONIBLE` (jamais de concordance déclarée sans Sage) ou
`NON_VERIFIE`. Si les chiffres du CR changent, le contrôle repasse à `NON_VERIFIE`.

Le contrôle est lancé automatiquement à l'import de chaque journée, et à la demande depuis le module
**État comparatif** (« Vérifier les ventes du mois avec Sage », « Vérifier le jour sélectionné »).

## Utilisation
- **Application** : module « État comparatif » (choix du mois, rapprochement Sage, détail des écarts, export Excel,
  chargement d'un rapport mensuel complet pour l'historique).
- **Outil** : `python tools/etat_comparatif.py "04 RC AVR.xlsx" … "10 RC OCT.xlsx" --sortie ETAT_COMPARATIF.xlsx
  [--config config.json]`. Il produit une feuille d'état comparatif par mois (jusqu'à la recette totale), ainsi
  que les feuilles RAPPROCHEMENT VENTES SAGE, CONTROLES, ANALYSE_MENSUELLE et CONTROLE_RECAP. Avec `--config` en mode `sql`, le rapprochement Sage de chaque jour est fait.

## Constats sur avril → octobre 2026
| Mois | Total ventes | Recouvrements | Recette totale |
|---|---:|---:|---:|
| Avril | 3 591 965 051 | 2 463 772 670 | 2 704 383 003 |
| Mai | 3 137 885 100 | 1 988 315 415 | 2 190 668 440 |
| Juin | 3 588 615 383 | 2 193 931 540 | 2 336 900 255 |
| Juillet | 4 087 974 074 | 2 808 534 015 | 2 980 401 749 |
| Août | 4 028 850 672 | 3 646 966 240 | 3 932 131 826 |
| Septembre | 4 255 352 416 | 3 855 271 805 | 4 186 851 775 |
| Octobre | 4 152 983 568 | 3 942 549 420 | 4 315 458 793 |

Erreurs relevées dans la feuille RECAP des rapports :
1. **ACOMPTE faux le 4 et le 21 de chaque mois** (12 cas) : sur ces deux lignes, la formule pointe vers la feuille de
   la **veille**. Par exemple, en octobre, `B7 = '03'!F284` au lieu de `'04'!F321`, et `B24 = '20'!F230` au lieu de
   `'21'!F214`. La RECETTE du modèle est fausse les mêmes jours. **À corriger dans le modèle RECAP.**
2. **TOTAL M-1 saisi à la main** : vide d'avril à août. En septembre et octobre, il ne correspond pas au TOTAL M
   du rapport précédent. Exemple d'octobre : vente à crédit +84 369 275 et recouvrements +48 874 675 par rapport à
   septembre. Origine à préciser (chiffres Sage après mise à jour ?).
3. Hors ACOMPTE, les autres colonnes de RECAP sont exactes. La cellule du CR qui calcule la vente totale est
   toujours égale à comptant + crédit (une seule erreur de saisie, FACB021708 le 17/06, comptée en H et en I).

Statut actuel : **rapprochement Sage non effectué** (pas d'accès à Sage dans l'environnement de développement). La
requête `ventes_jour` et les codes des journaux de ventes sont **à vérifier sur l'installation**.
