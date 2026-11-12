# Rapport de tests

Exécution : `python -m pytest -q`, Python 3.12, Linux (environnement de développement), le 12/11/2026.
**Résultat : 135 tests réussis, 0 échec.**

Le parseur est testé sur une **copie anonymisée du rapport réel** (jours 01, 03, 12 et 14 de
`10 RC OCT.xlsx`), avec les chiffres de référence du classeur : comptages, totaux `TOTAL VENTES` /
`TOTAL DE VERSEMENTS`, cas limites réels. Les parcours de bout en bout (import → rapprochement →
impression) utilisent des données synthétiques de même structure et un **Sage fictif**. La concordance
avec le vrai Sage reste à établir.

## Correspondance avec les critères d'acceptation (§16)
| N° | Critère | Test(s) | État |
|---|---|---|---|
| 1 | Seules les deux sections utiles ; totaux et caisse exclus | `test_cas1_*`, `test_reel_*` | OK sur le **rapport réel** (31 jours analysés) |
| 2 | BC + facture compté une fois ; BC seul sans créance | `test_cas2_*` | OK |
| 3 | Réimport : zéro doublon | `test_cas3_reimport_zero_doublon`, `test_cas3_montant_modifie_conflit_sans_doublon` | OK |
| 4 | Solde progressif exact | `test_cas4_solde_progressif`, `test_solde_non_garanti_sans_ouverture` | OK |
| 5 | Concordance : fiche validée + preuve | `test_cas5_cas6_concordance_et_ecart` | OK (Sage fictif) |
| 6 | Écart : fiche en anomalie, autres validées | idem | OK (Sage fictif) |
| 7 | Sage indisponible : aucune fausse validation | `test_cas7_sage_indisponible` | OK |
| 8 | Écriture diverse : détectée, reprise sans double | `test_cas8_*`, `test_option_b_*` | OK |
| 9 | BC déjà inclus : pas de double comptage | `test_cas9_*` | OK (formule réelle Sage non établie) |
| 10 | Facture échue selon politique | `test_cas10_*` | OK |
| 11 | Solde confirmé / pointage détaillé | `test_cas11_*` | OK |
| 12 | PDF disponible / absent | `test_cas12_*` | OK |
| 13 | Impression différée, recto verso, report, séparation | `test_cas13_*`, `test_annulation_job_libere_lignes` | OK (PDF) ; duplex physique non testé |
| 14 | Écriture rétroactive : alerte | `test_cas14_*`, `test_correction_tracee_invalide_fiche` | OK |
| 15 | Windows 10/11 : navigation, packaging, impression | — | **NON FAIT** (pas de poste Windows) |

## Validation sur le rapport réel complet (31 jours, hors dépôt)
`python tools/analyser_rapport.py "10 RC OCT.xlsx"` :
- 4 218 factures, 126 avoirs, 2 537 acomptes imputés sur factures comptant, 913 reçus (+4 reçus négatifs) extraits ; 1 350 BC/BL seuls, 106 annulées,
  30 factures à montant nul, versements de caisse exclus (COMPTE DE LIAISON traité comme un client) ;
- **31/31 jours** : le total du rapport est égal à la somme des lignes, et la somme des lignes est égale à
  retenu + exclu + bloqué (aucun montant oublié) ;
- 8 lignes bloquantes sur le mois (n° de BC portant une facture) ; les 4 reçus négatifs sont traités comme
  annulations de reçus (3 liés automatiquement, 1 en alerte) ; même n° de facture pour deux clients signalé.

Contrôle croisé avec la feuille RECAP : RECOUVREMENTS extraits = 3 942 549 420 = RECAP ; ventes comptant et
à terme des feuilles = RECAP ; colonne ACOMPTE de RECAP erronée les 04/10 et 21/10 (voir MAPPING_RAPPORT.md).

Volume (base SQLite) : import du mois complet (7 705 mouvements, 26 lots) en 0,4 s. Le réimport des mêmes
données depuis un autre fichier insère 0 mouvement. La fiche la plus chargée (2 414 lignes) est calculée en 16 ms.

## Second mois réel (septembre 2026)
`python tools/analyser_rapport.py "09 RC SEPT.xlsx"` : 30/30 jours cohérents sans modification des règles ;
RECAP identique aux feuilles. Jeu anonymisé `tests/fixtures/RC_SEPT_2026_ANONYMISE.xlsx` (jours 09, 18, 24, 25).
Import enchaîné septembre + octobre : 16 314 mouvements, 0 rejet, 0,9 s.

## État comparatif (avril → octobre 2026)
`tools/etat_comparatif.py` : chiffres journaliers identiques à la feuille RECAP pour vente comptant, vente à terme,
total ventes et recouvrements, sur les 214 journées (hors ACOMPTE, faux dans RECAP le 4 et le 21) ; cellule
« vente totale » du CR = comptant + crédit chaque jour. Rapprochement Sage testé avec le Sage fictif (concordance,
écart expliqué pièce par pièce, Sage indisponible).

## Vérification sur sept mois (avril → octobre 2026)
`tools/verifier_mois.py` sur 7 rapports : **214/214 journées cohérentes, aucun montant non expliqué** ;
12 écarts RECAP (colonne ACOMPTE, le 4 et le 21 de chaque mois) ; 32 feuilles à date imprimée fausse (mai) ;
440 anomalies au registre, dont 177 avec impact sur un solde restées ouvertes à traiter. Détail :
[CATALOGUE_ERREURS_CR.md](CATALOGUE_ERREURS_CR.md). Jeux anonymisés : avril (10, 24), mai (18, 29), juin (17, 23),
juillet (11), août (04, 08, 11), septembre (09, 18, 24, 25), octobre (01, 03, 12, 14) : contrôle automatique
d'absence de noms réels (2 430 noms vérifiés).

## Vérification multi-mois (août + septembre + octobre 2026)
`tools/verifier_mois.py` sur 93 feuilles : 93/93 jours cohérents ; 6 écarts RECAP (tous dans la colonne
ACOMPTE) ; 9/10 reçus négatifs liés ; 28 factures comptant signalées (16 BC de juillet, non fourni, et des
erreurs de saisie réelles). Jeu anonymisé d'août : `tests/fixtures/RC_AOUT_2026_ANONYMISE.xlsx`.

## Vérification multi-mois (septembre + octobre 2026)
`tools/verifier_mois.py` : 62/62 jours cohérents ; 4 écarts RECAP (colonne ACOMPTE) ; 23 factures comptant
sans acompte connu sur leur BC (15 BC d'août, 8 erreurs de saisie réelles) ; 6 reçus négatifs dont 4 liés.

## Autres vérifications effectuées
- Interface réelle lancée sous Xvfb : les 10 modules s'affichent sans erreur (`tools/captures.py`, captures dans `docs/captures/`).
- Spec PyInstaller : compilation réussie sous Linux. L'exécutable démarre et reste ouvert 12 s sans erreur.
- Fichiers `.bat` / `.bas` / `.ps1` : 100 % ASCII, CRLF.

## Bugs trouvés et corrigés pendant ce cycle
- En-têtes de colonnes signalés à tort comme anomalies : corrigé.
- Section « DEPENSES » non détectée comme fin des reçus quand le titre est en colonne C : corrigé.
- Montant négatif sur un type AVOIR : sens inversé deux fois. Corrigé et testé.
- Index PDF : numéro de pièce mal extrait d'un nom de fichier avec espaces. Corrigé.
- Retour des tâches de fond vers Tk depuis un thread secondaire : remplacé par une file thread-safe.
- Chevauchement de texte dans le pied de la fiche PDF : corrigé.
- (cycle 2, rapport réel) Colonne F mal interprétée (montant de BC) alors qu'il s'agit d'ACOMPTES encaissés :
  traitement ajouté, sinon chaque client payant comptant serait apparu débiteur à tort.
- (cycle 2) `FVCB` paramétré en facture : ce sont des avoirs (119/119 négatifs). Corrigé.
- (cycle 2) Même n° de facture pour deux clients non détecté : contrôle ajouté (rapport et import).
- (cycle 2) Anonymiseur : libellé `VERSEMENT CAISSE RECETTE` pseudonymisé à tort. Corrigé ; le jeu
  anonymisé donne désormais exactement les mêmes résultats que les feuilles réelles.

## Liste détaillée
- [OK] tests/test_anomalies.py::test_anomalies_du_rapport_conservees_jusqu_a_resolution
- [OK] tests/test_anomalies.py::test_integration_d_une_facture_corrigee
- [OK] tests/test_anomalies.py::test_meme_recu_saisi_deux_jours_meme_client
- [OK] tests/test_anomalies.py::test_meme_numero_de_recu_pour_deux_clients_jours_differents
- [OK] tests/test_anomalies.py::test_montant_different_pour_une_piece_deja_saisie
- [OK] tests/test_anomalies.py::test_ligne_rejetee_puis_reintegree_apres_correspondance
- [OK] tests/test_anomalies.py::test_anomalie_resolue_automatiquement_quand_l_import_lie_le_recu
- [OK] tests/test_anomalies.py::test_ignorer_exige_un_motif
- [OK] tests/test_anomalies.py::test_catalogue_couvre_toutes_les_anomalies_reelles
- [OK] tests/test_anomalies.py::test_reel_avril_recus_au_numero_tronque_7RC
- [OK] tests/test_anomalies.py::test_reel_avril_facture_annulee_compensee_par_avoir
- [OK] tests/test_anomalies.py::test_reel_mai_avoir_au_prefixe_tronque_FRC
- [OK] tests/test_anomalies.py::test_reel_mai_trois_numeros_de_facture_pour_deux_clients
- [OK] tests/test_anomalies.py::test_reel_juin_facture_saisie_en_comptant_et_en_vat
- [OK] tests/test_anomalies.py::test_reel_juin_commentaire_a_la_place_du_client
- [OK] tests/test_anomalies.py::test_reel_juillet_numero_de_preparation_de_livraison
- [OK] tests/test_anomalies.py::test_date_feuille_du_modele_non_mise_a_jour
- [OK] tests/test_etat_comparatif.py::test_valeurs_jour_reel_01_octobre
- [OK] tests/test_etat_comparatif.py::test_recette_selon_le_modele_recap
- [OK] tests/test_etat_comparatif.py::test_rapprochement_ventes_ecart_explique_piece_par_piece
- [OK] tests/test_etat_comparatif.py::test_rapprochement_ventes_concordant
- [OK] tests/test_etat_comparatif.py::test_rapprochement_ventes_sage_indisponible
- [OK] tests/test_etat_comparatif.py::test_nouveaux_chiffres_du_cr_remettent_le_controle_a_faire
- [OK] tests/test_etat_comparatif.py::test_tableau_du_mois_et_export_excel
- [OK] tests/test_etat_comparatif.py::test_references_saisies_dans_recap
- [OK] tests/test_etat_comparatif.py::test_creance_fin_de_mois_depuis_sage
- [OK] tests/test_etat_comparatif.py::test_creance_non_disponible_sans_sage_ni_soldes_d_ouverture
- [OK] tests/test_etat_comparatif.py::test_import_d_un_etat_chiffre_d_affaire_existant
- [OK] tests/test_etat_comparatif.py::test_creances_non_mises_a_jour_detectees
- [OK] tests/test_flux.py::test_import_et_rejet_client_non_mappe
- [OK] tests/test_flux.py::test_cas3_reimport_zero_doublon
- [OK] tests/test_flux.py::test_cas3_montant_modifie_conflit_sans_doublon
- [OK] tests/test_flux.py::test_cas4_solde_progressif
- [OK] tests/test_flux.py::test_solde_non_garanti_sans_ouverture
- [OK] tests/test_flux.py::test_cas5_cas6_concordance_et_ecart
- [OK] tests/test_flux.py::test_cas7_sage_indisponible
- [OK] tests/test_flux.py::test_operateur_ne_valide_pas_automatiquement
- [OK] tests/test_flux.py::test_cas8_ecriture_diverse_reprise_option_a
- [OK] tests/test_flux.py::test_option_b_ne_force_pas_egalite
- [OK] tests/test_flux.py::test_cas14_ecriture_retroactive
- [OK] tests/test_flux.py::test_correction_tracee_invalide_fiche
- [OK] tests/test_flux.py::test_champs_manuels_survivent_synchro
- [OK] tests/test_flux.py::test_correspondance_jamais_automatique_sur_ressemblance
- [OK] tests/test_flux.py::test_permissions
- [OK] tests/test_flux.py::test_fichier_correspondances_export_import
- [OK] tests/test_flux.py::test_annulation_recu_liee_jour_precedent
- [OK] tests/test_flux.py::test_import_refuse_sens_contraire_a_la_regle
- [OK] tests/test_flux.py::test_appariement_independant_de_la_representation_sage
- [OK] tests/test_flux.py::test_migration_004_convertit_les_anciens_signes
- [OK] tests/test_flux.py::test_recu_negatif_origine_trouvee_dans_sage
- [OK] tests/test_flux.py::test_recu_negatif_les_deux_recus_sur_le_meme_compte
- [OK] tests/test_flux.py::test_recu_negatif_sage_indisponible
- [OK] tests/test_flux.py::test_recu_negatif_comptes_differents_a_analyser
- [OK] tests/test_flux.py::test_septembre_recu_negatif_lie_au_recu_de_la_veille
- [OK] tests/test_flux.py::test_facture_comptant_acompte_sur_bc_anterieur
- [OK] tests/test_flux.py::test_facture_comptant_n_de_bc_d_un_autre_client
- [OK] tests/test_flux.py::test_facture_comptant_issue_d_un_bc_en_bp
- [OK] tests/test_flux.py::test_facture_comptant_colonne_b_non_bc_avec_acompte_sur_la_ligne
- [OK] tests/test_flux.py::test_historique_bons_mois_precedent
- [OK] tests/test_flux.py::test_recu_negatif_ecrit_avant_le_recu_positif_dans_la_feuille
- [OK] tests/test_modules.py::test_cas9_bc_deja_inclus_pas_double_compte
- [OK] tests/test_modules.py::test_cas9_bc_non_inclus_ajoute_une_fois
- [OK] tests/test_modules.py::test_cas10_facture_echue_selon_politique
- [OK] tests/test_modules.py::test_solvabilite_donnees_insuffisantes
- [OK] tests/test_modules.py::test_cas11_solde_confirme_par_client
- [OK] tests/test_modules.py::test_cas11_ecart_ouvre_pointage_detaille
- [OK] tests/test_modules.py::test_cas12_pdf_disponible_ou_absent
- [OK] tests/test_modules.py::test_liens_messagerie
- [OK] tests/test_modules.py::test_cas13_impression_differee_recto_verso
- [OK] tests/test_modules.py::test_cas13_report_de_solde_et_pagination
- [OK] tests/test_modules.py::test_annulation_job_libere_lignes
- [OK] tests/test_modules.py::test_sql_ecriture_interdite[UPDATE F_COMPTET SET CT_Intitule='x']
- [OK] tests/test_modules.py::test_sql_ecriture_interdite[SELECT 1; DELETE FROM F_ECRITUREC]
- [OK] tests/test_modules.py::test_sql_ecriture_interdite[SELECT * INTO T FROM F_COMPTET]
- [OK] tests/test_modules.py::test_sql_ecriture_interdite[EXEC sp_who]
- [OK] tests/test_modules.py::test_sql_ecriture_interdite[DROP TABLE x]
- [OK] tests/test_modules.py::test_requetes_livrees_lecture_seule
- [OK] tests/test_modules.py::test_config_refuse_mot_de_passe
- [OK] tests/test_modules.py::test_sauvegarde_restauration
- [OK] tests/test_modules.py::test_transaction_atomique
- [OK] tests/test_parser.py::test_reel_comptages[01-124-1-84-23-8]
- [OK] tests/test_parser.py::test_reel_comptages[03-165-6-85-38-8]
- [OK] tests/test_parser.py::test_reel_comptages[12-247-2-156-62-9]
- [OK] tests/test_parser.py::test_reel_comptages[14-181-32-97-28-1]
- [OK] tests/test_parser.py::test_reel_totaux_du_rapport_et_aucun_montant_oublie[01]
- [OK] tests/test_parser.py::test_reel_totaux_du_rapport_et_aucun_montant_oublie[03]
- [OK] tests/test_parser.py::test_reel_totaux_du_rapport_et_aucun_montant_oublie[12]
- [OK] tests/test_parser.py::test_reel_totaux_du_rapport_et_aucun_montant_oublie[14]
- [OK] tests/test_parser.py::test_reel_jour01_montants
- [OK] tests/test_parser.py::test_reel_colonnes_bon_de_commande_jamais_exploitees
- [OK] tests/test_parser.py::test_reel_avoir_fvcb_et_bc_seul
- [OK] tests/test_parser.py::test_reel_bc_avec_montant_facture_bloque
- [OK] tests/test_parser.py::test_reel_meme_numero_pour_deux_clients
- [OK] tests/test_parser.py::test_reel_recus_negatifs_annulent_le_recu_errone
- [OK] tests/test_parser.py::test_recu_negatif_sans_original_avertit
- [OK] tests/test_parser.py::test_reel_compte_de_liaison_est_un_client
- [OK] tests/test_parser.py::test_cas1_seules_les_deux_sections_utiles
- [OK] tests/test_parser.py::test_cas1_entete_recus_detectee_dynamiquement
- [OK] tests/test_parser.py::test_cas2_bc_plus_facture_compte_une_fois
- [OK] tests/test_parser.py::test_facture_comptant_soldee_par_acompte_impute
- [OK] tests/test_parser.py::test_mode_facture_seule
- [OK] tests/test_parser.py::test_regle_des_signes
- [OK] tests/test_parser.py::test_reel_regle_des_signes_sur_le_mois
- [OK] tests/test_parser.py::test_type_non_parametre_bloquant
- [OK] tests/test_parser.py::test_compte_collectif_ventilation_analytique
- [OK] tests/test_parser.py::test_client_sans_correspondance_signale
- [OK] tests/test_parser.py::test_jour02_cas_bloquants
- [OK] tests/test_parser.py::test_date_feuille_differente_bloquante
- [OK] tests/test_parser.py::test_entete_recus_absente_bloquante
- [OK] tests/test_parser.py::test_parse_montant[1500-1500]
- [OK] tests/test_parser.py::test_parse_montant[1500.0-1500]
- [OK] tests/test_parser.py::test_parse_montant[1 250 000-1250000]
- [OK] tests/test_parser.py::test_parse_montant[1.250.000-1250000]
- [OK] tests/test_parser.py::test_parse_montant[(5 000)--5000]
- [OK] tests/test_parser.py::test_parse_montant[-200--200]
- [OK] tests/test_parser.py::test_parse_montant[12 000 FCFA-12000]
- [OK] tests/test_parser.py::test_parse_montant[-None]
- [OK] tests/test_parser.py::test_parse_montant[None-None]
- [OK] tests/test_parser.py::test_parse_montant_centimes_refuses
- [OK] tests/test_parser.py::test_classeur_prepare_aller_retour
- [OK] tests/test_parser.py::test_export_erp_ecrit_par_excel_normalise
- [OK] tests/test_parser.py::test_controle_croise_macro_application
- [OK] tests/test_parser.py::test_compte_de_liaison_conteneur
- [OK] tests/test_parser.py::test_septembre_reel[09-238-3-150-40-16206800-185834025-124993825]
- [OK] tests/test_parser.py::test_septembre_reel[18-152-11-73-32-10043100-177364600-124607850]
- [OK] tests/test_parser.py::test_septembre_reel[24-165-1-117-28-19013325-121774450-82496750]
- [OK] tests/test_parser.py::test_septembre_reel[25-143-0-86-23-21312325-247481745-115516700]
- [OK] tests/test_parser.py::test_septembre_bc_avec_facture_bloque
- [OK] tests/test_parser.py::test_aout_reel[04-145-25-6993100-127227025-117608400]
- [OK] tests/test_parser.py::test_aout_reel[08-143-43-5417950-136479425-163859050]
- [OK] tests/test_parser.py::test_aout_reel[11-244-42-12620575-180804350-144815900]
- [OK] tests/test_parser.py::test_aout_lignes_bc_sans_numero_en_colonne_c
- [OK] tests/test_parser.py::test_aout_recu_negatif_avant_le_positif_dans_la_journee
- [OK] tests/test_parser.py::test_aout_meme_numero_de_recu_pour_deux_clients
- [OK] tests/test_parser.py::test_facture_sans_numero_bloquante
