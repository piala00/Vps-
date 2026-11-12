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
| F | BON DE COMMANDE – ENTREE | ACOMPTE (encaissement à la commande) | **non exploité** : rien n'est comptabilisé au stade du BC |
| G | BON DE COMMANDE – BP | BC « bon pour » (à crédit) | **non exploité** |
| H | FACTURE – COMPTANT | VENTE COMPTANT | facture au débit **+ acompte imputé au crédit** (même montant), signe conservé |
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
| `FACB` avec F = H (acompte et facture comptant le même jour) | 1 988 | FACTURE (débit) + acompte imputé (crédit) : solde net nul |
| `FACB` avec H seul (acompte encaissé un jour précédent sur le `BCCB`) | 541 | FACTURE (débit) + acompte imputé (crédit) le jour de la facture |
| acompte (F) avec facture à terme (I) sur la même ligne | 0 | — (les acomptes ne concernent que les ventes comptant) |
| `FACB` avec G = I (BC à crédit facturé) | 680 | FACTURE seule (G ignoré) |
| `BCCB` / `BLCB` sans montant facture | 1 350 | ignorés (aucun mouvement, y compris leur acompte en F) |
| `FRCB` (60) et `FVCB` (59) | 119 | **toujours négatifs** : AVOIR au **débit négatif** (règle GTC) |
| lignes `ANNULEE` | 106 | ignorées (bloquant si un montant est présent) |
| factures à montant nul (`AVARIE`, `BONUS`, `AN`…) | 27 | aucune écriture, information |
| `COMPTE DE LIAISON`, `VENTE PROMOTIONNELLE`, `SOURCE DU PAYS RETOUR` | ~70 pièces | **comptes clients Sage normaux** (confirmé par la comptabilité) : traités comme tout client |
| n° `BCCB` portant un montant facture | 8 | **bloquant** : le n° de facture manque |
| même n° de facture pour 2 clients (`FACB039522` le 12/10) | 1 | avertissement + conflit enregistré à l'import |
| reçus `7RCB` négatifs | 4 | **annulation d'un reçu fait sur un compte erroné** (règle confirmée par la comptabilité) : reçu au **crédit négatif**, lié au reçu annulé ; 3/4 liés automatiquement, 1 en alerte |
| reçus | 913 | tous `7RCB`, montant en F (RECOUVREMENTS) |
| libellés clients distincts | ~213 | fichier de correspondances à compléter |

## Comptes clients particuliers (confirmé par la comptabilité le 12/11/2026)
| Libellé | Nature | Fonctionnement |
|---|---|---|
| `VENTE PROMOTIONNELLE` | client (délégation commerciale) | facturée en compte, à crédit ; solde par reçus après la vente promotionnelle |
| `SOURCE DU PAYS RETOUR` | client (compte rattaché à un fournisseur) | les déstockeurs y facturent puis effectuent le versement |
| `COMPTE DE LIAISON` | **compte conteneur** (comme CLIENTS DETAILS BTA) : bénéficiaire réel en colonne E (ETS RASHMA, DAVID PANZANI…) | facturation de clients sans cash immédiat ; paiement soit par reçu le jour même à ce nom, soit (le plus souvent) par un règlement / acompte dans la caisse des opérations de liaison |
| `CLIENTS DETAILS BTA` | compte conteneur | acheteur réel en colonne E (ventilation analytique) |

Conséquence pour le rapprochement : le paiement d'une facture COMPTE DE LIAISON passé directement en
comptabilité n'apparaît pas dans le rapport. Il est détecté comme « écriture Sage absente du rapport » et
repris par l'option A (reprise liée à l'EC_No, sans rien écrire dans Sage).

Octobre : 40 factures, 7 avoirs et 46 acomptes imputés de plus qu'avec l'ancienne exclusion. Les factures
comptant de COMPTE DE LIAISON sont toutes adossées à un acompte de BC (31 sur la même ligne, 14 sur un BC
antérieur du mois, 1 sur un BC de septembre). Contrôle sur tout le mois : 2 520 factures comptant sur 2 537
ont leur acompte visible en octobre ; les 17 autres portent des n° de BC antérieurs à octobre.

## Bons de commande et acomptes (règle confirmée par la comptabilité le 12/11/2026)
- Tant qu'un montant est dans les colonnes BON DE COMMANDE (F « ENTREE » = acompte, G « BP »), **rien
  n'est comptabilisé** dans Sage : seules les **factures** et les **règlements** passent à la mise à jour
  comptable. Les colonnes F et G ne sont donc **jamais** transformées en mouvements.
- Dans Sage Gestion commerciale, le BC est transformé en BL puis en facture au magasin. À la mise à jour
  comptable, l'acompte encaissé sur le BC est **imputé sur la facture** et les deux montants s'annulent sur le
  compte client.
- Dans le rapport, les acomptes ne concernent que les ventes **comptant** (colonne H) : 0 cas d'acompte
  avec une facture à terme (I). Pour chaque facture comptant, l'ERP enregistre donc la facture au débit et
  l'**acompte imputé** au crédit, du même montant et à la date de la facture. Le paramètre
  `rapport.factures_comptant.mode` vaut `solder_par_acompte` ; `facture_seule` le désactive.
- Les factures **en compte / BP** (colonne I, « VAT ») restent dues jusqu'aux reçus `7RCB`.
- Octobre : 2 491 acomptes imputés (309 821 225), aucune facture comptant non soldée. Le compte collectif
  CLIENTS DETAILS BTA a une variation nette nulle sur le mois.

Recherche documentaire (12/11/2026) : la documentation publique confirme le principe comptable général
(acompte reçu porté au crédit du client ou du compte 4191, puis soldé par la facture définitive) et, pour
Sage 100, que l'acompte est rattaché au bon de commande puis imputé sur la facture de vente, les
règlements étant comptabilisés par la « mise à jour comptable des règlements ». L'aide en ligne Sage 100
et le forum Sage n'étaient pas accessibles depuis l'environnement de développement : la référence et le
journal exacts de l'écriture d'acompte seront constatés lors du premier rapprochement réel.

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

Vérification dans Sage (tableau de bord → alerte → « Vérifier dans Sage (reçu négatif) »), selon la
procédure de la comptabilité, en lecture seule :
1. rechercher sur le compte qui porte le reçu négatif un **reçu antérieur de même montant**. S'il existe, la
   logique est confirmée, le lien est enregistré et l'alerte close. Si ce reçu figure dans le rapport sous un
   **autre libellé**, il est signalé que les deux libellés désignent le même compte Sage ;
2. sinon, indiquer **dans quels comptes Sage** ont été passés le reçu négatif et les reçus positifs de même
   montant du même jour. Résultat : `MEME_COMPTE`, `A_ANALYSER` ou `NON_COMPTABILISE`.

Octobre 2026 :
| Reçu négatif | Annule | Réaffectation possible (même jour, même montant) |
|---|---|---|
| 7RCB028975 (14/10, 3 500 000) | 7RCB028907 (même jour) | 7RCB028847 |
| 7RCB028976 (14/10, 7 000 000) | 7RCB028853 (même jour) | 7RCB028851 |
| 7RCB030438 (27/10, 8 100 000) | 7RCB030328 (26/10) | — |
| 7RCB030477 (27/10, 965 950) — feuille 27, ligne 338 | **non trouvé** sur « ALH OUMAROU BOUBAKARY » | 7RCB030347 « OUMAROU BOUBAKARY » (feuille 27, ligne 315) : même compte Sage ? **en vérification par la comptabilité** |

## Contrôle de complétude (pour chaque jour)
Pour chaque colonne H, I et F (acomptes) et pour la colonne F des reçus :
1. **total du rapport = somme des lignes de détail**. Il est vérifié sur les 31 jours sans aucun écart.
2. **somme des lignes = retenu + exclu (versements de caisse) + bloqué (anomalies)**. Il est vérifié sur les 31 jours.
   Un montant non interprété fait apparaître une anomalie bloquante.

## Points restant à confirmer par la comptabilité
1. ~~Acomptes (colonne F)~~ : **réglé**. Voir « Bons de commande et acomptes » ci-dessous. Reste à vérifier
   au premier rapprochement réel la **référence** sous laquelle Sage passe l'acompte imputé (n° de facture,
   de BC ou de règlement). L'appariement essaie les trois, puis date et montant.
2. ~~Sens des `FVCB`~~ : réglé. Comme toute facture, ils vont au débit avec leur signe (négatif).
3. ~~`COMPTE DE LIAISON`, `VENTE PROMOTIONNELLE`, `SOURCE DU PAYS RETOUR`~~ : réglé, ce sont des comptes
   clients (voir « Comptes clients particuliers »).
