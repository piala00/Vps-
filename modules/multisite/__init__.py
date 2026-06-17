from flask import Blueprint
bp = Blueprint("multisite", __name__, url_prefix="")
from . import routes
