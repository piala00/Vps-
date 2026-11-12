"""Adaptateur Sage FICTIF pour tests et demonstration. Donnees inventees, signalees
comme telles dans l'interface ("MODE DEMONSTRATION")."""
from __future__ import annotations

import json
from datetime import date

from .base import (SageClient, SageEntry, SageIndisponible, SagePurchaseOrder,
                   SolvencyComponents)


class FakeSageAdapter:
    nom = "Sage FICTIF (demonstration)"
    est_demo = True

    def __init__(self):
        self.disponible = True
        self.clients: dict[str, SageClient] = {}
        self.ecritures: list[SageEntry] = []
        self.bons: list[SagePurchaseOrder] = []
        self.solvabilite: dict[str, SolvencyComponents] = {}
        self.pdfs: dict[str, str] = {}

    @classmethod
    def depuis_json(cls, path) -> "FakeSageAdapter":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        a = cls()
        for c in d.get("clients", []):
            a.ajouter_client(SageClient(**c))
        for e in d.get("ecritures", []):
            e = dict(e)
            e["date_ecriture"] = date.fromisoformat(e["date_ecriture"])
            if e.get("date_echeance"):
                e["date_echeance"] = date.fromisoformat(e["date_echeance"])
            a.ecritures.append(SageEntry(**e))
        for b in d.get("bons_commande", []):
            b = dict(b)
            b["date_doc"] = date.fromisoformat(b["date_doc"])
            a.bons.append(SagePurchaseOrder(**b))
        for piece, comp in d.get("solvabilite", {}).items():
            a.solvabilite[piece] = SolvencyComponents(**comp)
        return a

    def ajouter_client(self, c: SageClient):
        self.clients[c.ct_num] = c

    def ajouter_ecriture(self, e: SageEntry):
        self.ecritures.append(e)

    def _check(self):
        if not self.disponible:
            raise SageIndisponible("Sage (fictif) indisponible")

    def ping(self):
        self._check()

    def lister_clients(self):
        self._check()
        return list(self.clients.values())

    def ecritures_client(self, ct_num, date_debut, date_fin):
        self._check()
        return sorted((e for e in self.ecritures if e.ct_num == ct_num
                       and (date_debut is None or e.date_ecriture >= date_debut)
                       and e.date_ecriture <= date_fin),
                      key=lambda e: (e.date_ecriture, e.ec_no))

    def solde_client(self, ct_num, date_arrete):
        return sum(e.signe for e in self.ecritures_client(ct_num, None, date_arrete))

    def soldes_a_date(self, date_ref):
        self._check()
        return {ct: self.solde_client(ct, date_ref) for ct in self.clients}

    def chercher_bon_commande(self, reference):
        self._check()
        ref = reference.replace(" ", "").upper()
        return [b for b in self.bons if b.piece.upper() == ref or b.piece.upper().endswith(ref)]

    def composantes_solvabilite(self, bc):
        self._check()
        return self.solvabilite.get(bc.piece, SolvencyComponents(None, None, None))

    def chemin_pdf_facture(self, piece):
        return self.pdfs.get(piece)
