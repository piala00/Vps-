# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('core', 'core'),
        ('modules', 'modules'),
    ],
    hiddenimports=[
        'flask', 'jinja2', 'werkzeug', 'click',
        'pyodbc', 'openpyxl', 'sqlite3', 'telegram',
        'modules.stock.routes',
        'modules.logistique.routes',
        'modules.commercial.routes',
        'modules.comptabilite.routes',
        'modules.caisse.routes',
        'modules.rh.routes',
        'modules.consolidation.routes',
        'modules.multisite.routes',
        'modules.rapports.routes',
        'modules.parametres.routes',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name='NEXORA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='static/img/nexora.ico',
)
