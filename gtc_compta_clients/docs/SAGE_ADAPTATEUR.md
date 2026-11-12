# Adaptateur Sage : statut **NON VÉRIFIÉ sur l'installation réelle**

## Principes
- Accès **lecture seule** : `verifier_lecture_seule()` refuse toute requête qui n'est pas un `SELECT`/`WITH`
  unique, ainsi que tout mot-clé d'écriture (INSERT, UPDATE, DELETE, MERGE, EXEC, INTO, DROP…).
  La connexion est ouverte avec `ApplicationIntent=ReadOnly`, puis rollback et fermeture après chaque requête.
- Recommandation : créer un login SQL ou Windows dédié, membre de `db_datareader` uniquement sur les bases
  Comptabilité et Gestion commerciale.
- Serveur par défaut : `GTC-LISTENER,1433` (listener AlwaysOn). Les bases sont lues depuis la configuration,
  jamais codées en dur.
- Chaque requête peut être remplacée par `config.json > sage > requetes > <nom>`, sans modifier le code.

## Requêtes livrées (à vérifier)
Les noms de tables et de champs reprennent ceux déjà utilisés par le connecteur GTC ERP PILOT V3
(`core/sage_connector.py` du dépôt). Ils ne sont pas garantis pour l'installation V11 de Bertoua.

| Nom | Requête | Hypothèses à confirmer |
|---|---|---|
| `clients` | `F_COMPTET WHERE CT_Type = 0` | `CT_Type = 0` = client ; `CT_Encours` = encours autorisé |
| `ecritures` | `F_ECRITUREC WHERE CT_Num = ? AND CG_Num LIKE '411%' AND EC_Date BETWEEN ...` | `EC_Sens` 0 = débit ; comptes collectifs clients en 411 ; exclusion éventuelle des écritures de simulation, brouillard ou extourne ; traitement du journal `RAN` en début d'exercice (risque de double comptage si RAN et écritures N-1 coexistent) |
| `nb_ecritures` | `COUNT(*)` identique | détection d'une extraction incomplète |
| `bon_commande` | `F_DOCENTETE WHERE DO_Domaine = 0 AND DO_Type = 1` | `DO_Type = 1` = bon de commande vente ; champ total `DO_TotalTTC` (le code existant utilise `DO_TTC`) ; référence abrégée ↔ `DO_Piece` |

## Non implémenté volontairement (aucune logique inventée)
- **Formule de solvabilité** (Informations client → Solvabilité). En mode SQL, l'adaptateur renvoie un
  risque inconnu, d'où l'avis `DONNEES_INSUFFISANTES`. Pour l'établir : sur 5 à 10 clients, relever dans
  Sage le plafond, le solde comptable, les BL et commandes en cours, les effets et le risque affiché,
  avec et sans le BC examiné. En déduire la formule, puis l'implémenter dans
  `SqlSageAdapter.composantes_solvabilite` avec `source_verifiee=True`.
- **Lien facture ↔ PDF.** À inventorier : pièces jointes Sage, dossier d'archivage, impression PDF à la
  demande, connecteurs. En attendant, l'application indexe des dossiers configurés.
- **Dates comptables et dates de pièce** : la date de pièce de l'ERP est la date du rapport, et la date
  comptable Sage est `EC_Date`. Les décalages (pièce saisie le lendemain) apparaissent comme des écarts.
  Il faut décider d'une règle de tolérance.

## Procédure de vérification sur site
```
python tools\verifier_sage.py --config config.json --date 31/10/2026 --clients CL001,CL002,CL003
```
L'outil vérifie les tables et colonnes via `INFORMATION_SCHEMA`, exécute les requêtes et calcule les soldes.
Le comptable compare ensuite chaque solde avec l'écran Sage et coche OK ou ÉCART. Le rapport texte est
déposé dans `docs/`. **Tant que cette recette n'est pas signée, le mode `sql` ne doit pas servir à valider des fiches.**
