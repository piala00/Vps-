# Journal d'avancement

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
| Classeur réel `10 RC OCT.xlsx` | mapping non vérifié (H/I, préfixes, sens des FRCB, comptant) |
| Accès en lecture seule à Sage 100 V11 (Bertoua) | requêtes non vérifiées, mode `sql` non recetté |
| Copies d'écran Sage « Solvabilité » sur quelques clients | formule de risque non établie |
| Photos ou scans recto verso de la fiche papier | modèle d'impression provisoire |
| Poste Windows 10/11 avec Excel et imprimante recto verso | `.xlsm`, exécutable et duplex non testés |
| Lien Sage ↔ PDF des factures | indexation de dossiers seulement |

### Décisions ouvertes (configuration sûre appliquée en attendant)
1. Sens comptable de chaque type de document : seuls FACB/FVCB sont pré-paramétrés en débit, à confirmer.
   Tout autre type est bloquant.
2. Politique des factures échues : « signaler » (n'impose rien).
3. Plafond à 0 dans Sage (illimité ou interdit ?) : DONNEES_INSUFFISANTES.
4. Tolérance de date entre le rapport et l'écriture Sage (pièce saisie le lendemain) : aucune ; l'écart est montré.
5. Correspondance automatique sur intitulé exact unique : désactivée (`correspondance_auto_intitule_exact`).
6. Seuil « recto verso plein » : 2 pages × lignes par page du modèle provisoire.
7. Authentification des utilisateurs : utilisateur défini dans `config.json` (à remplacer).

### Prochaines étapes
1. Analyser le vrai rapport : produire le mapping définitif, puis ajouter des tests sur une copie anonymisée d'une vraie journée.
2. Sur site : `tools/verifier_sage.py`, recette des soldes, ajustement des requêtes.
3. Établir la formule de solvabilité par concordance.
4. Construire et recetter le `.xlsm`, compiler l'exécutable, tester le duplex sur l'imprimante réelle.
5. Adapter la fiche au modèle papier réel.
6. Authentification et passage éventuel à SQL Server multi-postes.

Avancement global estimé : fondations et moteurs en place ; **aucune fonctionnalité n'est encore validée
sur les données réelles de GTC**.
