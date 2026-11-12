"""Extraction des factures et des recus d'une feuille journaliere du rapport commercial.

ATTENTION : la structure decrite ici provient du cahier des charges
(colonnes B/C/D/E/F/G/H/I, entete "RECUS DE VERSEMENTS"). Elle n'a PAS encore
ete verifiee sur le classeur reel "10 RC OCT.xlsx" (non fourni). Toutes les
regles sont parametrables dans config["rapport"].

La feuille source n'est jamais modifiee : on lit uniquement les valeurs.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import date

from ..money import MontantInvalide, parse_montant
from ..text import normaliser, normaliser_reference

COLS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def col_idx(letter: str) -> int:
    return COLS.index(letter.upper())


@dataclass
class Mouvement:
    nature: str                 # FACTURE / AVOIR / REGLEMENT
    reference_piece: str
    client_libelle: str
    montant: int                # toujours positif
    sens: str                   # D / C
    bc_origine: str = ""
    mode_reference: str = ""    # colonne E (COMPTANT, EN COMPTE, BP, acheteur)
    acheteur_detail: str = ""
    ct_num: str = ""            # renseigne par la correspondance clients
    feuille: str = ""
    ligne: int = 0
    type_document: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Anomalie:
    feuille: str
    ligne: int
    section: str
    gravite: str                # BLOQUANT / AVERTISSEMENT / INFO
    motif: str
    contenu: str
    proposition: str = ""
    statut: str = "OUVERTE"


@dataclass
class ResultatPreparation:
    feuille: str
    date_rapport: date | None
    agence: str
    factures: list[Mouvement] = field(default_factory=list)
    reglements: list[Mouvement] = field(default_factory=list)
    anomalies: list[Anomalie] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    ligne_entete_recus: int | None = None

    @property
    def mouvements(self) -> list[Mouvement]:
        return self.factures + self.reglements

    @property
    def bloquant(self) -> bool:
        return any(a.gravite == "BLOQUANT" and a.statut == "OUVERTE" for a in self.anomalies)


def _cell(row: list, letter: str):
    i = col_idx(letter)
    return row[i] if i < len(row) else None


def _texte(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _row_text(row) -> str:
    return " ".join(_texte(v) for v in row if _texte(v))


def prefixe_document(ref: str) -> str:
    """'FACB 0123' -> 'FACB' ; '7RCB045' -> 'RCB' (chiffre de tete ignore)."""
    m = re.match(r"^\d*([A-Z]+)", normaliser_reference(ref))
    return m.group(1) if m else ""


class ParseurRapport:
    def __init__(self, regles: dict, correspondances: dict[str, str] | None = None):
        self.r = regles
        self.correspondances = correspondances or {}   # libelle normalise -> ct_num
        self.re_doc = re.compile(regles["motif_document"])
        self.re_recu = re.compile(regles["motif_recu"])
        self.exclusions = [normaliser(m) for m in regles["mots_exclusion"]]
        self.collectifs = {normaliser(c) for c in regles.get("comptes_collectifs", [])}
        self.entete_recus = normaliser(regles["entete_recus"])

    # -------------------------------------------------------------------------
    def analyser(self, rows: list[list], feuille: str, agence: str,
                 date_rapport: date | None) -> ResultatPreparation:
        res = ResultatPreparation(feuille=feuille, date_rapport=date_rapport, agence=agence)
        st = {"lignes_lues": len(rows), "factures": 0, "avoirs": 0, "reglements": 0,
              "bc_seuls_ignores": 0, "totaux_exclus": 0, "hors_perimetre_exclus": 0,
              "anomalies": 0}

        idx_recus = next((i for i, r in enumerate(rows)
                          if self.entete_recus in normaliser(_row_text(r))), None)
        res.ligne_entete_recus = idx_recus + 1 if idx_recus is not None else None
        if idx_recus is None:
            res.anomalies.append(Anomalie(feuille, 0, "RECUS", "BLOQUANT",
                f"Entete '{self.r['entete_recus']}' introuvable",
                "", "Verifier que la feuille complete a ete collee"))

        fin_docs = idx_recus if idx_recus is not None else len(rows)
        self._section_documents(rows[:fin_docs], 0, res, st)
        if idx_recus is not None:
            self._section_recus(rows, idx_recus + 1, res, st)

        vus = {}
        for m in res.mouvements:
            cle = (m.nature, normaliser_reference(m.reference_piece), m.client_libelle)
            if cle in vus:
                res.anomalies.append(Anomalie(feuille, m.ligne, m.nature, "BLOQUANT",
                    f"Piece {m.reference_piece} en double (deja ligne {vus[cle]})",
                    m.reference_piece, "Supprimer le doublon ou corriger la reference"))
            vus[cle] = m.ligne

        for m in res.mouvements:
            self._affecter_client(m, res)
        st["anomalies"] = len(res.anomalies)
        res.stats = st
        return res

    # -------------------------------------------------------------------------
    def _est_exclu(self, row) -> bool:
        txt = normaliser(" ".join(_texte(_cell(row, c)) for c in "BCDE"))
        return any(re.search(r"(^|\W)" + re.escape(m) + r"(\W|$)", txt) for m in self.exclusions)

    def _section_documents(self, rows, offset, res, st):
        feuille = res.feuille
        for i, row in enumerate(rows):
            ligne = offset + i + 1
            num = _texte(_cell(row, "C"))
            client = _texte(_cell(row, "D"))
            montants_f = [_cell(row, c) for c in self.r["colonnes_facture"]]
            montants_bc = [_cell(row, c) for c in self.r["colonnes_bc"]]
            a_montant = any(_est_montant(v) for v in montants_f + montants_bc)
            if not num and not client:
                if a_montant:
                    st["totaux_exclus"] += 1
                continue
            if self._est_exclu(row):
                st["totaux_exclus"] += 1
                continue
            numn = normaliser_reference(num)
            if not self.re_doc.match(numn):
                # en-tetes de colonnes et libelles sans montant : ignores silencieusement
                if a_montant:
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "AVERTISSEMENT",
                        "Ligne avec montant mais numero de document non reconnu",
                        _row_text(row), "Verifier la colonne C"))
                continue
            try:
                vals_f = [parse_montant(v) for v in montants_f]
            except MontantInvalide as exc:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    str(exc), _row_text(row), "Corriger le montant"))
                continue
            vals_f = [v for v in vals_f if v not in (None, 0)]
            if not vals_f:
                st["bc_seuls_ignores"] += 1      # BC / BL seul : pas de creance facturee
                continue
            if len(set(vals_f)) > 1:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    "Montants facture differents dans " + "/".join(self.r["colonnes_facture"]),
                    _row_text(row), "Determiner la colonne de montant facture applicable"))
                continue
            montant = vals_f[0]
            if not client:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    "Client absent (colonne D)", _row_text(row), "Renseigner le client"))
                continue
            prefixe = prefixe_document(num)
            regle = self.r["types_documents"].get(prefixe)
            if regle is None:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    f"Type de document '{prefixe}' non parametre (nature/sens inconnus)",
                    _row_text(row), "Parametrer le type dans rapport.types_documents"))
                continue
            nature, sens = regle["nature"], regle["sens"]
            notes = "" if regle.get("confirme") else f"regle {prefixe} non confirmee"
            if montant < 0:
                # Montant negatif : avoir/retour. Si le type est deja parametre en AVOIR,
                # le signe n'est qu'une presentation : on ne l'inverse pas une 2e fois.
                montant = -montant
                notes = (notes + " ; montant negatif dans le rapport").strip(" ;")
                if nature != "AVOIR":
                    nature = "AVOIR"
                    sens = "C" if sens == "D" else "D"
            mode = _texte(_cell(row, "E"))
            m = Mouvement(nature=nature, reference_piece=num, client_libelle=client,
                          montant=montant, sens=sens, bc_origine=_texte(_cell(row, "B")),
                          mode_reference=mode, feuille=feuille, ligne=ligne,
                          type_document=prefixe, notes=notes)
            if normaliser(client) in self.collectifs:
                m.acheteur_detail = mode
            res.factures.append(m)
            st["avoirs" if nature == "AVOIR" else "factures"] += 1

    def _section_recus(self, rows, start, res, st):
        feuille = res.feuille
        col_m = self.r["colonne_montant_recu"]
        vides = 0
        for i in range(start, len(rows)):
            row = rows[i]
            ligne = i + 1
            txt = _row_text(row)
            if not txt:
                vides += 1
                if vides >= self.r.get("lignes_vides_fin_section", 8):
                    break
                continue
            vides = 0
            num = _texte(_cell(row, "C"))
            numn = normaliser_reference(num)
            if _est_entete_section(row) and not self.re_recu.match(numn):
                break                      # nouvelle section : fin des recus
            if self._est_exclu(row):
                st["totaux_exclus" if "TOTAL" in normaliser(txt) else "hors_perimetre_exclus"] += 1
                continue
            if not self.re_recu.match(numn):
                if _est_montant(_cell(row, col_m)):
                    res.anomalies.append(Anomalie(feuille, ligne, "RECUS", "AVERTISSEMENT",
                        "Ligne avec montant dans la section recus sans reference de recu",
                        txt, "Verifier s'il s'agit d'un reglement client"))
                continue
            client = _texte(_cell(row, "D"))
            try:
                montant = parse_montant(_cell(row, col_m))
            except MontantInvalide as exc:
                res.anomalies.append(Anomalie(feuille, ligne, "RECUS", "BLOQUANT", str(exc), txt,
                                              "Corriger le montant"))
                continue
            if not montant:
                res.anomalies.append(Anomalie(feuille, ligne, "RECUS", "AVERTISSEMENT",
                    "Recu sans montant", txt, "Verifier la colonne " + col_m))
                continue
            if not client:
                res.anomalies.append(Anomalie(feuille, ligne, "RECUS", "BLOQUANT",
                    "Client absent (colonne D)", txt, "Renseigner le client"))
                continue
            sens = "C"
            nature = "REGLEMENT"
            if montant < 0:
                res.anomalies.append(Anomalie(feuille, ligne, "RECUS", "BLOQUANT",
                    "Recu de montant negatif (remboursement ?)", txt, "Traitement manuel"))
                continue
            m = Mouvement(nature=nature, reference_piece=num, client_libelle=client,
                          montant=montant, sens=sens, mode_reference=_texte(_cell(row, "E")),
                          feuille=feuille, ligne=ligne, type_document=prefixe_document(num))
            if normaliser(client) in self.collectifs:
                m.acheteur_detail = m.mode_reference
            res.reglements.append(m)
            st["reglements"] += 1

    def _affecter_client(self, m: Mouvement, res: ResultatPreparation):
        ct = self.correspondances.get(normaliser(m.client_libelle))
        if ct:
            m.ct_num = ct
        else:
            res.anomalies.append(Anomalie(res.feuille, m.ligne, m.nature, "BLOQUANT",
                f"Client '{m.client_libelle}' sans correspondance verifiee vers un code tiers Sage",
                m.reference_piece, "Creer la correspondance dans Clients > Correspondances"))


def _est_montant(v) -> bool:
    """Vrai si la cellule contient un montant non nul (ou un nombre illisible)."""
    try:
        return parse_montant(v) not in (None, 0)
    except MontantInvalide:
        return bool(re.search(r"\d", str(v)))


def _est_entete_section(row) -> bool:
    """Ligne-titre : un seul texte, en majuscules, sans montant."""
    vals = [_texte(v) for v in row if _texte(v)]
    if len(vals) != 1:
        return False
    v = vals[0]
    return len(v) >= 6 and v == v.upper() and not re.search(r"\d", v)


def empreinte_mouvement(agence: str, m: Mouvement) -> str:
    base = "|".join([agence, m.nature, normaliser_reference(m.reference_piece), m.ct_num,
                     str(m.montant), m.sens])
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def lire_feuille(path, feuille: str) -> list[list]:
    """Lit les valeurs d'une feuille (lecture seule, jamais d'ecriture)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if feuille not in wb.sheetnames:
            raise KeyError(f"Feuille '{feuille}' absente. Feuilles : {', '.join(wb.sheetnames)}")
        return [list(r) for r in wb[feuille].iter_rows(values_only=True)]
    finally:
        wb.close()
