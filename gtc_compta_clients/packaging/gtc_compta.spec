# -*- mode: python ; coding: utf-8 -*-
# PyInstaller : dossier autonome (onedir, plus fiable que onefile pour CustomTkinter).
# Lancer depuis packaging\ : python -m PyInstaller --noconfirm --clean gtc_compta.spec
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas, binaries, hidden = [], [], []
for pkg in ("customtkinter",):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h
datas += [
    (os.path.join(ROOT, "gtc_compta", "db", "migrations"), os.path.join("gtc_compta", "db", "migrations")),
    (os.path.join(ROOT, "config.example.json"), "."),
    (os.path.join(ROOT, "vba"), "vba"),
]
hidden += ["pyodbc", "openpyxl", "reportlab", "reportlab.pdfgen", "tkinter", "tkinter.filedialog",
           "tkinter.messagebox", "tkinter.ttk", "darkdetect"]

a = Analysis([os.path.join(ROOT, "run.py")], pathex=[ROOT], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=["pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GTC_Compta_Clients", console=False,
          upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="GTC_Compta_Clients", upx=False)
