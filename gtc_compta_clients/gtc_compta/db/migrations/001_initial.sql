-- Schema initial GTC Comptabilite Clients (SQLite).
-- Montants : INTEGER en FCFA. Sens : 'D' (debit client) / 'C' (credit client).

CREATE TABLE app_settings (cle TEXT PRIMARY KEY, valeur TEXT);

CREATE TABLE roles (code TEXT PRIMARY KEY, libelle TEXT NOT NULL);
INSERT INTO roles VALUES ('operateur','Operateur'),
  ('comptable_controleur','Comptable controleur'),
  ('responsable','Responsable (derogations)'),
  ('admin','Administrateur technique');

CREATE TABLE users (
  login TEXT PRIMARY KEY, nom TEXT NOT NULL,
  role TEXT NOT NULL REFERENCES roles(code), actif INTEGER NOT NULL DEFAULT 1);

CREATE TABLE audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  horodatage TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  utilisateur TEXT NOT NULL, action TEXT NOT NULL, objet TEXT, details TEXT);
CREATE INDEX ix_audit_action ON audit_events(action, horodatage);

-- Referentiel clients (synchronise depuis Sage, lecture seule) ----------------
CREATE TABLE clients (
  ct_num TEXT PRIMARY KEY, intitule TEXT NOT NULL, telephone TEXT, ville TEXT,
  encours_autorise INTEGER, est_collectif INTEGER NOT NULL DEFAULT 0,
  sage_synchro_le TEXT);
CREATE INDEX ix_clients_intitule ON clients(intitule);

-- Champs manuels : survivent a chaque rafraichissement (cle = code tiers stable)
CREATE TABLE client_manual_fields (
  ct_num TEXT PRIMARY KEY REFERENCES clients(ct_num),
  zone TEXT, delai_reglement_jours INTEGER, notes_recouvrement TEXT,
  contacts TEXT, telephone_whatsapp TEXT, telegram TEXT, preference_communication TEXT,
  modifie_le TEXT, modifie_par TEXT);

-- Correspondances verifiees libelle du rapport -> code tiers Sage
CREATE TABLE client_aliases (
  libelle_normalise TEXT PRIMARY KEY, libelle_original TEXT NOT NULL,
  ct_num TEXT NOT NULL REFERENCES clients(ct_num),
  verifie_par TEXT NOT NULL, verifie_le TEXT NOT NULL);

-- Imports ----------------------------------------------------------------------
CREATE TABLE import_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cle_lot TEXT NOT NULL UNIQUE, agence TEXT NOT NULL, date_rapport TEXT NOT NULL,
  fichier TEXT NOT NULL, feuille TEXT, empreinte_fichier TEXT NOT NULL,
  format_version TEXT NOT NULL, operateur TEXT NOT NULL,
  importe_le TEXT NOT NULL, statut TEXT NOT NULL,
  nb_inseres INTEGER NOT NULL DEFAULT 0, nb_deja_presents INTEGER NOT NULL DEFAULT 0,
  nb_conflits INTEGER NOT NULL DEFAULT 0, nb_rejets INTEGER NOT NULL DEFAULT 0);

CREATE TABLE raw_import_rows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id),
  feuille TEXT, ligne INTEGER, contenu_json TEXT NOT NULL, resultat TEXT NOT NULL, motif TEXT);
CREATE INDEX ix_raw_batch ON raw_import_rows(batch_id);

CREATE TABLE normalized_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agence TEXT NOT NULL, nature TEXT NOT NULL,          -- FACTURE / AVOIR / REGLEMENT / COMPLEMENT_SAGE
  reference_piece TEXT NOT NULL, ct_num TEXT NOT NULL REFERENCES clients(ct_num),
  date_piece TEXT NOT NULL, date_comptable TEXT,
  sens TEXT NOT NULL CHECK (sens IN ('D','C')),
  montant INTEGER NOT NULL CHECK (montant >= 0), devise TEXT NOT NULL DEFAULT 'XAF',
  libelle TEXT, bc_origine TEXT, mode_reference TEXT, acheteur_detail TEXT,
  source TEXT NOT NULL,                                  -- RAPPORT / SAGE_COMPLEMENT / CORRECTION
  batch_id INTEGER REFERENCES import_batches(id),
  source_fichier TEXT, source_feuille TEXT, source_ligne INTEGER,
  sage_ec_no INTEGER, statut TEXT NOT NULL DEFAULT 'PROVISOIRE',  -- PROVISOIRE / VALIDE / ANNULE
  remplace_id INTEGER REFERENCES normalized_movements(id),
  cree_le TEXT NOT NULL, cree_par TEXT NOT NULL, motif TEXT);
-- Unicite metier : un meme document ne peut exister qu'une fois (hors annules)
CREATE UNIQUE INDEX ux_mvt_metier ON normalized_movements(agence, nature, reference_piece, ct_num)
  WHERE statut <> 'ANNULE';
CREATE UNIQUE INDEX ux_mvt_sage ON normalized_movements(sage_ec_no)
  WHERE sage_ec_no IS NOT NULL AND statut <> 'ANNULE';
CREATE INDEX ix_mvt_client_date ON normalized_movements(ct_num, date_piece);

CREATE TABLE import_conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id),
  movement_id INTEGER NOT NULL REFERENCES normalized_movements(id),
  champ TEXT NOT NULL, valeur_existante TEXT, valeur_importee TEXT,
  statut TEXT NOT NULL DEFAULT 'OUVERT', resolu_par TEXT, resolu_le TEXT);

CREATE TABLE opening_balances (
  ct_num TEXT NOT NULL REFERENCES clients(ct_num), date_reference TEXT NOT NULL,
  solde INTEGER NOT NULL,                 -- signe : >0 debiteur (client doit)
  source TEXT NOT NULL, importe_le TEXT NOT NULL, importe_par TEXT NOT NULL,
  PRIMARY KEY (ct_num, date_reference));

-- Rapprochement Sage ---------------------------------------------------------------
CREATE TABLE sage_accounting_entries_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT, reconciliation_id INTEGER,
  ec_no INTEGER NOT NULL, ct_num TEXT NOT NULL, journal TEXT, date_ecriture TEXT,
  numero_piece TEXT, reference_piece TEXT, libelle TEXT,
  sens TEXT NOT NULL, montant INTEGER NOT NULL, capture_le TEXT NOT NULL);
CREATE INDEX ix_snap_reco ON sage_accounting_entries_snapshot(reconciliation_id);

CREATE TABLE daily_reconciliations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ct_num TEXT NOT NULL REFERENCES clients(ct_num), date_arrete TEXT NOT NULL,
  batch_id INTEGER, statut TEXT NOT NULL,
  solde_erp INTEGER, solde_sage INTEGER, ecart INTEGER,
  empreinte_sage TEXT, preuve_json TEXT, message TEXT,
  execute_le TEXT NOT NULL, execute_par TEXT NOT NULL,
  valide_le TEXT, valide_par TEXT, obsolete INTEGER NOT NULL DEFAULT 0);
CREATE INDEX ix_reco_client ON daily_reconciliations(ct_num, date_arrete);

CREATE TABLE reconciliation_discrepancies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reconciliation_id INTEGER NOT NULL REFERENCES daily_reconciliations(id),
  type TEXT NOT NULL,   -- SAGE_ABSENT_ERP / ERP_ABSENT_SAGE / MONTANT_DIFFERENT / RETROACTIF
  movement_id INTEGER, sage_ec_no INTEGER, montant_erp INTEGER, montant_sage INTEGER,
  description TEXT, statut TEXT NOT NULL DEFAULT 'OUVERT');

CREATE TABLE discrepancy_resolutions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discrepancy_id INTEGER NOT NULL REFERENCES reconciliation_discrepancies(id),
  decision TEXT NOT NULL,  -- OPTION_A_REPRISE / OPTION_B_FACTURE_GESCOM / EXPLIQUE / AUTRE
  motif TEXT NOT NULL, justificatif TEXT, decideur TEXT NOT NULL, decide_le TEXT NOT NULL,
  movement_id INTEGER);

CREATE TABLE movement_sage_links (
  movement_id INTEGER NOT NULL REFERENCES normalized_movements(id),
  sage_ec_no INTEGER NOT NULL, reconciliation_id INTEGER, lie_le TEXT NOT NULL,
  PRIMARY KEY (movement_id, sage_ec_no));

-- Pointage client --------------------------------------------------------------------
CREATE TABLE client_balance_confirmations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ct_num TEXT NOT NULL REFERENCES clients(ct_num), date_arrete TEXT NOT NULL,
  solde_client INTEGER NOT NULL, solde_sage INTEGER, ecart INTEGER,
  interlocuteur TEXT NOT NULL, canal TEXT, statut TEXT NOT NULL,  -- CONFIRME_PAR_CLIENT / EN_POINTAGE / CONTESTE
  empreinte_sage TEXT, notes TEXT, preuve TEXT,
  enregistre_le TEXT NOT NULL, enregistre_par TEXT NOT NULL, alerte_retroactive INTEGER NOT NULL DEFAULT 0);

CREATE TABLE client_pointing_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  confirmation_id INTEGER NOT NULL REFERENCES client_balance_confirmations(id),
  sage_ec_no INTEGER, date_ecriture TEXT, piece TEXT, libelle TEXT, sens TEXT, montant INTEGER,
  statut TEXT NOT NULL DEFAULT 'EN_VERIFICATION',  -- CONFIRME / CONTESTE / MANQUANT / EN_VERIFICATION
  commentaire TEXT, modifie_le TEXT, modifie_par TEXT);

-- Solvabilite -----------------------------------------------------------------------
CREATE TABLE purchase_order_credit_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, bc_reference TEXT NOT NULL, ct_num TEXT,
  montant_bc INTEGER, plafond INTEGER, risque_sage INTEGER, bc_deja_inclus INTEGER,
  risque_projete INTEGER, depassement INTEGER, versement_necessaire INTEGER,
  factures_echues_json TEXT, avis TEXT NOT NULL, motifs TEXT,
  controle_le TEXT NOT NULL, controle_par TEXT NOT NULL);

-- Documents et impressions -------------------------------------------------------------
CREATE TABLE invoice_pdf_links (
  piece TEXT PRIMARY KEY, chemin TEXT NOT NULL, source TEXT NOT NULL,
  indexe_le TEXT NOT NULL, taille INTEGER);

CREATE TABLE print_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cree_le TEXT NOT NULL, cree_par TEXT NOT NULL,
  type TEXT NOT NULL, fichier_pdf TEXT, nb_pages INTEGER, statut TEXT NOT NULL);

CREATE TABLE print_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER REFERENCES print_jobs(id),
  ct_num TEXT NOT NULL REFERENCES clients(ct_num),
  periode_debut TEXT, periode_fin TEXT, dernier_mouvement_id INTEGER,
  solde_reporte INTEGER, solde_final INTEGER, nb_pages INTEGER, version INTEGER NOT NULL,
  statut TEXT NOT NULL,            -- GENERE / IMPRIME / ANNULE
  imprime_le TEXT NOT NULL, imprime_par TEXT NOT NULL);
CREATE INDEX ix_print_client ON print_history(ct_num, statut);
