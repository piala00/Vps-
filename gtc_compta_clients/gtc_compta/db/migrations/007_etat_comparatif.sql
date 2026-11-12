-- Etat comparatif : chiffres de chaque journee du rapport commercial et rapprochement des ventes avec Sage.
CREATE TABLE etat_comparatif_jours (
  agence TEXT NOT NULL, date_jour TEXT NOT NULL,
  vente_comptant INTEGER NOT NULL DEFAULT 0, vente_credit INTEGER NOT NULL DEFAULT 0,
  total_ventes INTEGER NOT NULL DEFAULT 0, recouvrements INTEGER NOT NULL DEFAULT 0,
  recette INTEGER NOT NULL DEFAULT 0, acompte INTEGER NOT NULL DEFAULT 0,
  total_ventes_cellule_cr INTEGER,              -- cellule du CR qui calcule la vente totale (2e TOTAL VENTES)
  total_ventes_retenu INTEGER,                  -- factures + avoirs effectivement integres aux fiches
  pieces_cr TEXT,                               -- factures / avoirs du CR de la journee (JSON), pour le pointage
  ventes_sage INTEGER, ecart_sage INTEGER,
  statut_sage TEXT NOT NULL DEFAULT 'NON_VERIFIE', -- NON_VERIFIE / CONCORDANT / ECART / SAGE_INDISPONIBLE
  detail_sage TEXT, verifie_le TEXT, verifie_par TEXT,
  source TEXT, batch_id INTEGER, maj_le TEXT NOT NULL,
  PRIMARY KEY (agence, date_jour));
-- Totaux de reference saisis dans la feuille RECAP du rapport (TOTAL N-1, TOTAL M-1), faute de donnees detaillees.
CREATE TABLE etat_comparatif_references (
  agence TEXT NOT NULL, annee INTEGER NOT NULL, mois INTEGER NOT NULL,
  type TEXT NOT NULL,                           -- N-1_SAISI_RECAP / M-1_SAISI_RECAP (mois concerne = annee/mois)
  vente_comptant INTEGER, vente_credit INTEGER, total_ventes INTEGER, recouvrements INTEGER,
  recette INTEGER, acompte INTEGER, source TEXT, maj_le TEXT NOT NULL,
  PRIMARY KEY (agence, annee, mois, type));
