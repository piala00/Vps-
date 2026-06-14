from flask import Blueprint
bp = Blueprint('rapports', __name__, url_prefix='')
from . import routes
