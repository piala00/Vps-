# Journal d'avancement

## Cycle 11 (12/11/2026) : état comparatif et rapprochement des ventes avec Sage
- Module « État comparatif » (modèle RECAP) : vente comptant, vente à crédit, total ventes, recouvrements,
  recette totale = recouvrements + vente comptant ; TOTAL M, M-1, ÉVOLUTION, N-1 (saisi dans RECAP à défaut),
  ÉCART ; export Excel ; alimenté à chaque import et depuis un rapport mensuel complet (migration 007).
- Rapprochement quotidien des ventes CR / Sage (lecture seule), pièce par pièce, lancé à l'import ; requête
  `ventes_jour` à vérifier sur l'installation.
- Outil `tools/etat_comparatif.py` : état comparatif et analyse mois par mois d'avril à octobre 2026.
- Feuille RECAP : cause des erreurs ACOMPTE identifiée (formule des lignes 4 et 21 pointant la veille) ;
  TOTAL M-1 saisi à la main, incohérent avec le mois précédent. 131 tests.


## Cycle 10 (12/11/2026) : registre des anomalies CR et vérification sur 7 mois
- **Registre des anomalies CR** (migration 006) : chaque erreur de rapport pouvant fausser un solde est conservée
  OUVERTE, affichée sur la fiche du client et au tableau de bord, puis traitée (intégration de la facture
  corrigée, réintégration des lignes rejetées après correspondance, résolution ou abandon motivés, audit).
- Contrôles entre jours et entre mois : pièce ressaisie un autre jour, même n° pour plusieurs clients,
  montant différent pour une pièce connue, ligne rejetée.
- Rapports d'avril à juillet : nouvelles erreurs reconnues (n° tronqués 7RC/FRC, PLCB, même montant en H et I,
  facture annulée par avoir, commentaire à la place du client, dates du modèle de mai). Confirmation exigée à
  l'import si la date imprimée diffère.
- Avril → octobre : **214/214 journées cohérentes, aucun montant non expliqué** ; 12 erreurs de formule RECAP
  (ACOMPTE, le 4 et le 21) ; catalogue des erreurs CR (docs/CATALOGUE_ERREURS_CR.md).
- Anonymisation renforcée (toutes les lignes, colonnes B, D, E) : 0 nom réel dans les 7 jeux de test.
  **Le jeu d'août poussé au commit 5d3571f contenait des noms réels** : corrigé ; purge de l'historique à
  décider par GTC. 123 tests.


## Cycle 9 (12/11/2026) : août 2026, vérification sur 3 mois
- `08 RC AOUT.xlsx` : 31/31 jours cohérents. Lignes de BC sans n° en colonne C (04/08, 06/08) reconnues
  comme BC seuls ; facture sans numéro rendue bloquante.
- Correction : un reçu négatif écrit avant le reçu qu'il annule dans la feuille est désormais lié.
- Vérification août → octobre (93 feuilles) : 9/10 reçus négatifs liés ; 6 écarts RECAP (colonne ACOMPTE) ;
  BC inconnus de septembre résolus par août ; erreurs de saisie listées dans MAPPING_RAPPORT.md.
- Jeu de test anonymisé d'août (04, 08, 11). 106 tests.
- Pour aller plus loin : rapport de **juillet** (16 factures comptant du début d'août portent des BC de juillet).


## Cycle 8 (12/11/2026) : vérification sur tous les mois
- Registre des BC (migration 005), contrôle de chaque facture comptant contre l'historique de tous les mois,
  diagnostic et BC probable ; chargement de l'historique des mois antérieurs.
- Outil `tools/verifier_mois.py` : vérification de N rapports mensuels avec le traitement réel, classeur de constats.
- Septembre + octobre : 62/62 jours cohérents ; 4 erreurs ACOMPTE dans RECAP ; 8 erreurs de saisie réelles
  sur les factures comptant ; 15 BC d'août à confirmer.
- **Besoin : les rapports des autres mois de 2026** (au minimum août) pour étendre la vérification. 98 tests.


## Cycle 7 (12/11/2026) : second mois réel (septembre 2026)
- `09 RC SEPT.xlsx` traité sans changement de règles : 30/30 jours cohérents ; RECAP identique.
- Jeu de test anonymisé de septembre (jours 09, 18, 24, 25) ; lien d'annulation de reçu entre deux jours.
- Recoupement des acomptes entre mois : 13/17 confirmés en septembre ; 3 erreurs de n° de BC (colonne B) et
  1 facture comptant issue d'un BC « BP » relevées.
- Nouveau reçu négatif à vérifier dans Sage : 7RCB024416 (09/09, BOUTIQUE TOURISTIQUE, −123 500).
- Import enchaîné des deux mois : 16 314 mouvements, 0 rejet. 93 tests.


## Cycle 6 (12/11/2026) : contrôle assisté des reçus négatifs
- Action « Vérifier dans Sage (reçu négatif) » sur les alertes : recherche du reçu d'origine sur le même
  compte Sage, sinon des comptes où les reçus ont été passés. Lecture seule, résultat tracé dans l'audit.
- Cas en cours : 7RCB030477 (ALH OUMAROU BOUBAKARY, feuille 27 l. 338) / 7RCB030347 (OUMAROU BOUBAKARY,
  feuille 27 l. 315). **Vérification dans Sage par la comptabilité en cours** ; le contrôle sera rejoué
  automatiquement dès l'accès Sage. 87 tests.


## Cycle 5 (12/11/2026) : comptes clients particuliers
- COMPTE DE LIAISON, VENTE PROMOTIONNELLE et SOURCE DU PAYS RETOUR sont des comptes clients Sage normaux.
  COMPTE DE LIAISON n'est plus exclu ; seuls les versements de caisse et les totaux le restent.
- Vérification : les factures comptant de COMPTE DE LIAISON sont adossées à des acomptes de BC, donc la
  règle « acompte imputé » s'applique ; ses paiements passés directement en comptabilité seront repris
  par l'option A au rapprochement.
- Mois réel : 4 218 factures, 126 avoirs, 2 537 acomptes imputés, 913 reçus ; totaux 31/31 cohérents.
- COMPTE DE LIAISON déclaré compte conteneur : le bénéficiaire réel (colonne E) est conservé pour la
  ventilation. Reçu 7RCB030477 (feuille 27, ligne 338) transmis à la comptabilité pour vérification. 83 tests.


## Cycle 4 (12/11/2026) : bons de commande et acomptes
- Règle de la comptabilité : rien n'est comptabilisé au stade du BC (colonnes F et G non exploitées). Seules
  les factures (H, I) et les règlements passent à la mise à jour comptable.
- Facture comptant (H) : l'acompte du BC est imputé sur la facture. L'ERP enregistre facture (débit) +
  acompte imputé (crédit) du même montant. Factures en compte / BP (I) : dues jusqu'aux reçus.
- Rapport réel : 2 491 acomptes imputés, toutes les factures comptant soldées, CLIENTS DETAILS BTA net nul ;
  totaux 31/31 cohérents. VBA et modèle de classeur alignés. 82 tests.
- À constater au premier rapprochement réel : la référence et le journal de l'acompte imputé dans Sage.


## Cycle 3 (12/11/2026) : règle des signes de la comptabilité
- Règle appliquée partout (parseur, VBA, import, fiche, impression, rapprochement) : factures (retours et
  avoirs compris) au débit avec leur signe ; reçus et acomptes au crédit avec leur signe.
- Migration 004 : montants signés, conversion des données déjà enregistrées, migrations sûres vis-à-vis
  des clés étrangères.
- Rapprochement sur l'effet signé : indépendant de la façon dont Sage stocke un avoir.
- Contrôle : RECOUVREMENTS du mois = 3 942 549 420, identique à RECAP ; deux erreurs relevées dans la
  colonne ACOMPTE de RECAP (04/10 et 21/10).
- 81 tests.


## Cycle 2 (12/11/2026) : analyse du rapport réel `10 RC OCT.xlsx`

### Terminé (avec preuve)
- Inventaire complet des 31 jours, mapping réel documenté ([MAPPING_RAPPORT.md](MAPPING_RAPPORT.md)).
- Colonnes confirmées par la feuille RECAP : F = ACOMPTE, G = BP, H = vente comptant, I = vente à terme,
  reçus F = RECOUVREMENTS.
- Parseur adapté : acomptes, avoirs FRCB/FVCB, n° de BC portant une facture, ANNULEE, factures à montant nul,
  date de la feuille (A4), même n° pour deux clients, reçus négatifs.
- **Contrôle de complétude automatique** sur chaque journée (totaux du rapport et montants
  retenus/exclus/bloqués) : 31/31 jours cohérents.
- Rapprochement : appariement des acomptes par n° de BC, puis repli prudent date/sens/montant (unique et tracé).
- Module VBA aligné sur les mêmes règles. **Contrôle croisé** macro/application à l'import.
- Correspondances clients en masse : fichier à compléter généré depuis le rapport (avec suggestions à
  vérifier), puis import contrôlé.
- Jeu de test anonymisé issu du rapport réel ; essai de volume sur le mois complet.
- Reçus négatifs (règle donnée par la comptabilité) : annulation liée au reçu erroné, y compris d'un jour
  précédent ; 3/4 liés automatiquement en octobre, le 4e en alerte. 77 tests.

### Questions pour la comptabilité (bloquent la mise en production)
1. ~~Les acomptes~~ : réglé (imputés sur la facture comptant ; référence Sage à constater au rapprochement).
2. ~~Les FVCB~~ : réglé (débit avec leur signe, comme toute facture).
3. ~~Reçus négatifs~~ : **réglé**. Il s'agit d'annulations de reçus faits sur un compte erroné (règle implémentée).
   Reste à vérifier : `7RCB030477` (ALH OUMAROU BOUBAKARY) a-t-il le même compte Sage que « OUMAROU BOUBAKARY » ?
4. ~~COMPTE DE LIAISON, VENTE PROMOTIONNELLE, SOURCE DU PAYS RETOUR~~ : réglé (comptes clients).
5. Les 8 lignes `BCCB` portant un montant de facture : quelle est la règle de correction attendue des commerciaux ?


## Cycle 1 (12/11/2026) : P0 partiel, P1, P2, P3 et P4 sur données fictives

### Terminé (avec preuve)
- **P1** : projet Python, configuration externe, SQLite + migrations + transactions + audit +
  sauvegarde/restauration, rôles, logs rotatifs, interface CustomTkinter à 10 modules (captures réelles).
- **P2** : parseur paramétrable des deux sections, classeur intermédiaire (feuilles normalisées,
  EXPORT_ERP versionné), traitement Python de secours, module VBA + construction du `.xlsm` par Excel.
- **P3** : import idempotent, conflits, corrections tracées, référentiel avec champs manuels persistants,
  correspondances vérifiées, soldes d'ouverture, fiches et soldes progressifs.
- **P4** : rapprochement automatique après import, écarts typés, options A/B, validation automatique
  conditionnelle avec preuve, statut d'attente si Sage est indisponible, alertes rétroactives.
- Premières versions de **P5 à P7** (architecture et moteurs) : solvabilité, pointage, PDF et messagerie
  assistée, fiches A4 recto verso et registre d'impression.
- 56 tests automatisés réussis ([RAPPORT_TESTS.md](RAPPORT_TESTS.md)).

### Bloqué : en attente d'éléments de GTC
| Élément manquant | Impact |
|---|---|
| ~~Classeur réel `10 RC OCT.xlsx`~~ | **reçu et analysé (cycle 2)** |
| Accès en lecture seule à Sage 100 V11 (Bertoua) | requêtes non vérifiées, mode `sql` non recetté |
| Copies d'écran Sage « Solvabilité » sur quelques clients | formule de risque non établie |
| Photos ou scans recto verso de la fiche papier | modèle d'impression provisoire |
| Poste Windows 10/11 avec Excel et imprimante recto verso | `.xlsm`, exécutable et duplex non testés |
| Lien Sage ↔ PDF des factures | indexation de dossiers seulement |

### Décisions ouvertes (configuration sûre appliquée en attendant)
1. Sens comptable des types de document : FACB en débit, FRCB/FVCB en avoir (déduit du rapport réel,
   à confirmer). Tout autre type est bloquant.
2. Politique des factures échues : « signaler » (n'impose rien).
3. Plafond à 0 dans Sage (illimité ou interdit ?) : DONNEES_INSUFFISANTES.
4. Tolérance de date entre le rapport et l'écriture Sage (pièce saisie le lendemain) : aucune ; l'écart est montré.
5. Correspondance automatique sur intitulé exact unique : désactivée (`correspondance_auto_intitule_exact`).
6. Seuil « recto verso plein » : 2 pages × lignes par page du modèle provisoire.
7. Authentification des utilisateurs : utilisateur défini dans `config.json` (à remplacer).

### Prochaines étapes
1. ~~Analyser le vrai rapport~~ (fait au cycle 2). Compléter les correspondances clients (fichier généré).
2. Sur site : `tools/verifier_sage.py`, recette des soldes, ajustement des requêtes.
3. Établir la formule de solvabilité par concordance.
4. Construire et recetter le `.xlsm`, compiler l'exécutable, tester le duplex sur l'imprimante réelle.
5. Adapter la fiche au modèle papier réel.
6. Authentification et passage éventuel à SQL Server multi-postes.

Avancement global estimé : fondations et moteurs en place ; **aucune fonctionnalité n'est encore validée
sur les données réelles de GTC**.

## Cycle : modèle « ETAT CHIFFRE D'AFFAIRE »
- Export mensuel au format exact de l'état de la comptabilité (TOTAL, COMPTANT, CREDIT, RECOUVREMENT, TOTAL
  RECETTE ; Total M-1, Total N-1, variations, créances début/fin de mois), formules Excel vivantes.
- Créances calculées (Sage en lecture seule, ou fiches si soldes d'ouverture complets), sinon `n/d`.
- Import d'un état existant avec contrôles : libellés, créances incohérentes ou non mises à jour, Total M-1 faux.
  5 erreurs relevées sur les deux exemples 2025.
- 135 tests réussis.
