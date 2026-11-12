# GTC Comptabilité Clients

Application Windows native (Python 3 / CustomTkinter) destinée **exclusivement au service comptable** de
GLOBAL TRADE COMPANY SARL, agence de Bertoua. Elle prépare chaque journée du rapport commercial dans un
classeur intermédiaire, importe les mouvements en zone provisoire, ventile par client, **rapproche
automatiquement avec Sage Comptabilité (lecture seule)**, puis valide et imprime les fiches clients
A4 recto verso.

> **Sage reste la référence du solde comptable officiel.** L'application n'écrit jamais dans Sage.

## État actuel (v0.1.0) : lire avant utilisation
| Élément | État |
|---|---|
| Fondations, base SQLite, migrations, audit, rôles | fait, testé |
| Parseur du rapport + classeur de préparation (traitement Python de secours) | fait, **validé sur les 31 jours du rapport réel `10 RC OCT.xlsx`** (contrôle de complétude des totaux) |
| Module VBA `.bas` + script de construction du `.xlsm` | écrit, **non exécuté** (pas d'Excel dans l'environnement de développement) |
| Import idempotent, ventilation, soldes progressifs, corrections tracées | fait, testé |
| Rapprochement Sage, écarts, reprise option A/B, rétroactivité | fait, testé avec un **Sage fictif** |
| Adaptateur Sage SQL | écrit, **non vérifié sur l'installation réelle** |
| Solvabilité / BC | moteur fait ; **formule Sage non reproduite** → avis `DONNEES_INSUFFISANTES` en mode SQL |
| Pointage client, documents PDF, WhatsApp/Telegram assistés | faits, testés (hors ouverture réelle des applications) |
| Fiches A4 recto verso, registre d'impression | faits ; **modèle provisoire** (scans de la fiche papier attendus) |
| Exécutable Windows | spec PyInstaller validée par une compilation Linux ; **à compiler et tester sous Windows 10/11** |

Le détail se trouve dans [docs/JOURNAL_AVANCEMENT.md](docs/JOURNAL_AVANCEMENT.md).

## Installation (poste de développement ou Windows)
```bat
python -m pip install -r requirements-dev.txt
python -m pytest -q                 :: 87 tests
python tools\analyser_rapport.py "10 RC OCT.xlsx"   :: controle d'un rapport reel (lecture seule)
python tools\make_demo.py           :: données fictives
python tools\demo_setup.py          :: environnement de démonstration complet
python run.py --config demo\sortie\config.json
```
En production : copier `config.example.json` en `config.json`, régler `sage.mode = "sql"`, le serveur
(`GTC-LISTENER,1433`) et les bases. Le mot de passe SQL éventuel se place dans la variable d'environnement
indiquée par `sage.password_env` (jamais dans le fichier). Utiliser de préférence un compte Windows/SQL
**en lecture seule**.

Exécutable : `packaging\COMPILER.bat`, qui produit `packaging\dist\GTC_Compta_Clients\GTC_Compta_Clients.exe`.

Classeur macro : `python tools\build_template.py`, puis sous Windows avec Excel `vba\CONSTRUIRE_XLSM.bat`
(voir [docs/CLASSEUR_PREPARATION.md](docs/CLASSEUR_PREPARATION.md)).

## Flux quotidien
1. Le comptable colle la feuille du jour dans `COLLAGE` du classeur `GTC_PREPARATION_JOURNALIERE.xlsm`
   puis clique **Trier et préparer**. Si les macros sont désactivées, l'application traite elle-même `COLLAGE`.
2. **Préparation / Imports** : ouvrir le classeur, contrôler l'aperçu et les anomalies, puis **Valider l'import**.
   Les mouvements passent en zone PROVISOIRE et le rapprochement Sage du jour démarre automatiquement.
3. **Rapprochement Sage** : les fiches concordantes sont validées automatiquement, avec la preuve conservée.
   Les écarts sont analysés un par un (option A : reprise de l'écriture Sage ; option B : facture Gescom à établir).
4. **Impressions** : quand on le décide, on imprime les nouveaux mouvements validés, groupés par zone puis
   par nom, en recto verso.

## Documentation
- [Architecture et modèle de données](docs/ARCHITECTURE.md)
- [Mapping du rapport commercial (établi sur le rapport réel)](docs/MAPPING_RAPPORT.md)
- [Règles métier et comptables](docs/REGLES_METIER.md)
- [Adaptateur Sage et requêtes à vérifier](docs/SAGE_ADAPTATEUR.md)
- [Classeur de préparation .xlsm](docs/CLASSEUR_PREPARATION.md)
- [Rapport de tests](docs/RAPPORT_TESTS.md)
- [Journal d'avancement et questions ouvertes](docs/JOURNAL_AVANCEMENT.md)
- Captures réelles de l'interface : [docs/captures/](docs/captures/)
