import os

class Config:
    SECRET_KEY        = os.environ.get('NEXORA_SECRET', 'NEXORA_DEV_KEY_2026')
    PORT              = int(os.environ.get('NEXORA_PORT', 5050))
    DEBUG             = False
    BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
    DB_PATH           = os.environ.get('NEXORA_DB_PATH') or os.path.join(BASE_DIR, 'nexora_local.db')
    LICENCE_VERIFY_KEY = 'NEXORA_LIC_V1_SECRET_2026_YOUSSOUF_HAMADOU_GTC'
    COLOR_NAVY        = '#1A3263'
    COLOR_GOLD        = '#FBC013'
