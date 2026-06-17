from flask import Blueprint
bp = Blueprint("comptabilite", __name__, url_prefix="")
from . import routes
