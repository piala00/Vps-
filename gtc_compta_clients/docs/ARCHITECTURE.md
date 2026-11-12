# Architecture

```
run.py                       point d'entree (--config)
gtc_compta/
  config.py                  configuration JSON externe (secrets refuses dans le fichier)
  context.py                 AppContext : config + base + adaptateur Sage + utilisateur + logs rotatifs
  money.py                   montants FCFA en entiers (jamais de float), parsing des cellules
  text.py                    normalisation des libelles et references
  db/database.py             SQLite : migrations, transactions imbriquees (savepoints), audit, sauvegarde/restauration
  db/migrations/*.sql        schema versionne
  excel/report_parser.py     extraction factures / recus d'une feuille journaliere (regles parametrables)
  excel/preparation.py       classeur de preparation : lecture COLLAGE, ecriture FACTURES/REGLEMENTS/ANOMALIES/EXPORT_ERP
  sage/base.py               interface SageAdapter + types (lecture seule)
  sage/sql_adapter.py        SQL Server via pyodbc, garde anti-ecriture, requetes surchargeables
  sage/fake.py               Sage FICTIF (tests / demonstration, signale dans l'interface)
  services/auth.py           roles et permissions
  services/clients.py        referentiel, champs manuels, correspondances verifiees, soldes d'ouverture
  services/imports.py        import idempotent, conflits, corrections tracees
  services/ledger.py         fiche client, solde progressif
  services/reconciliation.py rapprochement, ecarts, reprise option A / B, retroactivite
  services/solvency.py       avis de solvabilite BC
  services/pointing.py       confirmation de solde et pointage contradictoire
  services/documents.py      PDF factures, export, WhatsApp/Telegram assistes, extrait de grand livre
  services/printing.py       fiches A4 recto verso, file d'attente, registre
  ui/app.py, ui/pages.py     interface CustomTkinter (10 modules), taches de fond via file thread-safe
vba/                         module VBA, modele .xlsx, script de construction du .xlsm
tools/                       donnees de demo, captures, verification Sage, modele de classeur
tests/                       pytest (unitaires + parcours complets)
packaging/                       PyInstaller (spec + COMPILER.bat)
```

Les services ne dépendent pas de l'interface : chaque règle est testable sans écran. L'interface appelle
les services et exécute les opérations longues (Sage, imports, génération PDF) en tâche de fond.

## Persistance
Toute la persistance passe par `Database` (`execute/query/one/scalar/transaction/audit`). Une implémentation
SQL Server multi-utilisateurs pourra être substituée plus tard. Il faudra alors adapter le dialecte des
quelques requêtes `ON CONFLICT` / `INSERT OR IGNORE`.

## Modèle de données (migrations 001 et 002)
| Table | Rôle |
|---|---|
| `clients` | référentiel synchronisé depuis Sage (code tiers stable) |
| `client_manual_fields` | zone, délai, notes, contacts, WhatsApp/Telegram : **jamais écrasés par la synchro** |
| `client_aliases` | correspondances **vérifiées** libellé du rapport → code tiers |
| `import_batches`, `raw_import_rows`, `import_conflicts` | lots, lignes brutes et résultat ligne à ligne, conflits |
| `normalized_movements` (migration 004) | mouvements (montant entier **signé**, colonne D/C selon la règle GTC : factures au débit, reçus/acomptes au crédit, statut PROVISOIRE/VALIDE/ANNULE, provenance complète, `sage_ec_no`) ; index unique métier `(agence, nature, référence, client)` hors annulés ; unicité de `sage_ec_no` |
| `opening_balances` | soldes d'ouverture importés de Sage à une date de référence |
| `daily_reconciliations` | contrôle par client et par date : soldes, écart, empreinte Sage, preuve JSON, validation |
| `sage_accounting_entries_snapshot` | écritures Sage capturées lors du contrôle |
| `reconciliation_discrepancies`, `discrepancy_resolutions` | écarts et décisions (option A/B, explication) |
| `movement_sage_links` | appariements mouvement ↔ EC_No |
| `client_balance_confirmations`, `client_pointing_lines` | confirmations de solde et pointage ligne à ligne |
| `purchase_order_credit_checks` | historique des avis de solvabilité |
| `invoice_pdf_links` | index des PDF de factures |
| `print_jobs`, `print_history`, `printed_movements` | registre d'impression et lignes déjà imprimées |
| `alertes`, `audit_events`, `users`, `roles`, `app_settings` | alertes, piste d'audit, sécurité |

## Rôles
| Action | Opérateur | Comptable contrôleur | Responsable | Admin |
|---|:-:|:-:|:-:|:-:|
| Import, synchro, solvabilité, impression | oui | oui | oui | partiel |
| Validation de fiche, reprise d'écriture, correction, pointage | | oui | oui | |
| Dérogation | | | oui | |
| Paramètres, restauration | | | | oui |

Limite actuelle : l'utilisateur est défini dans `config.json`. Une authentification réelle (compte Windows
ou mot de passe) reste à faire avant un déploiement multi-postes.
