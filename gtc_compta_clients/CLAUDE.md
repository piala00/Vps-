# GTC Comptabilité clients (GTC SARL, agence de Bertoua)

Application Windows native : Python 3.12, CustomTkinter, SQLite, openpyxl, reportlab, pyodbc (Sage 100 en
**lecture seule**), PyInstaller. Langue de travail : **français** (code, interface, documents, réponses).

## Règles absolues
- **Sage en lecture seule** : uniquement des `SELECT` (`verifier_lecture_seule` dans `gtc_compta/sage/sql_adapter.py`),
  jamais d'INSERT, UPDATE, DELETE, EXEC ou de création d'objet. Connexion avec `ApplicationIntent=ReadOnly`.
- **Ne jamais inventer** de tables Sage, de soldes, de PDF ni de résultats de tests. Si une donnée manque, l'écrire
  (`n/d`, `NON_DISPONIBLE`, `SAGE_INDISPONIBLE`).
- **Secrets hors des fichiers** : mot de passe SQL dans la variable `GTC_SAGE_PASSWORD`, jamais dans `config.json`.
- **Données clients confidentielles** : les vrais CR et les comptes rendus Sage restent hors de tout dépôt (dossier
  `data/` non versionné). Les jeux de test de `tests/fixtures` sont anonymisés (`tools/anonymiser_rapport.py`).
- Ne jamais renommer un `.xlsx` en `.xlsm` (le classeur `.xlsm` se construit avec `vba/CONSTRUIRE_XLSM.ps1`).

## Commandes
- Lancer l'application : `DEMARRER.bat` ou `py -3 run.py` (mode démo tant que `sage.mode` vaut `"demo"`).
- Tests : `py -3 -m pip install -r requirements-dev.txt` puis `py -3 -m pytest -q` (136 tests attendus au vert).
- Vérification Sage sur site : `py -3 tools\verifier_sage.py --config config.json ...` (voir `docs/TEST_SAGE.md`).
- Contrôle de plusieurs mois de CR : `tools/verifier_mois.py` ; état comparatif : `tools/etat_comparatif.py`.
- Exécutable : dossier `packaging/` (PyInstaller 6.11.1).

## Règles métier (validées par la comptabilité)
- Factures (FACB), factures retour (FRCB) et avoirs (FVCB) au **débit**, avec leur signe. Reçus (7RCB) et règlements
  au **crédit**, avec leur signe.
- Reçu négatif = annulation d'un reçu fait sur le mauvais compte (même montant, même compte), suivie d'un reçu
  positif sur le bon compte.
- Colonnes du bon de commande (F ACOMPTE « ENTREE », G BP) **jamais comptabilisées**. Seules les factures (H comptant,
  I VAT/crédit) et les reçus le sont. À la facturation, l'acompte s'annule avec la facture.
- VENTE PROMOTIONNELLE, SOURCE DU PAYS RETOUR et COMPTE DE LIAISON sont des clients (le compte de liaison sert de
  compte conteneur).
- Même n° de pièce pour deux clients, ou repris deux fois : **anomalie à signaler** (`docs/CATALOGUE_ERREURS_CR.md`).
- Le logiciel doit suivre chaque compte client **sans consulter Sage**. Sage sert au rapprochement.
- État comparatif (`docs/ETAT_COMPARATIF.md`) : modèle « ETAT CHIFFRE D'AFFAIRE ». Colonnes TOTAL, COMPTANT,
  CREDIT = TOTAL − COMPTANT, RECOUVREMENT, TOTAL RECETTE = COMPTANT + RECOUVREMENT (l'état s'arrête là). Une feuille
  par mois, puis la dernière feuille « ETAT COMPARATIF <année> » avec une ligne par mois et la comparaison avec le
  mois précédent (pas de N-1 tant que les rapports de l'année précédente manquent).
- Chaque jour, le TOTAL VENTES du CR doit égaler les ventes comptabilisées dans Sage (factures comptant + crédit,
  avoirs déduits), pièce par pièce (`rapprocher_ventes_jour`).

## Où on en est
- Moteurs, interface (11 modules), tests et documents en place. Contrôle sur sept mois réels de CR (avril à
  octobre 2026) : aucun montant inexpliqué (détails dans `docs/JOURNAL_AVANCEMENT.md`).
- **Rien n'a encore été vérifié sur le vrai Sage.** C'est l'étape en cours, depuis le PC qui accède au serveur SQL.

## Prochaine étape : test sur Sage (lecture seule)
Suivre `docs/TEST_SAGE.md`, dans l'ordre :
1. `--lister-bases` → renseigner `database_compta` (et `database_gescom`) dans `config.json`.
2. `--mois 10/2026` → tables et colonnes, liste des journaux. Identifier le journal des FACB/FRCB/FVCB
   (`sage.journaux_ventes`, « VTE » supposé) et la colonne du n° de facture (`EC_Piece` ou `EC_RefPiece`).
   Adapter `REQUETES` dans `sql_adapter.py` (ou `sage.requetes` dans `config.json`) si besoin.
3. `--jour 01/10/2026 --rapport "<10 RC OCT.xlsx>"` → TOTAL VENTES du CR attendu : 49 662 050. Puis tous les jours
   du mois (module État comparatif → « Vérifier les ventes du mois avec Sage »).
4. Soldes de quelques clients comparés à l'écran Sage, puis calcul des créances de fin de mois.
5. Vérifier dans Sage les reçus négatifs non rattachés : 7RCB008601 (03/04), 7RCB015930 (23/06), 7RCB030477 (27/10).
6. Requête des BC (`bon_commande` sur `F_DOCENTETE`, `DO_Type` à confirmer) et recherche de la facture issue d'un BC.

## Questions encore ouvertes
- À quelle agence appartiennent les exemples d'état 2025 (`livrables/ETAT_CA_2025_REPRODUIT.xlsx`) ?
- D'où viennent les « TOTAL M-1 » saisis à la main dans la feuille RECAP des CR ?
