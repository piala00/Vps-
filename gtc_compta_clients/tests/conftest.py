import copy
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gtc_compta.config import DEFAULTS  # noqa: E402
from gtc_compta.db import Database  # noqa: E402
from gtc_compta.sage.fake import FakeSageAdapter  # noqa: E402
from gtc_compta.services import clients as svc_clients  # noqa: E402
from gtc_compta.services.auth import Utilisateur  # noqa: E402

DEMO = ROOT / "demo"
REF = date(2026, 9, 30)
J1 = date(2026, 10, 1)
CORR = {"ETS ALPHA": "CL001", "QUINCAILLERIE BETA": "CL002", "SOCIETE GAMMA": "CL003",
        "DELTA SARL": "CL004", "CLIENTS DETAILS BTA": "CL099", "COMPTE DE LIAISON": "CL050"}


@pytest.fixture(scope="session", autouse=True)
def demo_files():
    if not (DEMO / "RC_DEMO_SYNTHETIQUE.xlsx").exists():
        subprocess.check_call([sys.executable, str(ROOT / "tools" / "make_demo.py")])
    return DEMO


@pytest.fixture
def cfg():
    c = copy.deepcopy(DEFAULTS)
    c["rapport"]["types_documents"]["FRCB"] = {"nature": "AVOIR", "sens": "C", "confirme": False}
    return c


@pytest.fixture
def user():
    return Utilisateur("compta1", "Comptable Test", "comptable_controleur")


@pytest.fixture
def operateur():
    return Utilisateur("op1", "Operateur", "operateur")


@pytest.fixture
def sage(demo_files):
    return FakeSageAdapter.depuis_json(demo_files / "sage_demo.json")


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def base(db, user, sage, cfg):
    """Referentiel synchronise + correspondances verifiees + soldes d'ouverture au 30/09."""
    svc_clients.synchroniser_clients(db, user, sage, cfg["rapport"]["comptes_collectifs"])
    for lib, ct in CORR.items():
        svc_clients.definir_correspondance(db, user, lib, ct)
    svc_clients.importer_soldes_ouverture(db, user, sage, REF)
    return db
