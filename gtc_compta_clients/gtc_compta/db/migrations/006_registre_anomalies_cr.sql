-- Registre des anomalies du rapport commercial (CR) : conservees jusqu'a resolution, pour que le
-- solde de chaque client reste juste meme sans consulter Sage.
CREATE TABLE anomalies_cr (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER REFERENCES import_batches(id),
  agence TEXT NOT NULL, date_rapport TEXT NOT NULL, feuille TEXT, ligne INTEGER,
  code TEXT NOT NULL, gravite TEXT NOT NULL, impact_solde INTEGER NOT NULL DEFAULT 1,
  motif TEXT NOT NULL, contenu TEXT, client_libelle TEXT, ct_num TEXT, reference TEXT,
  montant INTEGER, colonne TEXT,
  statut TEXT NOT NULL DEFAULT 'OUVERTE',     -- OUVERTE / RESOLUE / IGNOREE / INFORMATION
  resolution TEXT, resolu_par TEXT, resolu_le TEXT, movement_id INTEGER,
  cree_le TEXT NOT NULL);
CREATE INDEX ix_anocr_statut ON anomalies_cr(statut, impact_solde);
CREATE INDEX ix_anocr_client ON anomalies_cr(ct_num, statut);
CREATE INDEX ix_anocr_ref ON anomalies_cr(reference, code);
