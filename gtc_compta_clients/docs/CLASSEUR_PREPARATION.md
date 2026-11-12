# Classeur de préparation `GTC_PREPARATION_JOURNALIERE.xlsm`

## Pourquoi il n'est pas livré tout fait
`openpyxl` ne sait pas créer un projet VBA fonctionnel, et renommer un `.xlsx` en `.xlsm` est interdit
par le cahier des charges. Le classeur macro est donc **construit par Excel lui-même** sous Windows :

1. `python tools\build_template.py` produit `vba\GTC_PREPARATION_JOURNALIERE_modele.xlsx`, avec les feuilles
   PARAMETRES (règles identiques à `config.json`), COLLAGE, FACTURES, REGLEMENTS, ANOMALIES et EXPORT_ERP.
2. Dans Excel : Options → Centre de gestion de la confidentialité → Paramètres des macros → cocher
   « Accès approuvé au modèle d'objet du projet VBA ».
3. Lancer `vba\CONSTRUIRE_XLSM.bat`. Il importe `GTC_Preparation.bas`, ajoute les deux boutons sur `COLLAGE`
   et enregistre au format macro (FileFormat 52).

Statut : **le code VBA n'a pas pu être exécuté ici** (pas d'Excel). Il reprend les règles du parseur Python,
mais doit être recetté sous Windows : voir le plan de recette ci-dessous.

## Utilisation
1. PARAMETRES : saisir la date du rapport.
2. COLLAGE : coller la feuille du jour entière (Ctrl+A, Ctrl+C dans le rapport, puis Ctrl+V en A1).
3. **Trier et préparer** : remplit FACTURES, REGLEMENTS, ANOMALIES et EXPORT_ERP. COLLAGE n'est pas modifiée.
4. Enregistrer, puis dans l'application : Préparation / Imports → ouvrir le classeur.
5. **Réinitialiser pour une nouvelle journée** : propose d'abord une copie datée, puis vide le classeur après confirmation.

Le classeur ne connaît pas les codes tiers Sage. L'application les complète à l'import à partir des
correspondances vérifiées, et les lignes non reconnues sont rejetées avec un motif.

## Secours si les macros sont désactivées
Si `EXPORT_ERP` est vide, l'application traite elle-même la feuille `COLLAGE` avec les mêmes règles (Python).
Le bouton « Créer un classeur de préparation depuis une feuille du rapport » produit aussi un classeur
intermédiaire `.xlsx`, sans macro, en lisant le rapport en lecture seule.

## Recette du .xlsm (à faire sous Windows)
- [ ] Feuille 01 du vrai rapport collée : les mouvements extraits sont identiques à ceux du traitement Python.
- [ ] Totaux, versements de caisse et dépenses absents d'EXPORT_ERP.
- [ ] Dates et références restent du texte dans EXPORT_ERP (pas de conversion automatique).
- [ ] Réinitialisation : copie datée créée, puis classeur vidé.
