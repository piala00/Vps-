from flask import Blueprint
bp = Blueprint("caisse", __name__, url_prefix="")
from . import routes
