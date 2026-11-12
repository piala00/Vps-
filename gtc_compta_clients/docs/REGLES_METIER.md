# Règles métier et comptables implémentées

## Montants et signes
- Montants en **entiers FCFA**. Une cellule avec des centimes non nuls est signalée, jamais arrondie en silence.
- Sens `D` : augmente la créance client. Sens `C` : la diminue. Solde > 0 : client débiteur.

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
3. Appariement : par EC_No déjà lié, puis par référence normalisée (`EC_RefPiece` ou `EC_Piece`) et sens.
   Les écritures multiples de même référence (agrégées ou éclatées) sont sommées.
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
