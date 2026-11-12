# Mapping du rapport commercial : établi sur le classeur réel `10 RC OCT.xlsx`

Analyse du 12/11/2026 : 32 feuilles (`01` à `31`, `RECAP`), 31 jours. Outils :
`tools/analyser_rapport.py` (statistiques, contrôle des totaux) et `tools/anonymiser_rapport.py`
(jeu de test `tests/fixtures/RC_OCT_2026_ANONYMISE.xlsx`, jours 01, 03, 12 et 14).

> Le classeur réel lui-même n'est **pas** versionné (données clients). Seule la copie anonymisée
> (noms remplacés, montants et numéros conservés) sert aux tests.

## Structure d'une feuille journalière
| Ligne | Contenu |
|---|---|
| 1, 3 | `GLOBAL TRADE COMPANY SARL`, `AGENCE DE BERTOUA` |
| 4 (A4) | **date de la journée**, contrôlée contre la date du rapport saisie |
| 5 à 7 | en-têtes : `FOLIO, N° PIECES, NOMS ET PRENOMS, REFRENCES, MONTANT` / `BON DE COMMANDE, FACTURE` / `ENTREE, BP, COMPTANT, VAT` |
| 8+ | section documents |
| variable | `TOTAL VENTES` (libellé en D, totaux F/G/H/I), puis un second `TOTAL VENTES` (libellé en G, H+I en I) |
| variable (117 à 385 selon le jour) | `REÇUS DE VERSEMENTS` **en colonne A**, puis l'en-tête `N°PIECES, NOMS ET PRENOMS, RECOUVREMENTS, AUTRES` |
| après les reçus | `TOTAL DE VERSEMENTS`, `TOTAL RECETTES`, `REPORT`, `TOTAL ENTREES`, versements (caisse Douala, Orange/MoMo, caisse centrale), `BTF nnnn VERSEMENT CAISSE RECETTE`, `SOLDE`, signatures |

## Colonnes de la section documents (confirmées par la feuille RECAP)
| Col. | En-tête | Signification (RECAP) | Traitement |
|---|---|---|---|
| A | FOLIO | n° d'ordre | — |
| B | N° PIECES | BC d'origine (`BC33525`) | `bc_origine` |
| C | (n° document) | `FACB…` facture, `FRCB…` / `FVCB…` avoirs, `BCCB…` bon de commande, `BLCB…` bon de livraison | type |
| D | NOMS ET PRENOMS | client | correspondance vérifiée → code tiers |
| E | REFRENCES | `EN COMPTE` (1, 2), `COMPTANT`, `ANNULEE`, `BP/<agent>`, `CASH/<agent>`, acheteur réel pour `CLIENTS DETAILS BTA` | mode / acheteur |
| F | BON DE COMMANDE – ENTREE | **ACOMPTE** (encaissement à la commande) | **mouvement ACOMPTE (crédit)** |
| G | BON DE COMMANDE – BP | BC « bon pour » (à crédit) | ignoré (pas de créance) |
| H | FACTURE – COMPTANT | VENTE COMPTANT | facture (débit) |
| I | FACTURE – VAT | VENTE À TERME | facture (débit) |

RECAP : `RECETTE = ACOMPTE + RECOUVREMENTS` (01/10 : 13 060 400 + 118 987 700 = 132 048 100).

## Constats sur le mois complet
| Constat | Volume | Règle appliquée |
|---|---|---|
| H et I jamais renseignés sur la même ligne | 0 cas | un seul montant facture par ligne |
| `FACB` avec F = H (acompte et facture comptant le même jour) | 1 988 | 1 ACOMPTE (C) + 1 FACTURE (D) |
| `FACB` avec H seul (acompte encaissé un jour précédent sur le `BCCB`) | 541 | FACTURE seule |
| `FACB` avec G = I (BC à crédit facturé) | 680 | FACTURE seule (G ignoré) |
| `BCCB` / `BLCB` sans montant facture | 1 350 | BC/BL seuls ignorés ; leur colonne F = acompte |
| `FRCB` (60) et `FVCB` (59) | 119 | **toujours négatifs** : AVOIR (crédit) |
| lignes `ANNULEE` | 106 | ignorées (bloquant si un montant est présent) |
| factures à montant nul (`AVARIE`, `BONUS`, `AN`…) | 27 | aucune écriture, information |
| `COMPTE DE LIAISON` | ~60 | hors périmètre (liaison interne) |
| n° `BCCB` portant un montant facture | 8 | **bloquant** : le n° de facture manque ; l'acompte de la ligne est conservé |
| même n° de facture pour 2 clients (`FACB039522` le 12/10) | 1 | avertissement + conflit enregistré à l'import |
| reçus `7RCB` négatifs | 4 | **bloquant** (remboursement ? annulation ?), traitement manuel |
| reçus | 913 | tous `7RCB`, montant en F (RECOUVREMENTS) |
| libellés clients distincts | ~213 | fichier de correspondances à compléter |

## Contrôle de complétude (pour chaque jour)
Pour chaque colonne H, I et F (acomptes) et pour la colonne F des reçus :
1. **total du rapport = somme des lignes de détail**. Il est vérifié sur les 31 jours sans aucun écart.
2. **somme des lignes = retenu + exclu (liaisons, caisse) + bloqué (anomalies)**. Il est vérifié sur les 31 jours.
   Un montant non interprété fait apparaître une anomalie bloquante.

## Points restant à confirmer par la comptabilité
1. **Acomptes (colonne F)** : sont-ils bien passés dans Sage au crédit du compte du client, et avec quelle
   référence (n° de BC, de reçu, autre) ? Le traitement est activé (`rapport.acomptes.integrer`), et le
   rapprochement Sage confirmera ou infirmera la règle dès les premiers jours.
2. **Sens des `FVCB`** : il s'agit d'avoirs, mais de quelle nature (remise, ristourne, avoir sur facture) ?
3. **Reçus négatifs** : remboursement au client, ou annulation d'un reçu ?
4. **`COMPTE DE LIAISON`** : exclusion confirmée ? Existe-t-il un compte 411 correspondant dans Sage ?
5. **`VENTE PROMOTIONNELLE`**, **`SOURCE DU PAYS RETOUR`** : comptes clients Sage réels ?
