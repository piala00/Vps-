#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/nexora_licence.py
NEXORA v2.0 — Moteur de Licences
=================================
Systeme de licences par numero de serie (comme Sage).
Le numero de serie est autonome : contient toutes les infos + signature.
Aucune connexion internet requise.

Architecture :
  - CLE SECRETE : uniquement dans NEXORA License Manager (jamais livree au client)
  - NEXORA (livre) : peut VERIFIER une licence, jamais en CREER
  - Numero de serie : NXR1- + Base32(JSON + signature HMAC-SHA256)
"""

import hmac
import hashlib
import base64
import json
import logging
from datetime import datetime, date
from typing import Optional, Dict

log = logging.getLogger("NEXORA.Licence")

# ─────────────────────────────────────────────────────────────────
# CLE DE VERIFICATION (publique cote application — ne permet pas de generer)
# ─────────────────────────────────────────────────────────────────
_VERIFY_KEY = "NEXORA_LIC_V1_SECRET_2026_YOUSSOUF_HAMADOU_GTC"

SERIAL_PREFIX = "NXR"
SERIAL_VERSION = "1"

MODULES_DISPONIBLES = {
    "STK": "Stock & Inventaire",
    "LOG": "Logistique (Flotte)",
    "COM": "Commercial (Ventes)",
    "CAI": "Caisse (Tresorerie)",
    "CPT": "Comptabilite",
    "RH":  "Ressources Humaines",
    "RAP": "Rapports",
    "CON": "Consolidation Multi-sites",
    "MST": "Multi-Sites (DT/DA)",
    "PAR": "Parametres",
}

MODULE_MAP = {
    "STK": "stock",
    "LOG": "logistique",
    "COM": "commercial",
    "CAI": "caisse",
    "CPT": "comptabilite",
    "RH":  "rh",
    "RAP": "rapports",
    "CON": "consolidation",
    "MST": "multisite",
    "PAR": "parametres",
}


class LicenceInfo:
    def __init__(self):
        self.valide = False
        self.erreur = ""
        self.nom_societe = ""
        self.pays = ""
        self.modules = []
        self.modules_noms = []
        self.nb_postes = 1
        self.date_expiration: Optional[date] = None
        self.perpetuelle = False
        self.version_nexora = "2.0"
        self.reference = ""
        self.jours_restants = 0
        self.expire_bientot = False

    def to_dict(self) -> Dict:
        return {
            "valide": self.valide,
            "erreur": self.erreur,
            "nom_societe": self.nom_societe,
            "pays": self.pays,
            "modules": self.modules,
            "modules_noms": self.modules_noms,
            "nb_postes": self.nb_postes,
            "date_expiration": str(self.date_expiration) if self.date_expiration else None,
            "perpetuelle": self.perpetuelle,
            "version_nexora": self.version_nexora,
            "reference": self.reference,
            "jours_restants": self.jours_restants,
            "expire_bientot": self.expire_bientot,
        }


class NexoraLicenceVerifier:
    """Verifie un numero de serie NEXORA. Ne peut pas en generer."""

    def __init__(self, verify_key: str = _VERIFY_KEY):
        self._key = verify_key.encode()

    def verifier(self, numero_serie: str) -> LicenceInfo:
        info = LicenceInfo()
        try:
            serial = numero_serie.strip().upper().replace(" ", "").replace("-", "")

            if not serial.startswith(SERIAL_PREFIX + SERIAL_VERSION):
                info.erreur = "Format de numero de serie invalide"
                return info

            payload_b64 = serial[len(SERIAL_PREFIX) + len(SERIAL_VERSION):]
            pad = 4 - len(payload_b64) % 4
            if pad != 4:
                payload_b64 += "=" * pad

            try:
                payload_bytes = base64.b32decode(payload_b64)
            except Exception:
                info.erreur = "Numero de serie corrompu"
                return info

            if len(payload_bytes) < 36:
                info.erreur = "Numero de serie trop court"
                return info

            data_bytes = payload_bytes[:-32]
            sig_bytes = payload_bytes[-32:]

            expected_sig = hmac.new(self._key, data_bytes, hashlib.sha256).digest()
            if not hmac.compare_digest(sig_bytes, expected_sig):
                info.erreur = "Numero de serie invalide — signature incorrecte"
                return info

            data = json.loads(data_bytes.decode("utf-8"))

            info.nom_societe = data.get("soc", "")
            info.pays = data.get("pay", "")
            info.nb_postes = int(data.get("pos", 1))
            info.version_nexora = data.get("ver", "2.0")
            info.reference = data.get("ref", "")
            module_codes = data.get("mod", [])
            info.modules = [MODULE_MAP.get(m, m.lower()) for m in module_codes]
            info.modules_noms = [MODULES_DISPONIBLES.get(m, m) for m in module_codes]

            exp_str = data.get("exp", "")
            if exp_str == "PERP":
                info.perpetuelle = True
                info.jours_restants = 99999
            else:
                try:
                    exp_date = datetime.strptime(exp_str, "%Y%m%d").date()
                    info.date_expiration = exp_date
                    today = date.today()
                    delta = (exp_date - today).days
                    info.jours_restants = max(0, delta)
                    if delta < 0:
                        info.erreur = "Licence expiree depuis le " + exp_date.strftime("%d/%m/%Y")
                        return info
                    info.expire_bientot = delta < 30
                except ValueError:
                    info.erreur = "Date d'expiration invalide"
                    return info

            info.valide = True
            log.info("[LICENCE] Valide - %s | expire: %s | postes: %s" %
                     (info.nom_societe, exp_str, info.nb_postes))
            return info

        except Exception as e:
            info.erreur = "Erreur de verification: " + str(e)
            log.error("[LICENCE] Erreur: %s" % e)
            return info

    def formater_numero(self, serial_brut: str) -> str:
        clean = serial_brut.strip().upper().replace(" ", "").replace("-", "")
        prefix = clean[:4]
        rest = clean[4:]
        groups = [rest[i:i + 4] for i in range(0, len(rest), 4)]
        return prefix + "-" + "-".join(groups)


class NexoraLicenceManager:
    """Gere l'etat de la licence cote application (config SQLite)."""

    def __init__(self, db_get_config, db_set_config):
        self._get = db_get_config
        self._set = db_set_config
        self._verifier = NexoraLicenceVerifier()
        self._cache: Optional[LicenceInfo] = None

    def get_licence(self, force_reload: bool = False) -> LicenceInfo:
        if self._cache and not force_reload:
            return self._cache

        serial = self._get("licence_serial", "")
        if not serial:
            info = LicenceInfo()
            info.erreur = "Aucune licence activee"
            self._cache = info
            return info

        info = self._verifier.verifier(serial)
        self._cache = info
        return info

    def activer(self, numero_serie: str) -> LicenceInfo:
        info = self._verifier.verifier(numero_serie)
        if info.valide:
            clean = numero_serie.strip().upper().replace(" ", "").replace("-", "")
            self._set("licence_serial", clean)
            self._set("licence_societe", info.nom_societe)
            self._set("licence_modules", ",".join(info.modules))
            self._set("licence_postes", str(info.nb_postes))
            self._set("licence_exp", str(info.date_expiration) if info.date_expiration else "PERP")
            self._set("licence_activee_le", str(date.today()))
            self._cache = info
            log.info("[LICENCE] Activee - %s" % info.nom_societe)
        return info

    def desactiver(self):
        self._set("licence_serial", "")
        self._cache = None

    def is_module_autorise(self, module: str) -> bool:
        if self.mode_demonstration():
            return True
        info = self.get_licence()
        if not info.valide:
            return False
        if info.perpetuelle or not info.modules:
            return True
        return module in info.modules

    def mode_demonstration(self) -> bool:
        serial = self._get("licence_serial", "")
        installed_date_str = self._get("installed_date", "")
        if serial:
            return False
        if not installed_date_str:
            self._set("installed_date", str(date.today()))
            return True
        try:
            installed = datetime.strptime(installed_date_str, "%Y-%m-%d").date()
            delta = (date.today() - installed).days
            return delta <= 30
        except Exception:
            return False

    def jours_demo_restants(self) -> int:
        installed_date_str = self._get("installed_date", "")
        if not installed_date_str:
            return 30
        try:
            installed = datetime.strptime(installed_date_str, "%Y-%m-%d").date()
            delta = (date.today() - installed).days
            return max(0, 30 - delta)
        except Exception:
            return 0


_licence_manager: Optional[NexoraLicenceManager] = None


def init_licence(db_get_config, db_set_config):
    global _licence_manager
    _licence_manager = NexoraLicenceManager(db_get_config, db_set_config)


def get_licence_manager() -> Optional[NexoraLicenceManager]:
    return _licence_manager
