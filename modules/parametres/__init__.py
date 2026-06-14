from flask import Blueprint
bp = Blueprint('parametres', __name__, url_prefix='')
from . import routes
