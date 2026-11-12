-- Lignes deja imprimees (evite les reimpressions involontaires et gere les annulations)
CREATE TABLE printed_movements (
  movement_id INTEGER NOT NULL REFERENCES normalized_movements(id),
  print_history_id INTEGER NOT NULL REFERENCES print_history(id),
  type TEXT NOT NULL DEFAULT 'NORMAL',     -- NORMAL / ANNULATION
  PRIMARY KEY (movement_id, type));
CREATE TABLE alertes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cree_le TEXT NOT NULL, type TEXT NOT NULL,
  ct_num TEXT, message TEXT NOT NULL, statut TEXT NOT NULL DEFAULT 'OUVERTE');
