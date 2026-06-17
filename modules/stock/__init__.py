from flask import Blueprint
bp = Blueprint("stock", __name__, url_prefix="")
from . import routes
