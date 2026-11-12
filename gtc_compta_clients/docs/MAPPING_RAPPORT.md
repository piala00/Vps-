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
| F | BON DE COMMANDE – ENTREE | **ACOMPTE** (encaissement à la commande) | **ACOMPTE au crédit, signe conservé** |
| G | BON DE COMMANDE – BP | BC « bon pour » (à crédit) | ignoré (pas de créance) |
| H | FACTURE – COMPTANT | VENTE COMPTANT | facture au débit, signe conservé |
| I | FACTURE – VAT | VENTE À TERME | facture au débit, signe conservé (avoirs négatifs) |

RECAP : `RECETTE = ACOMPTE + RECOUVREMENTS` (01/10 : 13 060 400 + 118 987 700 = 132 048 100).

Comparaison des lignes TOTAL des 31 feuilles avec la feuille RECAP : VENTE COMPTANT (372 909 373),
VENTE À TERME (3 780 074 195) et RECOUVREMENTS (3 942 549 420) sont **identiques**. La colonne **ACOMPTE de
RECAP comporte deux erreurs** : le 04/10 reprend la valeur du 03/10 (12 466 335 au lieu de 0), et le 21/10
reprend celle du 20/10 (32 789 775 au lieu de 6 738 250). Total RECAP 435 334 258, feuilles 396 816 398 :
écart de 38 517 860.

## Constats sur le mois complet
| Constat | Volume | Règle appliquée |
|---|---|---|
| H et I jamais renseignés sur la même ligne | 0 cas | un seul montant facture par ligne |
| `FACB` avec F = H (acompte et facture comptant le même jour) | 1 988 | 1 ACOMPTE (crédit) + 1 FACTURE (débit) |
| `FACB` avec H seul (acompte encaissé un jour précédent sur le `BCCB`) | 541 | FACTURE seule |
| `FACB` avec G = I (BC à crédit facturé) | 680 | FACTURE seule (G ignoré) |
| `BCCB` / `BLCB` sans montant facture | 1 350 | BC/BL seuls ignorés ; leur colonne F = acompte |
| `FRCB` (60) et `FVCB` (59) | 119 | **toujours négatifs** : AVOIR au **débit négatif** (règle GTC) |
| lignes `ANNULEE` | 106 | ignorées (bloquant si un montant est présent) |
| factures à montant nul (`AVARIE`, `BONUS`, `AN`…) | 27 | aucune écriture, information |
| `COMPTE DE LIAISON` | ~60 | hors périmètre (liaison interne) |
| n° `BCCB` portant un montant facture | 8 | **bloquant** : le n° de facture manque ; l'acompte de la ligne est conservé |
| même n° de facture pour 2 clients (`FACB039522` le 12/10) | 1 | avertissement + conflit enregistré à l'import |
| reçus `7RCB` négatifs | 4 | **annulation d'un reçu fait sur un compte erroné** (règle confirmée par la comptabilité) : reçu au **crédit négatif**, lié au reçu annulé ; 3/4 liés automatiquement, 1 en alerte |
| reçus | 913 | tous `7RCB`, montant en F (RECOUVREMENTS) |
| libellés clients distincts | ~213 | fichier de correspondances à compléter |

## Reçus négatifs (règle confirmée le 12/11/2026)
Quand un reçu a été fait sur un compte erroné, le caissier fait un reçu du **même montant avec un signe
négatif** sur ce même compte. Les deux reçus s'annulent à la comptabilisation, et un nouveau reçu positif
est en général fait sur le compte de la bonne personne.

Traitement :
- le reçu négatif reste un REGLEMENT au **crédit**, avec son **montant négatif** (règle des signes GTC), sur
  le compte écrit dans le rapport ;
- il est lié au reçu positif qu'il annule : même client, même montant, du jour ou d'un jour déjà importé, pas
  déjà annulé. Un reçu ne peut être annulé qu'une fois ;
- sans reçu d'origine, une alerte `ANNULATION_RECU_A_VERIFIER` est créée (reçu antérieur au démarrage, ou
  libellé client différent). Les reçus de même montant faits le même jour sur d'autres comptes sont
  cités comme réaffectations possibles.

Octobre 2026 :
| Reçu négatif | Annule | Réaffectation possible (même jour, même montant) |
|---|---|---|
| 7RCB028975 (14/10, 3 500 000) | 7RCB028907 (même jour) | 7RCB028847 |
| 7RCB028976 (14/10, 7 000 000) | 7RCB028853 (même jour) | 7RCB028851 |
| 7RCB030438 (27/10, 8 100 000) | 7RCB030328 (26/10) | — |
| 7RCB030477 (27/10, 965 950) | **non trouvé** sur « ALH OUMAROU BOUBAKARY » | 7RCB030347 « OUMAROU BOUBAKARY » : même compte Sage ? |

## Contrôle de complétude (pour chaque jour)
Pour chaque colonne H, I et F (acomptes) et pour la colonne F des reçus :
1. **total du rapport = somme des lignes de détail**. Il est vérifié sur les 31 jours sans aucun écart.
2. **somme des lignes = retenu + exclu (liaisons, caisse) + bloqué (anomalies)**. Il est vérifié sur les 31 jours.
   Un montant non interprété fait apparaître une anomalie bloquante.

## Points restant à confirmer par la comptabilité
1. **Acomptes (colonne F)** : sont-ils bien passés dans Sage au crédit du compte du client, et avec quelle
   référence (n° de BC, de reçu, autre) ? Le traitement est activé (`rapport.acomptes.integrer`), et le
   rapprochement Sage confirmera ou infirmera la règle dès les premiers jours.
2. ~~Sens des `FVCB`~~ : réglé. Comme toute facture, ils vont au débit avec leur signe (négatif).
3. **`COMPTE DE LIAISON`** : exclusion confirmée ? Existe-t-il un compte 411 correspondant dans Sage ?
4. **`VENTE PROMOTIONNELLE`**, **`SOURCE DU PAYS RETOUR`** : comptes clients Sage réels ?
