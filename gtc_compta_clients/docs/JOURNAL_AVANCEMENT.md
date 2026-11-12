# Journal d'avancement

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
