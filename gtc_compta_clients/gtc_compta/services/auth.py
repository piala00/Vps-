"""Roles et permissions. Toute action sensible appelle exiger()."""
from __future__ import annotations

from dataclasses import dataclass

PERMISSIONS = {
    "importer": {"operateur", "comptable_controleur", "responsable", "admin"},
    "valider_fiche": {"comptable_controleur", "responsable"},
    "reprise_sage": {"comptable_controleur", "responsable"},
    "corriger_mouvement": {"comptable_controleur", "responsable"},
    "derogation": {"responsable"},
    "correspondance_client": {"comptable_controleur", "responsable", "admin"},
    "soldes_ouverture": {"comptable_controleur", "responsable"},
    "synchro_sage": {"operateur", "comptable_controleur", "responsable", "admin"},
    "pointage": {"comptable_controleur", "responsable"},
    "solvabilite": {"operateur", "comptable_controleur", "responsable"},
    "impression": {"operateur", "comptable_controleur", "responsable"},
    "champs_manuels": {"operateur", "comptable_controleur", "responsable"},
    "parametres": {"admin"},
    "sauvegarde": {"admin", "responsable"},
}

LIBELLES_ROLES = {"operateur": "Operateur", "comptable_controleur": "Comptable controleur",
                  "responsable": "Responsable", "admin": "Administrateur technique"}


class AccesRefuse(PermissionError):
    pass


@dataclass(frozen=True)
class Utilisateur:
    login: str
    nom: str
    role: str

    def peut(self, action: str) -> bool:
        return self.role in PERMISSIONS.get(action, set())


def exiger(user: Utilisateur, action: str) -> None:
    if not user.peut(action):
        raise AccesRefuse(f"Action '{action}' non autorisee pour le role "
                          f"{LIBELLES_ROLES.get(user.role, user.role)}")


def assurer_utilisateur(db, user: Utilisateur) -> None:
    db.execute("INSERT INTO users(login, nom, role) VALUES (?,?,?) "
               "ON CONFLICT(login) DO UPDATE SET nom=excluded.nom, role=excluded.role",
               (user.login, user.nom, user.role))
