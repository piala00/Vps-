# Rapport de tests

Exécution : `python -m pytest -q`, Python 3.12, Linux (environnement de développement), le 12/11/2026.
**Résultat : 56 tests réussis, 0 échec.**

Ces tests utilisent des **données synthétiques** et un **Sage fictif**. Ils prouvent les règles
implémentées, pas leur concordance avec le vrai rapport ni avec le vrai Sage.

## Correspondance avec les critères d'acceptation (§16)
| N° | Critère | Test(s) | État |
|---|---|---|---|
| 1 | Seules les deux sections utiles ; totaux et caisse exclus | `test_cas1_*` | OK (synthétique) |
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

## Liste détaillée
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
- [OK] tests/test_parser.py::test_cas1_seules_les_deux_sections_utiles
- [OK] tests/test_parser.py::test_cas1_entete_recus_detectee_dynamiquement
- [OK] tests/test_parser.py::test_cas2_bc_plus_facture_compte_une_fois
- [OK] tests/test_parser.py::test_avoir_negatif_pas_de_double_inversion
- [OK] tests/test_parser.py::test_type_non_parametre_bloquant
- [OK] tests/test_parser.py::test_compte_collectif_ventilation_analytique
- [OK] tests/test_parser.py::test_client_sans_correspondance_signale
- [OK] tests/test_parser.py::test_montants_h_i_incoherents_bloquants
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
