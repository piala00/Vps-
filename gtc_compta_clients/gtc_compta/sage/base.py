"""Interface d'acces a Sage (lecture seule). Aucune ecriture n'est jamais faite dans Sage."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


class SageIndisponible(RuntimeError):
    """Sage injoignable : aucun rapprochement ne doit etre declare."""


class SageExtractionIncomplete(RuntimeError):
    """Extraction partielle ou incoherente : aucun rapprochement ne doit etre declare."""


@dataclass(frozen=True)
class SageClient:
    ct_num: str
    intitule: str
    telephone: str = ""
    ville: str = ""
    encours_autorise: int | None = None


@dataclass(frozen=True)
class SageEntry:
    ec_no: int
    ct_num: str
    journal: str
    date_ecriture: date
    numero_piece: str
    reference_piece: str
    libelle: str
    sens: str                 # 'D' / 'C'
    montant: int
    date_echeance: date | None = None
    lettre: bool = False

    @property
    def signe(self) -> int:
        return self.montant if self.sens == "D" else -self.montant


@dataclass(frozen=True)
class SagePurchaseOrder:
    piece: str
    ct_num: str
    date_doc: date
    montant_ttc: int
    statut: str = ""


@dataclass
class SolvencyComponents:
    """Composantes reproduisant la fenetre Sage 'Informations client > Solvabilite'.

    risque_sage : risque tel que calcule par Sage (None si formule non etablie).
    bc_deja_inclus : True si le BC examine est deja compte dans risque_sage
    (None si inconnu -> aucun avis favorable possible).
    """
    plafond: int | None
    risque_sage: int | None
    bc_deja_inclus: bool | None
    factures_echues: list[dict] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    source_verifiee: bool = False


class SageAdapter(Protocol):
    nom: str
    est_demo: bool

    def ping(self) -> None: ...
    def lister_clients(self) -> list[SageClient]: ...
    def ecritures_client(self, ct_num: str, date_debut: date | None, date_fin: date) -> list[SageEntry]: ...
    def solde_client(self, ct_num: str, date_arrete: date) -> int: ...
    def soldes_a_date(self, date_ref: date) -> dict[str, int]: ...
    def chercher_bon_commande(self, reference: str) -> list[SagePurchaseOrder]: ...
    def composantes_solvabilite(self, bc: SagePurchaseOrder) -> SolvencyComponents: ...
    def chemin_pdf_facture(self, piece: str) -> str | None: ...
