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


# Catalogue des erreurs de CR : (motif reconnu, code, impact sur le solde client, libelle)
CATALOGUE_ERREURS = [
    (r"^Numero de bon .* avec un montant de facture", "BC_AVEC_FACTURE", True,
     "N° de bon de commande / livraison (BCCB, BLCB) saisi a la place du n° de facture"),
    (r"^Montant de facture sans numero de facture", "FACTURE_SANS_NUMERO", True,
     "Montant de facture sans n° de facture en colonne C"),
    (r"^Type de document", "TYPE_INCONNU", True, "Type de piece inconnu en colonne C"),
    (r"^Montants facture differents", "MONTANTS_H_I_DIFFERENTS", True,
     "Montants differents en COMPTANT (H) et VAT (I) sur la meme ligne"),
    (r"^Ligne marquee ANNULEE mais portant", "ANNULEE_AVEC_MONTANT", True, "Ligne ANNULEE portant un montant"),
    (r"^Client absent", "CLIENT_ABSENT", True, "Nom du client absent (colonne D)"),
    (r"^Colonne [A-Z] :|montant illisible|centimes", "MONTANT_ILLISIBLE", True, "Montant illisible ou avec centimes"),
    (r"^Piece .* en double", "DOUBLON_JOUR", True, "Meme piece saisie deux fois dans la journee"),
    (r"utilise pour plusieurs clients", "NUMERO_PLUSIEURS_CLIENTS", True,
     "Meme n° de piece (facture ou recu) utilise pour plusieurs clients"),
    (r"^Recu sans montant", "RECU_SANS_MONTANT", True, "Recu sans montant"),
    (r"^Recu negatif", "RECU_NEGATIF_SANS_ORIGINE", True,
     "Recu negatif (contre-passation) dont le recu annule n'est pas retrouve"),
    (r"sans correspondance verifiee", "CLIENT_SANS_CORRESPONDANCE", True,
     "Client du rapport non rattache a un code tiers Sage"),
    (r"non explique entre les lignes", "MONTANT_NON_EXPLIQUE", True,
     "Montant du rapport non interprete par l'extraction"),
    (r"^Date de la feuille", "DATE_FEUILLE", True, "Feuille collee d'une autre journee"),
    (r"^Entete .* introuvable", "ENTETE_RECUS_ABSENTE", True, "Section des recus introuvable"),
    (r"^Date du rapport non renseignee", "DATE_ABSENTE", True, "Date du rapport absente"),
    (r"la ligne TOTAL du rapport", "TOTAL_RAPPORT_FAUX", False, "Ligne TOTAL du rapport fausse"),
    (r"^Avoir .* de montant positif", "AVOIR_POSITIF", True, "Avoir de montant positif"),
    (r"saisie dans les deux colonnes", "MONTANT_H_ET_I", True,
     "Meme facture saisie en COMPTANT et en VAT (comptee deux fois dans le TOTAL du rapport)"),
    (r"mal saisi : prefixe", "NUMERO_MAL_SAISI", False, "N° de piece tronque (FRC, 7RC...) : montant repris"),
    (r"ANNULEE compensee par", "FACTURE_ANNULEE_PAR_AVOIR", False,
     "Facture ANNULEE compensee par une facture retour ANNULEE (les deux reprises)"),
    (r"^Nom du client remplace par un commentaire", "CLIENT_LIBELLE_COMMENTAIRE", True,
     "Commentaire ecrit a la place du nom du client"),
    (r"sans aucun numero \(ni BC", "BC_SANS_NUMERO", False, "Ligne de bon de commande sans aucun numero"),
    (r"^Facture .* sans montant", "FACTURE_MONTANT_NUL", False, "Facture sans montant (gratuite, avarie, bonus)"),
    (r"ligne\(s\) de bon de commande sans numero en colonne C", "BC_SANS_NUMERO_C", False,
     "Ligne de bon de commande sans n° BCCB en colonne C"),
    (r"numero de document non reconnu|sans reference de recu", "LIGNE_NON_RECONNUE", False,
     "Ligne avec montant non reconnue"),
]


def classer_anomalie(motif: str) -> tuple[str, bool]:
    for motif_re, code, impact, _lib in CATALOGUE_ERREURS:
        if re.search(motif_re, motif):
            return code, impact
    return "AUTRE", True


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
    code: str = ""              # code stable du type d'erreur (catalogue des erreurs CR)
    impact_solde: bool = False  # True : le solde d'un client peut etre faux tant que non resolue
    client: str = ""
    reference: str = ""
    montant: int | None = None
    colonne: str = ""


@dataclass
class ResultatPreparation:
    feuille: str
    date_rapport: date | None
    agence: str
    factures: list[Mouvement] = field(default_factory=list)
    reglements: list[Mouvement] = field(default_factory=list)
    acomptes: list[Mouvement] = field(default_factory=list)
    bons: list[dict] = field(default_factory=list)      # registre BC (information, jamais comptabilise)
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
              "bc_seuls_ignores": 0, "bc_sans_numero_c": 0, "bc_sans_aucun_numero": 0, "annulees": 0, "factures_montant_nul": 0, "totaux_exclus": 0,
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
        st["total_acompte_cr"], st["total_ventes_cellule_cr"] = self._cellules_total(rows[:fin_docs])
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

        if st["bc_sans_aucun_numero"]:
            res.anomalies.append(Anomalie(feuille, 0, "DOCUMENTS", "INFO",
                f"{st['bc_sans_aucun_numero']} ligne(s) de bon de commande sans aucun numero (ni BC en B, ni piece en C)",
                "", "Aucune incidence comptable (montants en BC uniquement) ; a signaler aux commerciaux"))
        if st["bc_sans_numero_c"]:
            res.anomalies.append(Anomalie(feuille, 0, "DOCUMENTS", "INFO",
                f"{st['bc_sans_numero_c']} ligne(s) de bon de commande sans numero en colonne C (BC lu en colonne B)",
                "", "Aucune incidence comptable ; a signaler aux commerciaux"))
        self._lier_annulations(res)
        for m in res.mouvements:
            self._affecter_client(m, res)
        self._completer_anomalies(rows, res, idx_recus)
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
        # Les colonnes BON DE COMMANDE (F acompte, G BP) ne sont jamais transformees en mouvements :
        # rien n'est comptabilise dans Sage au stade du BC. Seules les colonnes FACTURE (H, I) et les
        # recus le sont, lors de la mise a jour comptable.
        fc = r.get("factures_comptant", {})
        cols_comptant = set(fc.get("colonnes", [])) if fc.get("mode") == "solder_par_acompte" else set()
        annulees_montant = []
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
                    for c in cols_f:
                        try:
                            st["montants_exclus"][c] += parse_montant(_cell(row, c)) or 0
                        except MontantInvalide:
                            pass
                continue
            if not self.re_doc.match(normaliser_reference(num)):
                if not a_montant:   # en-tetes de colonnes sans montant : ignores silencieusement
                    continue
                if any(_est_montant(_cell(row, c)) for c in cols_f):
                    # Montant de FACTURE sans numero de facture : impossible a comptabiliser / rapprocher.
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                        f"Montant de facture sans numero de facture valide en colonne C ('{num}')",
                        _row_text(row), "Renseigner le numero de la facture Sage"))
                    continue
                bc_b = _texte(_cell(row, "B"))
                if not num and re.match(self.r.get("motif_bc", r"^BC\d+$"), normaliser_reference(bc_b)):
                    # Ligne de BON DE COMMANDE dont le n° BCCB n'a pas ete recopie en C : rien n'est
                    # comptabilise ; l'acompte / BP est seulement enregistre dans le registre des BC.
                    st["bc_seuls_ignores"] += 1
                    st["bc_sans_numero_c"] += 1
                    try:
                        acpt_bc = parse_montant(_cell(row, "F")) or 0
                        bp_bc = parse_montant(_cell(row, "G")) or 0
                    except MontantInvalide:
                        acpt_bc = bp_bc = 0
                    if normaliser(mode) not in annules:
                        res.bons.append({"bc": normaliser_reference(bc_b), "piece": bc_b, "client": client,
                                         "acompte": acpt_bc, "bp": bp_bc, "ligne": ligne})
                    continue
                if not num:
                    # Ligne de bon de commande sans aucun numero (ni BC en B, ni piece en C) : montants
                    # uniquement en F/G, rien n'est comptabilise ; simple information.
                    st["bc_seuls_ignores"] += 1
                    st["bc_sans_aucun_numero"] += 1
                    continue
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "AVERTISSEMENT",
                    "Ligne avec montant de bon de commande mais numero de document non reconnu",
                    _row_text(row), "Verifier les colonnes B et C"))
                continue
            vals = self._montants(row, cols_f, res, ligne, "DOCUMENTS")
            if vals is None:
                continue
            factures = {c: vals[c] for c in cols_f if vals[c]}
            prefixe = prefixe_document(num)
            bc = _texte(_cell(row, "B"))
            try:
                acpt_bc = parse_montant(_cell(row, "F")) or 0
                bp_bc = parse_montant(_cell(row, "G")) or 0
            except MontantInvalide:
                acpt_bc = bp_bc = 0
            if (acpt_bc or bp_bc) and normaliser(mode) not in annules:
                # Registre des bons de commande : sert uniquement a controler les factures comptant.
                # Colonne B sans n° de BC valide (vide, "OLA"...) : l'acompte est rattache a la piece.
                res.bons.append({"bc": cle_bc(bc, num, self.r), "piece": num, "client": client,
                                 "acompte": acpt_bc, "bp": bp_bc, "ligne": ligne})
            if normaliser(mode) in annules:
                if factures:
                    # Facture annulee : peut etre compensee par une facture retour / d'avoir ANNULEE de
                    # montant oppose (meme client, meme jour) ; appariement en fin de section.
                    annulees_montant.append((row, ligne, num, client, mode, prefixe, factures))
                else:
                    st["annulees"] += 1
                continue
            if not client:
                if factures:
                    res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                        "Client absent (colonne D)", _row_text(row), "Renseigner le client"))
                continue
            if not factures:
                if prefixe in bons:
                    st["bc_seuls_ignores"] += 1      # BC / BL seul : pas de creance facturee
                elif self._regle(prefixe)[0] is not None:
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
            if len(factures) > 1:
                # Meme montant saisi en COMPTANT et en VAT : une seule facture. Colonne retenue selon la
                # reference (COMPTANT / acompte -> comptant ; EN COMPTE / BP -> a terme).
                col = self._colonne_probable(mode, acpt_bc, cols_comptant, cols_f)
                autres = tuple(c for c in factures if c != col)
                res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "AVERTISSEMENT",
                    f"Facture {num} saisie dans les deux colonnes {'/'.join(cols_f)} (meme montant) : une seule "
                    f"facture retenue en {col}", _row_text(row),
                    "Le TOTAL VENTES du rapport compte cette facture deux fois ; verifier la colonne", colonnes=autres))
                factures = {col: factures[col]}
            col, montant = next(iter(factures.items()))
            self._creer_facture(row, ligne, num, client, mode, prefixe, col, montant, res, st, cols_comptant, fc)
        self._apparier_annulees(annulees_montant, res, st, cols_comptant, fc)

    def _regle(self, prefixe):
        """(regle, prefixe reel) ; tolere un prefixe tronque (FRC -> FRCB, 7RC -> 7RCB...)."""
        regle = self.r["types_documents"].get(prefixe)
        if regle is not None:
            return regle, prefixe
        reel = self.r.get("prefixes_tronques", {}).get(prefixe)
        return (self.r["types_documents"].get(reel), reel) if reel else (None, None)

    @staticmethod
    def _colonne_probable(mode, acompte, cols_comptant, cols_f):
        m = normaliser(mode)
        if cols_comptant and (acompte or m.startswith(("COMPTANT", "CASH"))):
            return next(iter(cols_comptant))
        autres = [c for c in cols_f if c not in cols_comptant]
        return autres[0] if autres else cols_f[0]

    def _creer_facture(self, row, ligne, num, client, mode, prefixe, col, montant, res, st, cols_comptant, fc,
                       note_supp=""):
        feuille = res.feuille
        if prefixe in set(self.r.get("prefixes_bons", [])):
            res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                f"Numero de bon ({num}) avec un montant de facture en {col} : numero de facture absent",
                _row_text(row), "Remplacer par le numero de la facture Sage", colonnes=(col,)))
            return
        regle, reel = self._regle(prefixe)
        if regle is None:
            res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "BLOQUANT",
                f"Type de document '{prefixe}' non parametre (nature/sens inconnus)",
                _row_text(row), "Parametrer le type dans rapport.types_documents"))
            return
        if reel != prefixe:
            res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "AVERTISSEMENT",
                f"Numero {num} mal saisi : prefixe '{prefixe}' au lieu de '{reel}' (montant repris)",
                _row_text(row), f"Numero Sage probable : {num.replace(prefixe, reel, 1)}"))
        base = dict(client_libelle=client, bc_origine=_texte(_cell(row, "B")), mode_reference=mode,
                    feuille=feuille, ligne=ligne, type_document=reel)
        if normaliser(client) in self.collectifs:
            base["acheteur_detail"] = mode
        # Regle comptable GTC : toute facture (y compris facture retour / d'avoir) est passee au
        # DEBIT du compte client en CONSERVANT son signe. Aucune inversion de colonne.
        nature, sens = regle["nature"], "D"
        notes = "" if regle.get("confirme") else f"regle {reel} non confirmee"
        if note_supp:
            notes = (notes + " ; " + note_supp).strip(" ;")
        if nature == "AVOIR" and montant > 0:
            res.anomalies.append(Anomalie(feuille, ligne, "DOCUMENTS", "INFO",
                f"Avoir {num} de montant positif (habituellement negatif)", _row_text(row),
                "Montant repris tel quel au debit"))
        elif nature != "AVOIR" and montant < 0:
            notes = (notes + " ; facture de montant negatif").strip(" ;")
        res.factures.append(Mouvement(nature=nature, reference_piece=num, montant=montant, sens=sens,
                                      colonne=col, notes=notes, **base))
        st["avoirs" if nature == "AVOIR" else "factures"] += 1
        if col in cols_comptant:
            # Facture COMPTANT : l'acompte encaisse sur le BC est impute sur la facture lors de la
            # mise a jour comptable Sage ; facture et acompte s'annulent sur le compte client.
            res.acomptes.append(Mouvement(
                nature="ACOMPTE", reference_piece=num, montant=montant, sens="C", colonne=col,
                notes="acompte impute sur facture comptant"
                      + ("" if fc.get("confirme") else " (regle a verifier au rapprochement Sage)"),
                **base))
            st["acomptes"] += 1

    def _apparier_annulees(self, lignes, res, st, cols_comptant, fc):
        """Facture ANNULEE + facture retour / d'avoir ANNULEE de montant oppose, meme client : les deux
        pieces existent dans Sage et s'annulent -> reprises toutes les deux. Sinon : bloquant."""
        pris = set()
        for i, (row, ligne, num, client, mode, prefixe, factures) in enumerate(lignes):
            if i in pris:
                continue
            col, mt = next(iter(factures.items()))
            j = next((k for k, x in enumerate(lignes) if k != i and k not in pris
                      and normaliser(x[3]) == normaliser(client) and sum(x[6].values()) == -mt), None)
            if j is None or len(factures) > 1 or len(lignes[j][6]) > 1:
                res.anomalies.append(Anomalie(res.feuille, ligne, "DOCUMENTS", "BLOQUANT",
                    "Ligne marquee ANNULEE mais portant un montant de facture", _row_text(row),
                    "Verifier l'annulation avec le commercial"))
                pris.add(i)
                continue
            pris.update({i, j})
            autre = lignes[j]
            for (r_, l_, n_, c_, m_, p_, f_), contre in (((row, ligne, num, client, mode, prefixe, factures), autre[2]),
                                                         (autre, num)):
                c2, mt2 = next(iter(f_.items()))
                self._creer_facture(r_, l_, n_, c_, m_, p_, c2, mt2, res, st, cols_comptant, fc,
                                    note_supp=f"ANNULEE, compensee par {contre}")
            res.anomalies.append(Anomalie(res.feuille, ligne, "DOCUMENTS", "INFO",
                f"Facture {num} ANNULEE compensee par {autre[2]} ANNULEE ({mt} / {-mt}) : les deux pieces sont "
                "reprises (elles existent dans Sage et s'annulent)", _row_text(row), ""))

    def _cellules_total(self, docs):
        """(ACOMPTE de la ligne TOTAL VENTES, cellule du CR qui calcule la vente totale = 2e ligne TOTAL VENTES)."""
        lib = normaliser(self.r.get("libelle_total_ventes", "TOTAL VENTES"))
        acompte, cellule = None, None
        cols_f = self.r["colonnes_facture"]
        for row in docs:
            txt_bce = normaliser(" ".join(_texte(_cell(row, c)) for c in "BCDE"))
            if acompte is None and lib in txt_bce:
                try:
                    acompte = parse_montant(_cell(row, "F")) or 0
                except MontantInvalide:
                    acompte = None
                continue
            if lib in normaliser(_texte(_cell(row, "G"))):
                try:
                    cellule = parse_montant(_cell(row, cols_f[-1]))
                except MontantInvalide:
                    cellule = None
        return acompte, cellule

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
            if a.ligne > 0 and (a.gravite == "BLOQUANT" or a.colonnes):
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
        tv = normaliser(self.r.get("libelle_total_ventes", "TOTAL VENTES"))
        for col in self.r["colonnes_facture"]:
            d = segment(rows[:fin_docs], 0, col, tv)
            d["retenu"] = sum(m.montant for m in res.factures if m.colonne == col)
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
        libelles = {"H": "ventes comptant", "I": "ventes a terme", "F": "recouvrements"}
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
            tronque = (not self.re_recu.match(numn)
                       and re.match(self.r.get("motif_recu_tronque", r"^\d*RC\d"), numn) is not None)
            if not self.re_recu.match(numn) and not tronque:
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
            if tronque:
                res.anomalies.append(Anomalie(feuille, ligne, "RECUS", "AVERTISSEMENT",
                    f"Numero {num} mal saisi : prefixe recu incomplet (montant repris)", txt,
                    "Numero Sage probable : " + re.sub(r"RC(?=\d)", "RCB", numn, count=1)))
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

    def _completer_anomalies(self, rows, res, idx_recus):
        """Code, impact sur le solde, client, piece et montant de chaque anomalie (depuis la ligne source)."""
        for a in res.anomalies:
            a.code, a.impact_solde = classer_anomalie(a.motif)
            if a.ligne <= 0 or a.ligne > len(rows):
                continue
            row = rows[a.ligne - 1]
            a.client = a.client or _texte(_cell(row, "D"))
            a.reference = a.reference or _texte(_cell(row, "C"))
            recu = idx_recus is not None and a.ligne > idx_recus
            cols = [self.r["colonne_montant_recu"]] if recu else (self.r["colonnes_facture"] + self.r["colonnes_bc"])
            if a.montant is None:
                for c in cols:
                    try:
                        v = parse_montant(_cell(row, c))
                    except MontantInvalide:
                        v = None
                    if v:
                        a.montant, a.colonne = v, c
                        break

    def _affecter_client(self, m: Mouvement, res: ResultatPreparation):
        if re.match(r"^(ANNULATION|ANNULE|ERREUR|CORRECTION|VERS |REGUL)", normaliser(m.client_libelle)):
            res.anomalies.append(Anomalie(res.feuille, m.ligne, m.nature, "BLOQUANT",
                f"Nom du client remplace par un commentaire : '{m.client_libelle}'", m.reference_piece,
                "Indiquer le vrai client (le commentaire ne correspond a aucun compte)"))
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


def cle_bc(colonne_b: str, piece: str, regles: dict) -> str:
    """Cle du registre des BC : le n° de BC s'il est valide, sinon la piece elle-meme."""
    b = normaliser_reference(colonne_b)
    if b and re.match(regles.get("motif_bc", r"^BC\d+$"), b):
        return b
    return "PIECE:" + normaliser_reference(piece)


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
