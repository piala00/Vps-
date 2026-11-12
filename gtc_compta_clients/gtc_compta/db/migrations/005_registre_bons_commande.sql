-- Registre des bons de commande lus dans les rapports (colonnes ACOMPTE et BP).
-- Information de controle uniquement : jamais comptabilise.
CREATE TABLE bons_commande_rapport (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agence TEXT NOT NULL, bc TEXT NOT NULL, piece TEXT NOT NULL, client_libelle TEXT NOT NULL,
  acompte INTEGER NOT NULL DEFAULT 0, bp INTEGER NOT NULL DEFAULT 0,
  date_rapport TEXT NOT NULL, source_ligne INTEGER, batch_id INTEGER REFERENCES import_batches(id),
  UNIQUE (agence, bc, piece, date_rapport));
CREATE INDEX ix_bcr_bc ON bons_commande_rapport(agence, bc);
CREATE INDEX ix_bcr_date ON bons_commande_rapport(agence, date_rapport, acompte);
