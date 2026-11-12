# Catalogue des erreurs de CR (rapport commercial)

Établi sur **sept mois réels**, d'avril à octobre 2026 (214 journées), avec `tools/verifier_mois.py`, qui
applique le traitement réel de l'application.

**Principe.** Le logiciel doit tenir le compte de chaque client **sans dépendre de Sage**. Toute erreur de CR
qui peut fausser un solde est donc :
1. **détectée** à l'import, ou en comparant avec les jours et mois déjà importés ;
2. **conservée** dans le registre des anomalies (`anomalies_cr`, statut `OUVERTE`) ;
3. **signalée sur la fiche du client** (« N anomalie(s) CR non résolue(s) peuvent affecter ce solde ») et au
   tableau de bord ;
4. **traitée** par le comptable (Préparation / Imports → « Anomalies CR à traiter ») : intégration de la pièce
   corrigée, réintégration après correspondance, résolution ou abandon motivés. Toute action est tracée.

Une pièce douteuse n'est **jamais comptée deux fois** et n'est **jamais perdue en silence**. Sur les 214
journées, **chaque montant du rapport est retenu, exclu pour un motif connu, ou bloqué en anomalie**. Aucun
montant n'est oublié.

## Erreurs constatées (avril → octobre 2026)

| Code | Erreur des commerciaux | Cas | Impact sur le solde | Traitement dans le logiciel |
|---|---|---|---|---|
| `FACTURE_COMPTANT_SANS_ACOMPTE` | Facture comptant dont le BC n'a pas d'acompte connu. Causes : **n° de BC faux en colonne B** (chiffre manquant, BC d'un autre client), **lignes de BC jamais saisies dans le CR** (ex. 01/06 : 26 factures sur des BC17276 à BC17310 absents de tous les rapports), BC en BP facturé en comptant, acompte insuffisant ou négatif, BC de mars (avant l'historique) | 105 | **OUI** : la facture est supposée soldée par l'acompte | Alerte avec diagnostic et **BC probable** (même client, même montant, 45 jours) |
| `BC_AVEC_FACTURE` | N° de **bon** (BCCB commande, BLCB livraison, **PLCB préparation de livraison**) écrit en C à la place du n° de facture, avec un montant de facture | 30 | **OUI** : facture absente de la fiche | Bloquée. Le comptable retrouve le n° FACB dans Sage, puis « Intégrer la facture corrigée » |
| `DATE_FEUILLE` | Date imprimée (A4) fausse : **tout le rapport de mai porte des dates d'avril** (modèle non mis à jour) ; feuille du 17/04 datée du 16/04 | 23 jours (32 feuilles) | **OUI** si la mauvaise journée est collée | Import bloqué sauf **confirmation explicite** du comptable (tracée) |
| `NUMERO_PLUSIEURS_CLIENTS` | **Même n° de pièce pour deux clients** : FACB017927, FACB017928 et FACB017929 (18/05), FVCB000362 (27/07), reçu 7RCB020978 (11/08), FACB039522 (12/10) | 12 lignes (6 cas) | **OUI** : une des lignes est sur le mauvais compte | Les deux lignes restent visibles, signalées sur les deux fiches ; contrôle aussi **entre jours et entre mois** |
| `RECU_NEGATIF_SANS_ORIGINE` | Reçu négatif (contre-passation) dont le reçu annulé n'est pas trouvé dans la journée | 10 signalés, **7 liés à l'import** (jour ou mois précédent) ; restent 7RCB008601 (03/04), 7RCB015930 (23/06), 7RCB030477 (27/10) | **OUI** tant que non lié | Lien automatique ; sinon « Vérifier dans Sage » |
| `NUMERO_MAL_SAISI` | N° de pièce **tronqué** : reçus **7RC**009311 et **7RC**009273 (10/04, 7 000 000 au total) au lieu de 7RCB, avoir **FRC**000378 (29/05) au lieu de FRCB | 3 | non (montant repris) | Signalé avec le **n° Sage probable** |
| `MONTANT_H_ET_I` | **Même facture saisie en COMPTANT et en VAT** : FACB021708 (17/06, 189 000). Le TOTAL VENTES du rapport la compte deux fois | 1 | **OUI** | Une seule facture retenue (colonne selon la référence / l'acompte), signalée |
| `FACTURE_SANS_NUMERO` | Montant de facture sans n° en colonne C (17/06, 8 600) | 1 | **OUI** | Bloquée ; « Intégrer la facture corrigée » |
| `CLIENT_LIBELLE_COMMENTAIRE` | **Commentaire écrit à la place du client** : « ANNULATION VERS EN PLUS CHEZ AHMADO » (reçu 7RCB015930, 23/06) | 1 | **OUI** : aucun compte ne correspond | Bloquant |
| `FACTURE_ANNULEE_PAR_AVOIR` | Facture ANNULEE compensée par sa facture retour ANNULEE : FACB014784 / FRCB000286 (24/04, ±9 641 000) | 1 | non | Les deux pièces sont reprises (elles existent dans Sage et s'annulent) |
| `PIECE_SAISIE_DEUX_FOIS` | Même pièce reprise **un autre jour** : FACB014574 (21/04 puis 22/04, 60 000) | 1 | non : comptée une seule fois | Signalée (date de la première saisie) |
| `RECU_SANS_MONTANT` | Reçu sans montant ni client : 7RCB021355 (14/08) | 1 | à vérifier (n° annulé ou oublié) | Signalé |
| `FACTURE_MONTANT_NUL` | Facture à 0 (gratuité, avarie, bonus, « AN ») | 180 | non | Information |
| `BC_SANS_NUMERO_C` | Ligne de BC sans son n° BCCB en C (BC lu en B) | 53 | non (rien n'est comptabilisé au BC) | Information ; acompte conservé dans le registre des BC |
| `BC_SANS_NUMERO` | Ligne de BC sans aucun numéro, ni en B ni en C (agences, gros clients) | 18 | non | Information |
| — | Ligne `ANNULEE` sans montant | 1 109 | non | Ignorée |

## Erreurs de la feuille RECAP (hors fiches clients)
**Douze écarts sur sept mois, tous dans la colonne ACOMPTE, toujours le 4 et le 21 du mois** (04 et 21 avril,
juin, juillet, août, septembre, octobre). C'est presque certainement une **erreur de formule** dans les lignes
« 4 » et « 21 » de la feuille RECAP, à corriger dans le modèle. Les colonnes vente comptant, vente à terme et
recouvrements sont exactes sur les sept mois.

## Contrôles actifs sans cas constaté sur ces sept mois
| Code | Erreur | Impact | Traitement |
|---|---|---|---|
| `CONFLIT_MONTANT` | Pièce déjà saisie avec **un autre montant** | **OUI** | Montant importé non intégré ; correction tracée |
| `DOUBLON_JOUR` | Même pièce deux fois dans la journée | **OUI** | Seconde ligne rejetée et signalée |
| `TYPE_INCONNU` | Préfixe de pièce inconnu | **OUI** | Bloquée |
| `MONTANTS_H_I_DIFFERENTS` | Montants **différents** en COMPTANT et VAT | **OUI** | Bloquée |
| `ANNULEE_AVEC_MONTANT` | Ligne ANNULEE portant un montant, sans pièce compensatrice | **OUI** | Bloquée |
| `CLIENT_ABSENT` | Nom du client vide | **OUI** | Bloquée |
| `CLIENT_SANS_CORRESPONDANCE` | Client non rattaché à un code Sage | **OUI** | Rejet, puis « Réintégrer les lignes rejetées » |
| `MONTANT_ILLISIBLE` | Montant texte ou avec centimes | **OUI** | Bloquée |
| `AVOIR_POSITIF` | Avoir FRCB/FVCB positif | à vérifier | Repris tel quel au débit, signalé |
| `TOTAL_RAPPORT_FAUX` | Ligne TOTAL ≠ somme des lignes (aucun cas : sauf FACB021708, les totaux du rapport sont justes) | non | Signalée |
| `MONTANT_NON_EXPLIQUE` | Montant non interprété par l'extraction | **OUI** | Bloquant : signaler à l'administrateur |

## Consignes proposées aux commerciaux
1. En colonne C, toujours le **n° complet de la facture** (FACB / FRCB / FVCB, reçus 7RCB) dès qu'un montant
   figure en COMPTANT, VAT ou RECOUVREMENTS. Jamais le n° du BC, du BL ou de la PL, jamais un n° tronqué.
2. Un montant de facture dans **une seule colonne** : COMPTANT **ou** VAT.
3. En colonne B, recopier **exactement** le n° du BC d'origine. Toujours saisir la **ligne du BC** (avec son
   acompte) le jour où l'acompte est encaissé.
4. Un n° de reçu ou de facture ne sert **qu'une fois**, pour **un seul client**.
5. Pour corriger un reçu fait sur le mauvais compte : reçu négatif **sur le même compte, du même montant**, avec
   le **nom du client** en colonne D (jamais un commentaire), puis nouveau reçu positif sur le bon compte.
6. Écrire le nom du client **toujours de la même façon**.
7. Au début de chaque mois, **mettre à jour la date du modèle** (cellule A4) avant de saisir la première journée.
