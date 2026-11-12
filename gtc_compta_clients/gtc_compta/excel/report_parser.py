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
from collections import defaultdict
from datetime import date, datetime

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
    colonne: str = ""
    reference_liee: str = ""    # recu annule par un recu negatif

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
    colonnes: tuple = ()        # colonnes de montant bloquees (vide = toute la ligne)


@dataclass
class ResultatPreparation:
    feuille: str
    date_rapport: date | None
    agence: str
    factures: list[Mouvement] = field(default_factory=list)
    reglements: list[Mouvement] = field(default_factory=list)
    acomptes: list[Mouvement] = field(default_factory=list)
    anomalies: list[Anomalie] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    ligne_entete_recus: int | None = None
    date_feuille: date | None = None

    @property
    def mouvements(self) -> list[Mouvement]:
        return self.factures + self.acomptes + self.reglements

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
        st = {"lignes_lues": len(rows), "factures": 0, "avoirs": 0, "acomptes": 0, "reglements": 0, "annulations_recus": 0,
              "bc_seuls_ignores": 0, "annulees": 0, "factures_montant_nul": 0, "totaux_exclus": 0,
              "hors_perimetre_exclus": 0, "anomalies": 0,
              "montants_exclus": defaultdict(int)}

        # Date imprimee en tete de feuille (cellule A4 dans le rapport reel)
        res.date_feuille = next((v.date() if isinstance(v, datetime) else v
                                 for r in rows[:8] for v in r[:3] if isinstance(v, (date, datetime))), None)
        if res.date_rapport is None:
            res.date_rapport = res.date_feuille
        elif res.date_feuille and res.date_feuille != res.date_rapport:
            res.anomalies.append(Anomalie(feuille, 0, "PARAMETRES", "BLOQUANT",
                f"Date de la feuille collee ({res.date_feuille:%d/%m/%Y}) differente de la date du rapport "
                f"({res.date_rapport:%d/%m/%Y})", "", "Verifier que la bonne journee a ete collee"))

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
        st["controle_totaux"] = self._controle_totaux(rows, fin_docs, idx_recus, res, st)
        st["montants_exclus"] = dict(st["montants_exclus"])

        vus, par_ref = {}, {}
        for m in res.mouvements:
            ref = normaliser_reference(m.reference_piece)
            cle = (m.nature, ref, normaliser(m.client_libelle))
            if cle in vus:
                res.anomalies.append(Anomalie(feuille, m.ligne, m.nature, "BLOQUANT",
                    f"Piece {m.reference_piece} en double (deja ligne {vus[cle]})",
                    m.reference_piece, "Supprimer le doublon ou corriger la reference"))
            vus[cle] = m.ligne
            if m.nature != "ACOMPTE":
                par_ref.setdefault((m.nature, ref), []).append(m)
        for (_nat, _ref), ms in par_ref.items():
            if len({normaliser(m.client_libelle) for m in ms}) > 1:
                for m in ms:
                    res.anomalies.append(Anomalie(feuille, m.ligne, m.nature, "AVERTISSEMENT",
                        f"Numero {m.reference_piece} utilise pour plusieurs clients ("
                        + ", ".join(sorted({x.client_libelle for x in ms})) + ")",
                        m.reference_piece, "Erreur de saisie probable : le rapprochement Sage indiquera "
                                           "la bonne affectation"))

        self._lier_annulations(res)
        for m in res.mouvements:
            self._affecter_client(m, res)
        st["anomalies"] = len(res.anomalies)
        res.stats = st
        return res

    # -------------------------------------------------------------------------
    def _est_exclu(self, row) -> bool:
        txt = normaliser(" ".join(_texte(_cell(row, c)) for c in "BCDE"))
        return any(re.search(r"(^|\W)" + re.escape(m) + r"(\W|$)", txt) for m in self.exclusions)

    def _montants(self, row, cols, res, ligne, section):
        """Montants des colonnes demandees ; None si un montant est illisible (anomalie posee)."""
        out = {}
        for c in cols:
            try:
                out[c] = parse_montant(_cell(row, c)) or 0
            except MontantInvalide as exc:
                res.anomalies.append(Anomalie(res.feuille, ligne, section, "BLOQUANT", f"Colonne {c} : {exc}",
                                              _row_text(row), "Corriger le montant"))
                return None
        return out

    def _section_documents(self, rows, offset, res, st):
        feuille = res.feuille
        r = self.r
        cols_f = r["colonnes_facture"]
        acpt = r.get("acomptes", {})
        col_acpt = acpt.get("colonne") if acpt.get("integrer") else None
        bons = set(r.get("prefixes_bons", []))
        annules = {normaliser(v) for v in r.get("valeurs_annulee", ["ANNULEE"])}
        for i, row in enumerate(rows):
            ligne = offset + i + 1
            num = _texte(_cell(row, "C"))
            client = _texte(_cell(row, "D"))
            mode = _texte(_cell(row, "E"))
            a_montant = any(_est_montant(_cell(row, c)) for c in r["colonnes_bc"] + cols_f)
            if not num and not client:
                if a_montant:
                    st["totaux_exclus"] += 1
                continue
            if self._est_exclu(row):
                cle = "totaux_exclus" if "TOTAL" in normaliser(_row_text(row)) else "hors_perimetre_exclus"
                st[cle] += 1
                if cle == "hors_perimetre_exclus":
                    for c in set(cols_f + ([col_acpt] if col_acpt else [])):
                        try:
                            st["montants_exclus"][c] += parse_montant(_cell(row, c)) or 0
                        except MontantInvalide:
                            pass
                continue
            if not self.re_doc.match(normaliser_reference(num)):
                if a_montant:   # les en-tetes de colonnes sans montant sont ignores silencieusement
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "AVERTISSEMENT",
                        "Ligne avec montant mais numero de document non reconnu",
                        _row_text(row), "Verifier la colonne C"))
                continue
            vals = self._montants(row, sorted(set(cols_f + ([col_acpt] if col_acpt else []))), res, ligne,
                                  "DOCUMENTS")
            if vals is None:
                continue
            factures = {c: vals[c] for c in cols_f if vals[c]}
            acompte = vals.get(col_acpt, 0) if col_acpt else 0
            prefixe = prefixe_document(num)
            if normaliser(mode) in annules:
                if factures or acompte:
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                        "Ligne marquee ANNULEE mais portant un montant", _row_text(row),
                        "Verifier l'annulation avec le commercial"))
                else:
                    st["annulees"] += 1
                continue
            if not client:
                if factures or acompte:
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                        "Client absent (colonne D)", _row_text(row), "Renseigner le client"))
                continue
            base = dict(client_libelle=client, bc_origine=_texte(_cell(row, "B")), mode_reference=mode,
                        feuille=feuille, ligne=ligne, type_document=prefixe)
            if normaliser(client) in self.collectifs:
                base["acheteur_detail"] = mode
            if acompte:
                # Acompte encaisse a la commande (colonne ACOMPTE) : reglement du client.
                # Encaissement : toujours au CREDIT du compte client, signe conserve.
                note = "" if acpt.get("confirme") else "traitement des acomptes non confirme"
                if acompte < 0:
                    note = (note + " ; acompte negatif").strip(" ;")
                m = Mouvement(nature="ACOMPTE", reference_piece=num, montant=acompte,
                              sens="C", colonne=col_acpt, notes=note, **base)
                res.acomptes.append(m)
                st["acomptes"] += 1
            if not factures:
                if prefixe in bons:
                    st["bc_seuls_ignores"] += 1      # BC / BL seul : pas de creance facturee
                elif prefixe in r["types_documents"]:
                    st["factures_montant_nul"] += 1
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "INFO",
                        f"Facture {num} sans montant (reference : {mode or '-'})", _row_text(row),
                        "Aucun mouvement cree ; verifier s'il s'agit d'une gratuite / avarie / bonus"))
                else:
                    st["bc_seuls_ignores"] += 1
                continue
            if len(set(factures.values())) > 1:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    "Montants facture differents dans " + "/".join(cols_f),
                    _row_text(row), "Determiner la colonne de montant facture applicable"))
                continue
            col, montant = next(iter(factures.items()))
            if prefixe in bons:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    f"Numero de bon ({num}) avec un montant de facture en {col} : numero de facture absent",
                    _row_text(row), "Remplacer par le numero de la facture Sage", colonnes=(col,)))
                continue
            regle = r["types_documents"].get(prefixe)
            if regle is None:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    f"Type de document '{prefixe}' non parametre (nature/sens inconnus)",
                    _row_text(row), "Parametrer le type dans rapport.types_documents"))
                continue
            # Regle comptable GTC : toute facture (y compris facture retour / d'avoir) est passee au
            # DEBIT du compte client en CONSERVANT son signe. Aucune inversion de colonne.
            nature, sens = regle["nature"], "D"
            notes = "" if regle.get("confirme") else f"regle {prefixe} non confirmee"
            if nature == "AVOIR" and montant > 0:
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "INFO",
                    f"Avoir {num} de montant positif (habituellement negatif)", _row_text(row),
                    "Montant repris tel quel au debit"))
            elif nature != "AVOIR" and montant < 0:
                notes = (notes + " ; facture de montant negatif").strip(" ;")
            res.factures.append(Mouvement(nature=nature, reference_piece=num, montant=montant, sens=sens,
                                          colonne=col, notes=notes, **base))
            st["avoirs" if nature == "AVOIR" else "factures"] += 1

    def _controle_totaux(self, rows, fin_docs, idx_recus, res, st) -> dict:
        """Rapproche les montants extraits des lignes TOTAL du rapport lui-meme.

        rapport : montant de la ligne TOTAL du rapport (TOTAL VENTES / TOTAL DE VERSEMENTS) ;
        lignes  : somme brute des lignes de detail de la colonne (lignes contenant TOTAL ignorees) ;
        retenu  : somme signee des mouvements extraits ; exclus : lignes hors perimetre
        (liaisons, caisse...) ; bloques : lignes en anomalie bloquante (traitement manuel).
        Controles : rapport == lignes (coherence du rapport) et
        lignes == retenu + exclus + bloques (aucun montant oublie par l'extraction)."""
        bloquantes: dict[int, set] = {}
        for a in res.anomalies:
            if a.gravite == "BLOQUANT" and a.ligne > 0:
                bloquantes.setdefault(a.ligne, set()).update(a.colonnes or {"*"})

        def val(row, col):
            try:
                return parse_montant(_cell(row, col)) or 0
            except MontantInvalide:
                return 0

        def segment(seg, offset, col, libelle_total):
            lignes = exclus = bloques = 0
            rapport = None
            for k, row in enumerate(seg):
                txt = normaliser(_row_text(row))
                if "TOTAL" in txt:
                    if rapport is None and libelle_total in normaliser(" ".join(_texte(_cell(row, c)) for c in "BCDE")):
                        rapport = val(row, col)
                    continue
                v = val(row, col)
                if not v:
                    continue
                lignes += v
                bl = bloquantes.get(offset + k + 1, ())
                if "*" in bl or col in bl:
                    bloques += v
                elif self._est_exclu(row):
                    exclus += v
            return {"rapport": rapport, "lignes": lignes, "exclus": exclus, "bloques": bloques}

        out = {}
        acpt = self.r.get("acomptes", {})
        acpt_col = acpt.get("colonne") if acpt.get("integrer") else None
        tv = normaliser(self.r.get("libelle_total_ventes", "TOTAL VENTES"))
        for col in self.r["colonnes_facture"] + ([acpt_col] if acpt_col else []):
            d = segment(rows[:fin_docs], 0, col, tv)
            d["retenu"] = sum(m.montant for m in res.factures + res.acomptes if m.colonne == col)
            out[f"documents_{col}"] = d
        if idx_recus is not None:
            col = self.r["colonne_montant_recu"]
            fin = normaliser(self.r.get("libelle_total_recus", "TOTAL DE VERSEMENTS"))
            seg = []
            for row in rows[idx_recus + 1:]:
                seg.append(row)
                if fin in normaliser(_row_text(row)):
                    break
            d = segment(seg, idx_recus + 1, col, fin)
            d["retenu"] = sum(m.montant for m in res.reglements)
            out[f"recus_{col}"] = d
        libelles = {"H": "ventes comptant", "I": "ventes a terme", "F": "acomptes / recouvrements"}
        for k, v in out.items():
            nom = f"{k} ({libelles.get(k[-1], '')})"
            if v["rapport"] is not None and v["rapport"] != v["lignes"]:
                res.anomalies.append(Anomalie(res.feuille, 0, "CONTROLE", "AVERTISSEMENT",
                    f"{nom} : la ligne TOTAL du rapport ({v['rapport']}) differe de la somme des lignes "
                    f"({v['lignes']})", "", "Verifier le total saisi dans le rapport"))
            ecart = v["lignes"] - v["retenu"] - v["exclus"] - v["bloques"]
            v["ecart_non_explique"] = ecart
            if ecart:
                res.anomalies.append(Anomalie(res.feuille, 0, "CONTROLE", "BLOQUANT",
                    f"{nom} : {ecart} non explique entre les lignes du rapport et les mouvements extraits",
                    "", "Signaler a l'administrateur : une ligne n'a pas ete interpretee"))
        return out

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
            # Recu : toujours au CREDIT du compte client, signe conserve. Un recu negatif
            # contre-passe un recu fait sur un compte errone (lien recherche plus bas).
            m = Mouvement(nature=nature, reference_piece=num, client_libelle=client,
                          montant=montant, sens=sens, mode_reference=_texte(_cell(row, "E")),
                          feuille=feuille, ligne=ligne, type_document=prefixe_document(num), colonne=col_m)
            if normaliser(client) in self.collectifs:
                m.acheteur_detail = m.mode_reference
            res.reglements.append(m)
            st["annulations_recus" if montant < 0 else "reglements"] += 1

    def _lier_annulations(self, res: ResultatPreparation):
        """Rattache chaque recu negatif au recu positif qu'il annule (meme client, meme montant,
        dans la journee). A defaut, avertissement : le recu annule est peut-etre d'un jour
        precedent (le lien sera recherche a l'import) ; les recus de meme montant faits le meme
        jour sur d'autres comptes sont cites comme reaffectations possibles."""
        positifs = [m for m in res.reglements if m.montant > 0]
        deja = set()
        for a in [m for m in res.reglements if m.montant < 0]:
            orig = next((p for p in positifs if id(p) not in deja and p.montant == -a.montant
                         and normaliser(p.client_libelle) == normaliser(a.client_libelle)), None)
            autres = [p for p in positifs if p.montant == -a.montant and p is not orig
                      and normaliser(p.client_libelle) != normaliser(a.client_libelle)]
            reaff = (" ; reaffectation possible : " + ", ".join(f"{p.reference_piece} ({p.client_libelle})"
                                                                for p in autres)) if autres else ""
            if orig:
                deja.add(id(orig))
                a.reference_liee = orig.reference_piece
                a.notes = f"annule le recu {orig.reference_piece}" + reaff
            else:
                a.notes = "recu annule non trouve dans la journee" + reaff
                res.anomalies.append(Anomalie(res.feuille, a.ligne, "RECUS", "AVERTISSEMENT",
                    f"Recu negatif {a.reference_piece} ({a.client_libelle}, {a.montant}) : aucun recu positif "
                    f"de meme montant sur ce compte dans la journee" + reaff, a.reference_piece,
                    "Le recu annule sera recherche dans les jours deja importes ; verifier le compte"))

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
