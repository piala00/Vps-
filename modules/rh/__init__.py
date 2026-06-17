from flask import Blueprint
bp = Blueprint("rh", __name__, url_prefix="")
from . import routes
