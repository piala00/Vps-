# Mapping du rapport commercial : établi sur les classeurs réels d'août, septembre et octobre 2026

Analyse du 12/11/2026 : 32 feuilles (`01` à `31`, `RECAP`), 31 jours. Outils :
`tools/analyser_rapport.py` (statistiques, contrôle des totaux) et `tools/anonymiser_rapport.py`
(jeu de test `tests/fixtures/RC_OCT_2026_ANONYMISE.xlsx`, jours 01, 03, 12 et 14).

> Le classeur réel lui-même n'est **pas** versionné (données clients). Seule la copie anonymisée
> (noms remplacés, montants et numéros conservés) sert aux tests.

## Validation sur un second mois : septembre 2026
`09 RC SEPT.xlsx` (feuilles 01 à 31, RECAP, `Feuil1` vide ; la feuille 31 est vide et datée du 01/10) est traité
**sans aucune modification des règles** :
- 30/30 jours cohérents (total du rapport = lignes ; aucun montant oublié) ;
- 4 682 factures, 123 avoirs, 2 781 acomptes imputés, 928 reçus ; 2 n° BCCB portant une facture
  (BCCB031741 le 18/09, BCCB032460 le 23/09, montants positifs : ce ne sont pas des avoirs) ;
- RECAP de septembre : vente comptant, vente à terme et recouvrements **identiques** aux feuilles ;
- import enchaîné septembre + octobre : 16 314 mouvements sur 52 jours, 0 rejet, 0,9 s.

Recoupement des acomptes entre les deux mois : sur les 17 factures comptant d'octobre dont l'acompte
n'apparaissait pas en octobre, **13 ont leur acompte sur un BC de septembre**. Les 4 autres révèlent des
erreurs de saisie :
| Facture | Constat |
|---|---|
| FACB038619 (05/10, DEST ANAS ABDOU NOVIA, 26 000) | colonne B « BC31018 » = BC de septembre d'un autre client ; même erreur sur BCCB034018 le 03/10 (devrait être BC34018) |
| FACB040560 (19/10, CLIENTS DETAILS BTA / ALH OGA, 26 000) | colonne B « BC3594 » : chiffre manquant ; l'acompte est sur BC35949 (17/10, même acheteur, même montant) |
| FACB040798 (20/10, CLIENTS DETAILS BTA / KUETE, 18 000) | colonne B « BC36198 » = BC d'un autre client ; BC réel inconnu |
| FACB041560 (26/10, COMPTE DE LIAISON, 36 450) | BC036855 en **BP** (aucun acompte) mais facture en colonne COMPTANT : probablement non soldée par acompte dans Sage (le rapprochement le signalera) |

## Troisième mois : août 2026 et vérification août → octobre (93 feuilles)
- 93/93 jours cohérents (total du rapport = lignes ; aucun montant non expliqué).
- Nouveau cas en août : les **04/08 (73 lignes) et 06/08 (26 lignes)**, des lignes de BC ont la colonne C
  (n° BCCB) **vide**. Le BC est en B et les montants ne sont qu'en F/G. Ce sont des lignes de BC seules, sans
  incidence comptable : leur acompte est conservé dans le registre et une information par jour est émise.
  Un montant de **facture** sans numéro en C est en revanche **bloquant**.
- RECAP, colonne ACOMPTE : deux nouveaux écarts en août (04/08 : feuille 7 968 225, RECAP 8 152 225 ;
  21/08 : feuille 4 278 111, RECAP 4 364 500), soit **6 écarts sur 3 mois, tous dans la colonne ACOMPTE**.
- Reçus négatifs : **9 sur 10 liés** à leur reçu d'origine. 7RCB024416 (09/09) annule 7RCB022350 d'**août**.
  7RCB020646 (08/08, ligne 233) annule 7RCB020641, écrit plus bas dans la même feuille (ligne 263) : l'import
  traite désormais les reçus négatifs après les positifs. Reste **7RCB030477** (27/10), en vérification dans Sage.
- Même n° de reçu pour deux clients : **7RCB020978** le 11/08 (SOULEY DARGALA 8 000 000 et YOUSSOUFA OUSTAZ
  NGAOUNDAL 2 500 000) ; reçu sans montant : 7RCB021355 (14/08).
- n° de BL/BC portant un montant de facture le 08/08 : BLCB026988, BLCB026945, BLCB026987, BCCB025793
  (montants positifs : pas des avoirs).
- Factures comptant : avec août chargé, les BC « inconnus » de septembre passent de 15 à 1. Erreurs de
  saisie en août : FACB030381 (BC25812 = BC de VENTE PROMOTIONNELLE), FACB031310 (BC27660 au lieu de
  BC27662), FACB030462 (acompte négatif de −57 200 sur BC26827), FACB031561 (acompte 141 100 pour 142 400).
  16 factures du début d'août portent des BC de **juillet** (rapport non fourni).

## Vérification de tous les mois : `tools/verifier_mois.py`
```
python tools\verifier_mois.py "08 RC AOUT.xlsx" "09 RC SEPT.xlsx" "10 RC OCT.xlsx" ... --sortie VERIFICATION.xlsx
```
L'outil passe tous les rapports fournis, dans l'ordre chronologique, par le **traitement réel** de
l'application : parseur, registre des BC, import, contrôles. Il produit un classeur de constats avec les
feuilles SYNTHESE, CONTROLE_JOURS, RECAP, ANOMALIES, FACTURES_COMPTANT, RECUS_NEGATIFS et NUMEROS.

Résultat septembre + octobre 2026 (62 feuilles) :
- 62/62 jours : total du rapport = lignes, et aucun montant non expliqué ;
- **feuille RECAP, colonne ACOMPTE : 4 erreurs**. Le 04/09, RECAP indique 9 559 275 pour 6 224 400 sur la
  feuille. Le 21/09, RECAP indique 0 pour 30 958 550. Les 04/10 et 21/10 sont déjà signalés plus bas. Les
  colonnes vente comptant, vente à terme et recouvrements sont exactes ;
- 23 factures comptant sans acompte connu sur leur BC :
  - **15 au début de septembre** : BC d'**août** (BC28xxx/BC29xxx), à confirmer avec le rapport d'août ;
  - **8 erreurs réelles** :

| Facture | Constat | Proposition |
|---|---|---|
| FACB034781 (12/09) | BC30659 = BC de HAMADOU HASSANA | BC30652 (même client, même montant, la veille) |
| FACB035365 (15/09) | BC21288 inconnu | BC31288 (chiffre erroné) |
| FACB035350 (15/09) | acompte du BC31327 (15 000) inférieur à la facture (19 700) | vérifier le complément |
| FACB037037 (26/09) | colonne B vide, aucun acompte sur la ligne | vérifier le règlement |
| FACB038619 (05/10) | BC31018 = BC de SAIDOU BIRI | BC34018 |
| FACB040560 (19/10) | BC3594 inconnu | BC35949 |
| FACB040798 (20/10) | BC36198 = BC de SALAHOUDINE OUSMANOU ABDOULAYE | BC36199 |
| FACB041560 (26/10) | BC036855 en BP facturé en comptant | facture probablement non soldée par acompte |

## Registre des bons de commande (contrôle des factures comptant)
À chaque import, les montants ACOMPTE (F) et BP (G) des BC sont enregistrés dans un **registre**. C'est une
information de contrôle, jamais un mouvement comptable. Chaque facture comptant est contrôlée contre ce
registre, tous mois importés confondus (acompte du BC ≥ factures comptant imputées). Si le contrôle échoue,
l'alerte `FACTURE_COMPTANT_SANS_ACOMPTE` donne un diagnostic : colonne B vide ou sans n° de BC, BC inconnu
(antérieur à l'historique ou mal saisi), BC appartenant à un autre client, BC en BP, ou acompte insuffisant.
Elle propose aussi le **BC probable** (même client, même montant, dans les 45 jours).

Seule une valeur de la forme `BC` + chiffres est un n° de BC (`rapport.motif_bc`). Sinon (vide, « OLA »,
« RASHMA »…), l'acompte est rattaché à la ligne de la facture. Pour les mois antérieurs au démarrage :
bouton « Historique des BC (mois antérieurs) » (Préparation / Imports), qui charge le registre sans créer
de mouvement.

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
| 7RCB026463 (25/09, 121 800) | 7RCB026459 (24/09) | — |
| 7RCB024416 (09/09, 123 500, « BOUTIQUE TOURISTIQUE ») | **7RCB022350 d'août** (trouvé avec le rapport d'août) | 7RCB024417 « MOHAMADOU AWALOU TOURISTIQUE » : nouveau reçu sur le bon compte |
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
