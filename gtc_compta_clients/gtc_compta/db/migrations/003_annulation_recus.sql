-- Recus negatifs : contre-passation d'un recu fait sur un compte errone.
ALTER TABLE normalized_movements ADD COLUMN reference_liee TEXT;
CREATE INDEX ix_mvt_reference_liee ON normalized_movements(reference_liee);
