from flask import Blueprint
bp = Blueprint('logistique', __name__, url_prefix='')
from . import routes
