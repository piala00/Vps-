from flask import Blueprint
bp = Blueprint('commercial', __name__, url_prefix='')
from . import routes
