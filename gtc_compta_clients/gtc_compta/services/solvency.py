"""Controle de solvabilite avant signature d'un BC.

La formule du risque est celle de Sage ("Informations client > Solvabilite") et
doit etre fournie par l'adaptateur (SolvencyComponents). Le BC examine n'est
ajoute au risque QUE si l'adaptateur indique qu'il n'y est pas deja inclus.
Avis : FAVORABLE / SOUS_CONDITION / DEFAVORABLE / DONNEES_INSUFFISANTES.
L'application emet un avis documente et ne signe rien dans Sage.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..db import now_iso
from ..sage.base import SageExtractionIncomplete, SageIndisponible
from .auth import Utilisateur, exiger


@dataclass
class AvisSolvabilite:
    avis: str
    bc: str
    ct_num: str | None = None
    montant_bc: int | None = None
    plafond: int | None = None
    risque_sage: int | None = None
    bc_deja_inclus: bool | None = None
    risque_projete: int | None = None
    depassement: int | None = None
    versement_necessaire: int = 0
    factures_echues: list = field(default_factory=list)
    motifs: list[str] = field(default_factory=list)
    check_id: int | None = None


def calculer_avis(bc_ref, bc, comp, politique: dict) -> AvisSolvabilite:
    a = AvisSolvabilite(avis="DONNEES_INSUFFISANTES", bc=bc_ref, ct_num=bc.ct_num, montant_bc=bc.montant_ttc,
                        plafond=comp.plafond, risque_sage=comp.risque_sage, bc_deja_inclus=comp.bc_deja_inclus,
                        factures_echues=list(comp.factures_echues))
    if comp.plafond is None or comp.risque_sage is None or comp.bc_deja_inclus is None:
        a.motifs.append(comp.details.get("motif") or "Composantes de solvabilite Sage incompletes")
        return a
    if comp.plafond == 0 and politique.get("plafond_zero", "donnees_insuffisantes") == "donnees_insuffisantes":
        a.motifs.append("Plafond (encours autorise) a 0 : signification Sage a confirmer")
        return a
    a.risque_projete = comp.risque_sage + (0 if comp.bc_deja_inclus else bc.montant_ttc)
    a.motifs.append("BC deja inclus dans le risque Sage : non rajoute" if comp.bc_deja_inclus
                    else "BC non inclus dans le risque Sage : ajoute au risque projete")
    a.depassement = max(0, a.risque_projete - comp.plafond)
    avis = "FAVORABLE"
    if a.depassement > 0:
        a.versement_necessaire = a.depassement
        maxi = politique.get("depassement_max_sous_condition")
        if maxi is not None and a.depassement > int(maxi):
            avis = "DEFAVORABLE"
            a.motifs.append(f"Depassement {a.depassement} superieur au maximum autorise {maxi}")
        else:
            avis = "SOUS_CONDITION"
            a.motifs.append(f"Versement prealable necessaire : {a.depassement}")
    if comp.factures_echues:
        tot = sum(int(f.get("montant", 0)) for f in comp.factures_echues)
        pol = politique.get("politique_factures_echues", "signaler")
        a.motifs.append(f"{len(comp.factures_echues)} facture(s) echue(s) pour {tot} (politique : {pol})")
        if pol == "bloquer":
            avis = "DEFAVORABLE"
        elif pol == "sous_condition" and avis == "FAVORABLE":
            avis = "SOUS_CONDITION"
    if not comp.source_verifiee:
        a.motifs.append("Formule non encore verifiee par concordance avec Sage")
    a.avis = avis
    return a


def controler_bc(db, user: Utilisateur, sage, reference: str, politique: dict) -> AvisSolvabilite:
    exiger(user, "solvabilite")
    reference = reference.strip()
    try:
        bcs = sage.chercher_bon_commande(reference)
        if len(bcs) == 1:
            comp = sage.composantes_solvabilite(bcs[0])
    except (SageIndisponible, SageExtractionIncomplete) as exc:
        a = AvisSolvabilite("DONNEES_INSUFFISANTES", reference, motifs=[f"Sage indisponible : {exc}"])
        return _enregistrer(db, user, a)
    if not bcs:
        return _enregistrer(db, user, AvisSolvabilite("DONNEES_INSUFFISANTES", reference,
                                                      motifs=["Bon de commande introuvable dans Sage"]))
    if len(bcs) > 1:
        return _enregistrer(db, user, AvisSolvabilite(
            "DONNEES_INSUFFISANTES", reference,
            motifs=["Reference ambigue : " + ", ".join(b.piece for b in bcs) + " - saisir le numero complet"]))
    return _enregistrer(db, user, calculer_avis(bcs[0].piece, bcs[0], comp, politique))


def _enregistrer(db, user, a: AvisSolvabilite) -> AvisSolvabilite:
    with db.transaction():
        cur = db.execute(
            "INSERT INTO purchase_order_credit_checks(bc_reference, ct_num, montant_bc, plafond, risque_sage, "
            "bc_deja_inclus, risque_projete, depassement, versement_necessaire, factures_echues_json, avis, motifs, "
            "controle_le, controle_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.bc, a.ct_num, a.montant_bc, a.plafond, a.risque_sage,
             None if a.bc_deja_inclus is None else int(a.bc_deja_inclus), a.risque_projete, a.depassement,
             a.versement_necessaire, json.dumps(a.factures_echues, default=str), a.avis, "\n".join(a.motifs),
             now_iso(), user.login))
        a.check_id = cur.lastrowid
        db.audit(user.login, "CONTROLE_SOLVABILITE", a.bc, {"avis": a.avis, "check": a.check_id})
    return a


def enregistrer_derogation(db, user: Utilisateur, check_id: int, motif: str) -> None:
    exiger(user, "derogation")
    if not motif.strip():
        raise ValueError("Motif obligatoire")
    db.audit(user.login, "DEROGATION_SOLVABILITE", str(check_id), {"motif": motif})


def historique(db, limite=200):
    return db.query("SELECT * FROM purchase_order_credit_checks ORDER BY id DESC LIMIT ?", (limite,))
