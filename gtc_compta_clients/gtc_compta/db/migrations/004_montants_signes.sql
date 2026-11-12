-- Regle comptable GTC : factures (y compris retours / avoirs) au DEBIT avec leur signe ;
-- recus et acomptes au CREDIT avec leur signe. Le montant devient signe (non nul).
CREATE TABLE normalized_movements_v4 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agence TEXT NOT NULL, nature TEXT NOT NULL,
  reference_piece TEXT NOT NULL, ct_num TEXT NOT NULL REFERENCES clients(ct_num),
  date_piece TEXT NOT NULL, date_comptable TEXT,
  sens TEXT NOT NULL CHECK (sens IN ('D','C')),
  montant INTEGER NOT NULL CHECK (montant <> 0), devise TEXT NOT NULL DEFAULT 'XAF',
  libelle TEXT, bc_origine TEXT, mode_reference TEXT, acheteur_detail TEXT,
  source TEXT NOT NULL,
  batch_id INTEGER REFERENCES import_batches(id),
  source_fichier TEXT, source_feuille TEXT, source_ligne INTEGER,
  sage_ec_no INTEGER, statut TEXT NOT NULL DEFAULT 'PROVISOIRE',
  remplace_id INTEGER REFERENCES normalized_movements(id),
  cree_le TEXT NOT NULL, cree_par TEXT NOT NULL, motif TEXT, reference_liee TEXT);
INSERT INTO normalized_movements_v4
SELECT id, agence,
  CASE WHEN nature = 'ANNULATION_RECU' THEN 'REGLEMENT' ELSE nature END,
  reference_piece, ct_num, date_piece, date_comptable,
  CASE WHEN source <> 'SAGE_COMPLEMENT' AND nature = 'AVOIR' THEN 'D'
       WHEN source <> 'SAGE_COMPLEMENT' AND nature IN ('ANNULATION_RECU', 'ACOMPTE', 'REGLEMENT') THEN 'C'
       ELSE sens END,
  CASE WHEN source <> 'SAGE_COMPLEMENT' AND nature = 'AVOIR' AND sens = 'C' THEN -montant
       WHEN source <> 'SAGE_COMPLEMENT' AND nature IN ('ANNULATION_RECU', 'ACOMPTE', 'REGLEMENT') AND sens = 'D' THEN -montant
       ELSE montant END,
  devise, libelle, bc_origine, mode_reference, acheteur_detail, source, batch_id, source_fichier,
  source_feuille, source_ligne, sage_ec_no, statut, remplace_id, cree_le, cree_par, motif, reference_liee
FROM normalized_movements;
DROP TABLE normalized_movements;
ALTER TABLE normalized_movements_v4 RENAME TO normalized_movements;
CREATE UNIQUE INDEX ux_mvt_metier ON normalized_movements(agence, nature, reference_piece, ct_num)
  WHERE statut <> 'ANNULE';
CREATE UNIQUE INDEX ux_mvt_sage ON normalized_movements(sage_ec_no)
  WHERE sage_ec_no IS NOT NULL AND statut <> 'ANNULE';
CREATE INDEX ix_mvt_client_date ON normalized_movements(ct_num, date_piece);
CREATE INDEX ix_mvt_reference_liee ON normalized_movements(reference_liee);
