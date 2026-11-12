# Test sur Sage (lecture seule)

Tout se fait en lecture seule : l'outil n'envoie que des `SELECT` (contrôle `verifier_lecture_seule`) et la
connexion est ouverte avec `ApplicationIntent=ReadOnly`. Rien n'est écrit dans Sage.

## 1. Installation (poste Windows qui accède au serveur SQL de Sage)
```bat
git clone -b claude/new-session-oxekgl https://github.com/piala00/Vps-.git
cd Vps-\gtc_compta_clients
py -3 -m pip install -r requirements.txt
copy config.example.json config.json
```
Dans `config.json`, section `sage` : `"mode": "sql"`, `"server"` (ex. `GTC-LISTENER,1433` ou `NOMSERVEUR\SAGE100`).
`"trusted_connection": true` si la session Windows a accès à SQL Server. Sinon, mettre `false` avec
`"username"`, et le mot de passe dans la variable `GTC_SAGE_PASSWORD` (jamais dans le fichier).

## 2. Étapes
1. `py -3 tools\verifier_sage.py --config config.json --lister-bases`
   → reporter le nom des bases dans `database_compta` (et `database_gescom`).
2. `py -3 tools\verifier_sage.py --config config.json --mois 10/2026`
   → tables et colonnes présentes, liste des journaux, journal qui porte les FACB/FRCB/FVCB
   (à mettre dans `journaux_ventes`), colonne qui contient le n° de facture (`EC_Piece` ou `EC_RefPiece`).
3. `py -3 tools\verifier_sage.py --config config.json --jour 01/10/2026 --rapport "C:\...\10 RC OCT.xlsx"`
   → ventes du jour dans Sage et comparaison pièce par pièce avec le CR (TOTAL VENTES du 01/10 : 49 662 050).
4. `py -3 tools\verifier_sage.py --config config.json --date 31/10/2026 --clients CODE1,CODE2`
   → soldes calculés à comparer avec l'écran Sage.

Chaque passage écrit `data\verification_sage_<date>.txt` (non versionné, car il contient des données clients).
Renvoyer ce fichier ou copier son contenu.
