# Mapping du rapport commercial : PROVISOIRE

> Le classeur réel **`10 RC OCT.xlsx` n'a pas été fourni**. Le mapping ci-dessous transcrit le cahier des
> charges. Il a été implémenté avec des **règles paramétrables** (`config.json > rapport`) et testé sur un
> classeur **synthétique** (`demo/RC_DEMO_SYNTHETIQUE.xlsx`). Ce classeur synthétique ne reproduit pas
> le vrai : il ne fait que représenter la structure décrite. La première tâche de la prochaine étape est
> d'analyser les 32 feuilles réelles et d'ajuster ces règles.

## Section 1 : documents commerciaux (du haut de la feuille jusqu'à l'en-tête des reçus)
| Colonne | Contenu (cahier des charges) | Traitement |
|---|---|---|
| B | référence abrégée du BC d'origine | `bc_origine` (traçabilité) |
| C | numéro du document (`FACB`, `FRCB`, `FVCB`…) | doit correspondre à `motif_document` ; préfixe → `types_documents` |
| D | client | correspondance **vérifiée** → code tiers Sage |
| E | référence (`COMPTANT`, `EN COMPTE`, `BP`, acheteur détail) | `mode_reference` ; acheteur réel pour les comptes collectifs |
| F/G | montants de **bons de commande** | **jamais** comptés comme facture (statistique « BC/BL seuls ignorés ») |
| H/I | montants de **factures** | un seul montant retenu ; H et I non vides et différents → anomalie bloquante |

Règles :
- Ligne avec un montant BC et un montant facture : **une seule facture** (test `cas2`).
- BC ou BL sans montant facture : aucune créance.
- Préfixe non paramétré : **anomalie bloquante**, jamais d'hypothèse sur le sens. Les types `FACB` et `FVCB`
  sont pré-paramétrés en FACTURE/Débit avec la mention « non confirmé ». `FRCB` n'est pas paramétré par défaut.
- Montant négatif : avoir/retour. Le sens n'est inversé qu'une seule fois (pas de double effet si le type
  est déjà paramétré en AVOIR).
- Lignes de total (`TOTAL`, `SOUS-TOTAL`, `REPORT`…) et lignes sans document : exclues.

## Section 2 : reçus de versements
- En-tête détecté **dynamiquement** par son libellé normalisé (`REÇUS DE VERSEMENTS`, accents ignorés), quelle
  que soit sa ligne (test : feuilles 01 et 02 décalées).
- Reçu : C correspond à `motif_recu` (`7RCB…`, `RCB…`), client en D, montant en `colonne_montant_recu` (F).
- Exclus : `VERSEMENT CAISSE`, `VERSEMENT BANQUE`, `LIAISON`, `CAISSE CENTRALE`, totaux (liste paramétrable).
- Fin de section : nouvelle ligne-titre (une seule cellule en majuscules sans chiffre, par exemple `DEPENSES`)
  ou N lignes vides.
- Reçu négatif ou sans client : anomalie bloquante.

## Cas particulier `CLIENTS DETAILS BTA`
Le compte reste le compte collectif Sage. La colonne E est conservée comme `acheteur_detail`, pour une
ventilation analytique sans création de faux comptes.

## Points à vérifier sur le classeur réel
1. Intitulés exacts des colonnes F/G/H/I. Que représentent H et I (comptant / en compte ? HT / TTC ?) ?
2. Liste exhaustive des préfixes de documents et leur sens comptable (FACB, FRCB, FVCB, BL, BS…).
3. Factures « COMPTANT » : le règlement figure-t-il toujours dans la section reçus ? Sinon la créance
   resterait ouverte dans l'ERP alors que Sage la solde.
4. Format des numéros (espaces, tirets, préfixe agence) et correspondance avec `EC_RefPiece` / `EC_Piece` dans Sage.
5. Autres sections présentes entre les documents et les reçus, et lignes de totaux intermédiaires.
6. Cellules fusionnées, formules, valeurs texte, cellules d'erreur.
