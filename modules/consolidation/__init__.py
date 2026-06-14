from flask import Blueprint
bp = Blueprint('consolidation', __name__, url_prefix='')
from . import routes
