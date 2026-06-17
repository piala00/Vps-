"""NEXORA v2.0 — Systeme de licences par numero de serie"""
import hmac, hashlib, base64, json, logging
from datetime import datetime, date, timedelta
from typing import Optional

log = logging.getLogger('NEXORA.Licence')

_VERIFY_KEY    = 'NEXORA_LIC_V1_SECRET_2026_YOUSSOUF_HAMADOU_GTC'
SERIAL_PREFIX  = 'NXR'
SERIAL_VERSION = '1'

MODULE_MAP = {
    'STK':'stock','LOG':'logistique','COM':'commercial',
    'CAI':'caisse','CPT':'comptabilite','RH':'rh',
    'RAP':'rapports','CON':'consolidation','MST':'multisite','PAR':'parametres',
}
MODULES_NOMS = {
    'STK':'Stock & Inventaire','LOG':'Logistique (Flotte)',
    'COM':'Commercial (Ventes)','CAI':'Caisse (Tresorerie)',
    'CPT':'Comptabilite','RH':'Ressources Humaines',
    'RAP':'Rapports','CON':'Consolidation Multi-sites',
    'MST':'Multi-Sites (DT/DA)','PAR':'Parametres',
}

class LicenceInfo:
    def __init__(self):
        self.valide = False
        self.erreur = ''
        self.nom_societe = ''
        self.pays = ''
        self.modules = []
        self.modules_noms = []
        self.nb_postes = 1
        self.date_expiration = None
        self.perpetuelle = False
        self.version_nexora = '2.0'
        self.reference = ''
        self.jours_restants = 0
        self.expire_bientot = False

    def to_dict(self):
        return {
            'valide': self.valide, 'erreur': self.erreur,
            'nom_societe': self.nom_societe, 'pays': self.pays,
            'modules': self.modules, 'modules_noms': self.modules_noms,
            'nb_postes': self.nb_postes,
            'date_expiration': str(self.date_expiration) if self.date_expiration else None,
            'perpetuelle': self.perpetuelle,
            'jours_restants': self.jours_restants,
            'expire_bientot': self.expire_bientot,
            'reference': self.reference,
        }

class NexoraLicenceVerifier:
    def __init__(self, key=_VERIFY_KEY):
        self._key = key.encode()

    def verifier(self, numero_serie):
        info = LicenceInfo()
        try:
            serial = numero_serie.strip().upper().replace(' ', '').replace('-', '')
            if not serial.startswith(SERIAL_PREFIX + SERIAL_VERSION):
                info.erreur = 'Format de numero de serie invalide'
                return info
            payload_b64 = serial[len(SERIAL_PREFIX) + len(SERIAL_VERSION):]
            pad = 4 - len(payload_b64) % 4
            if pad != 4:
                payload_b64 += '=' * pad
            try:
                payload_bytes = base64.b32decode(payload_b64)
            except Exception:
                info.erreur = 'Numero de serie corrompu'
                return info
            if len(payload_bytes) < 36:
                info.erreur = 'Numero de serie trop court'
                return info
            data_bytes = payload_bytes[:-32]
            sig_bytes  = payload_bytes[-32:]
            expected   = hmac.new(self._key, data_bytes, hashlib.sha256).digest()
            if not hmac.compare_digest(sig_bytes, expected):
                info.erreur = 'Numero de serie invalide - signature incorrecte'
                return info
            data = json.loads(data_bytes.decode('utf-8'))
            info.nom_societe    = data.get('soc', '')
            info.pays           = data.get('pay', '')
            info.nb_postes      = int(data.get('pos', 1))
            info.version_nexora = data.get('ver', '2.0')
            info.reference      = data.get('ref', '')
            module_codes        = data.get('mod', [])
            info.modules        = [MODULE_MAP.get(m, m.lower()) for m in module_codes]
            info.modules_noms   = [MODULES_NOMS.get(m, m) for m in module_codes]
            exp_str = data.get('exp', '')
            if exp_str == 'PERP':
                info.perpetuelle    = True
                info.jours_restants = 99999
            else:
                exp_date = datetime.strptime(exp_str, '%Y%m%d').date()
                info.date_expiration = exp_date
                delta = (exp_date - date.today()).days
                info.jours_restants = max(0, delta)
                if delta < 0:
                    info.erreur = 'Licence expiree depuis le ' + exp_date.strftime('%d/%m/%Y')
                    return info
                info.expire_bientot = delta < 30
            info.valide = True
            log.info("Licence valide: %s | exp: %s | postes: %d",
                     info.nom_societe, exp_str, info.nb_postes)
            return info
        except Exception as e:
            info.erreur = 'Erreur de verification: ' + str(e)
            log.error("Erreur licence: %s", e)
            return info

class NexoraLicenceManager:
    def __init__(self, db_get_config, db_set_config):
        self._get = db_get_config
        self._set = db_set_config
        self._verifier = NexoraLicenceVerifier()
        self._cache = None

    def get_licence(self, force=False):
        if self._cache and not force:
            return self._cache
        serial = self._get('licence_serial', '')
        if not serial:
            info = LicenceInfo()
            info.erreur = 'Aucune licence activee'
            self._cache = info
            return info
        info = self._verifier.verifier(serial)
        self._cache = info
        return info

    def activer(self, numero_serie):
        info = self._verifier.verifier(numero_serie)
        if info.valide:
            clean = numero_serie.strip().upper().replace(' ', '').replace('-', '')
            self._set('licence_serial',   clean)
            self._set('licence_societe',  info.nom_societe)
            self._set('licence_modules',  ','.join(info.modules))
            self._set('licence_postes',   str(info.nb_postes))
            self._set('licence_exp',      str(info.date_expiration) if info.date_expiration else 'PERP')
            self._set('licence_activee_le', str(date.today()))
            self._cache = info
            log.info("Licence activee: %s", info.nom_societe)
        return info

    def desactiver(self):
        self._set('licence_serial', '')
        self._cache = None

    def is_module_autorise(self, module):
        info = self.get_licence()
        if not info.valide:
            return self.mode_demonstration()
        if info.perpetuelle or not info.modules:
            return True
        return module in info.modules

    def mode_demonstration(self):
        serial = self._get('licence_serial', '')
        if serial:
            return False
        installed = self._get('installed_date', '')
        if not installed:
            self._set('installed_date', str(date.today()))
            return True
        try:
            d = datetime.strptime(installed, '%Y-%m-%d').date()
            return (date.today() - d).days <= 30
        except Exception:
            return False

    def jours_demo_restants(self):
        installed = self._get('installed_date', '')
        if not installed:
            return 30
        try:
            d = datetime.strptime(installed, '%Y-%m-%d').date()
            return max(0, 30 - (date.today() - d).days)
        except Exception:
            return 0

_licence_manager: Optional[NexoraLicenceManager] = None

def init_licence(db_get_config, db_set_config):
    global _licence_manager
    _licence_manager = NexoraLicenceManager(db_get_config, db_set_config)

def get_licence_manager():
    return _licence_manager
