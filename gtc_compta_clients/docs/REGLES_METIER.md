# Règles métier et comptables implémentées

## Montants et signes : règle de la comptabilité GTC (12/11/2026)
- **Toutes les factures** (FACB, et aussi les factures retour / d'avoir FRCB et FVCB) sont enregistrées au
  **DÉBIT** du compte client **en conservant leur signe**. Un avoir est donc un débit négatif.
- **Tous les reçus et acomptes** sont enregistrés au **CRÉDIT** du compte client **en conservant leur signe**.
  Un reçu négatif (contre-passation d'un reçu fait sur un compte erroné) est donc un crédit négatif.
- Aucune inversion de colonne n'est jamais faite. L'import rejette un mouvement qui serait dans la mauvaise
  colonne (facture au crédit, reçu au débit).
- Solde = Σ débits − Σ crédits ; solde > 0 : client débiteur.
- Montants en **entiers FCFA**. Une cellule avec des centimes non nuls est signalée, jamais arrondie en silence.
- Rapprochement Sage : la comparaison porte sur l'**effet signé sur le solde** (débit +, crédit −). Un avoir
  saisi dans Sage en débit négatif ou en crédit positif est donc apparié de la même façon.

## Mouvements extraits du rapport
| Nature | Origine | Colonne | Signe |
|---|---|---|---|
| FACTURE | `FACB` avec montant en H (comptant) ou I (à terme) | Débit | celui du rapport |
| AVOIR | `FRCB` / `FVCB` | Débit | celui du rapport (négatif) |
| ACOMPTE (imputé) | facture **comptant** (colonne H) : l'acompte du BC est imputé sur la facture à la mise à jour comptable. Même pièce, même montant que la facture. Les colonnes BC (F, G) ne sont jamais exploitées | Crédit | celui de la facture |
| REGLEMENT | reçu `7RCB` (RECOUVREMENTS) ; un reçu **négatif** contre-passe un reçu fait sur un compte erroné et est lié au reçu annulé (même client, montant opposé) | Crédit | celui du rapport |

## Import
- Unicité métier : (agence, nature, référence pièce, code tiers), hors mouvements annulés (index SQL unique).
- Même lot réimporté : rejeté en entier. Même mouvement dans un autre fichier : « déjà présent ». Montant ou
  sens différent : **conflit** enregistré, sans doublon ni écrasement.
- Code tiers absent ou inconnu : ligne rejetée avec motif. L'affectation se fait **uniquement** par
  correspondance vérifiée (les suggestions par similarité sont affichées mais jamais appliquées).
- Corrections : l'ancien mouvement passe ANNULE, le nouveau porte `remplace_id`, un motif obligatoire et
  l'audit. Les fiches déjà validées à une date ≥ la pièce repassent `A_RAPPROCHER` et une alerte est créée.

## Soldes
- Le solde d'ouverture est importé de Sage à une date de référence. Sans lui, la fiche affiche
  « solde NON garanti » et le rapprochement donne `BLOQUE`.
- Solde progressif : ouverture + mouvements non annulés postérieurs à la date de référence, triés par date
  (factures avant règlements le même jour).

## Rapprochement Sage (par client, à date d'arrêté)
1. Solde Sage à la date de référence, écritures entre la référence et l'arrêté, solde Sage à l'arrêté.
   Contrôle de cohérence : solde de référence + écritures = solde à l'arrêté, sinon `EN_ATTENTE_SAGE`.
2. Sage injoignable ou extraction incomplète (nombre de lignes ≠ COUNT) : `EN_ATTENTE_SAGE`, **jamais rapproché**.
3. Appariement, dans l'ordre :
   a) par EC_No déjà lié ;
   b) par référence normalisée (`EC_RefPiece` ou `EC_Piece`) et sens. Pour un acompte, le n° de BC
      d'origine est aussi essayé. Les écritures multiples de même référence sont sommées ;
   c) repli **pour les acomptes et règlements uniquement** : même date, même sens, même montant, avec une
      correspondance **unique des deux côtés**. La méthode `DATE_SENS_MONTANT` est inscrite dans la preuve.
4. Écarts : `SAGE_ABSENT_ERP`, `ERP_ABSENT_SAGE`, `MONTANT_DIFFERENT`, `RETROACTIF` (solde Sage de référence modifié).
5. `RAPPROCHE` **uniquement si** écart nul **et** aucune ligne non appariée. La validation automatique n'a
   lieu que si l'utilisateur a le droit de valider. Elle passe les mouvements en VALIDE et enregistre
   l'utilisateur, la date et la preuve (soldes, EC_No, appariements, empreinte SHA-256 des écritures).
6. Chaque client est indépendant : un client en écart ne bloque pas la validation des autres.
7. Rétroactivité : on recalcule l'empreinte des fiches validées. Si elle a changé, la fiche repasse
   `A_RAPPROCHER`, une alerte est créée et les confirmations client concernées sont marquées.

## Écritures Sage absentes du rapport
- **Option A** : reprise comme mouvement `COMPLEMENT_SAGE` lié à l'EC_No (unicité SQL), avec motif et
  justificatif. Elle est refusée si un mouvement ERP porte déjà la même référence (risque de double
  comptabilisation). Rien n'est écrit dans Sage.
- **Option B** : décision « facture Gescom à établir », documentée. L'écart reste ouvert jusqu'à la concordance réelle.
- Aucun montant fictif n'est jamais injecté.

## Solvabilité
- Risque projeté = risque Sage + montant du BC **seulement si** l'adaptateur indique que le BC n'est pas déjà inclus.
- Composante inconnue (plafond, risque, inclusion du BC), BC introuvable, ambigu, ou Sage indisponible :
  `DONNEES_INSUFFISANTES`.
- Plafond à 0 : `DONNEES_INSUFFISANTES` par défaut (sa signification dans Sage reste à confirmer).
- Dépassement : `SOUS_CONDITION` avec le versement nécessaire, ou `DEFAVORABLE` au-delà du maximum paramétré.
- Factures échues : politique `signaler` (défaut, la règle n'étant **pas encore validée**), `sous_condition` ou `bloquer`.

## Pointage client
- `CONFIRME_PAR_CLIENT` est distinct du rapprochement Sage. Si le solde communiqué est égal au solde Sage
  à la date, le résultat est « solde confirmé — OK ». Sinon un pointage détaillé est ouvert : écritures depuis
  la dernière confirmation, avec un statut par ligne.
- La clôture « confirmé » est impossible tant qu'une ligne n'est pas confirmée.

## Impression
- Seules les lignes VALIDÉES sont imprimées. Le mode « nouveaux mouvements » reporte le solde de la dernière impression.
- Un mouvement imprimé puis annulé génère une ligne de contre-passation à la prochaine impression.
- Chaque client a un nombre de pages pair (page blanche ajoutée si nécessaire), ce qui le sépare
  physiquement des autres en recto verso. La marge de reliure alterne entre recto et verso.
- Le registre empêche les réimpressions involontaires. Une impression ratée s'annule et libère ses lignes.
