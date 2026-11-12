"""Composants d'interface communs (CustomTkinter + ttk.Treeview)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

BLEU = "#1F4E79"
BLEU_CLAIR = "#DDEBF7"
VERT = "#2E7D32"
ORANGE = "#E65100"
ROUGE = "#C62828"
GRIS = "#F3F5F8"

COULEUR_STATUT = {"VALIDE": "#E8F5E9", "RAPPROCHE": "#E3F2FD", "ECART_A_ANALYSER": "#FFF3E0",
                  "BLOQUE": "#FFEBEE", "EN_ATTENTE_SAGE": "#F3E5F5", "A_RAPPROCHER": "#FFFDE7",
                  "FAVORABLE": "#E8F5E9", "SOUS_CONDITION": "#FFF3E0", "DEFAVORABLE": "#FFEBEE",
                  "DONNEES_INSUFFISANTES": "#ECEFF1", "BLOQUANT": "#FFEBEE", "AVERTISSEMENT": "#FFF3E0",
                  "CONFIRME_PAR_CLIENT": "#E8F5E9", "EN_POINTAGE": "#FFF3E0", "CONTESTE": "#FFEBEE"}


def style_treeview(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure("Treeview", rowheight=24, font=("Segoe UI", 10), background="white", fieldbackground="white")
    st.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background=BLEU_CLAIR)
    st.map("Treeview", background=[("selected", "#90CAF9")], foreground=[("selected", "black")])


class Table(ctk.CTkFrame):
    """Treeview avec ascenseurs. colonnes : [(cle, titre, largeur, ancre)]."""

    def __init__(self, master, colonnes, height=12, selectmode="browse", on_select=None, on_double=None):
        super().__init__(master, fg_color="transparent")
        self.colonnes = colonnes
        self.tv = ttk.Treeview(self, columns=[c[0] for c in colonnes], show="headings", height=height,
                               selectmode=selectmode)
        for key, titre, larg, anc in colonnes:
            self.tv.heading(key, text=titre)
            self.tv.column(key, width=larg, anchor=anc, stretch=True)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tv.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tv.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        for st, col in COULEUR_STATUT.items():
            self.tv.tag_configure(st, background=col)
        self._data: dict[str, object] = {}
        if on_select:
            self.tv.bind("<<TreeviewSelect>>", lambda e: on_select(self.selection()))
        if on_double:
            self.tv.bind("<Double-1>", lambda e: on_double(self.selection()))

    def remplir(self, lignes, valeurs, tag=None):
        self.tv.delete(*self.tv.get_children())
        self._data.clear()
        for i, l in enumerate(lignes):
            iid = str(i)
            self._data[iid] = l
            t = tag(l) if tag else None
            self.tv.insert("", "end", iid=iid, values=valeurs(l), tags=(t,) if t else ())

    def selection(self):
        sel = self.tv.selection()
        return self._data.get(sel[0]) if sel else None

    def selections(self):
        return [self._data[i] for i in self.tv.selection()]

    def toutes(self):
        return list(self._data.values())


def titre_page(master, texte, sous_titre=""):
    f = ctk.CTkFrame(master, fg_color=BLEU, corner_radius=0, height=56)
    f.pack(fill="x")
    ctk.CTkLabel(f, text=texte, text_color="white", font=ctk.CTkFont(size=20, weight="bold")).pack(
        side="left", padx=18, pady=10)
    if sous_titre:
        ctk.CTkLabel(f, text=sous_titre, text_color="#CFE3F7", font=ctk.CTkFont(size=12)).pack(
            side="left", padx=4)
    return f


def barre(master):
    f = ctk.CTkFrame(master, fg_color="transparent")
    f.pack(fill="x", padx=14, pady=(10, 4))
    return f


def bouton(master, texte, cmd, couleur=None, actif=True, motif="", **kw):
    """Bouton : s'il est desactive, le motif est affiche dans une infobulle et au clic."""
    b = ctk.CTkButton(master, text=texte, command=cmd, fg_color=couleur or BLEU, **kw)
    if not actif:
        b.configure(state="disabled", fg_color="#9E9E9E")
        if motif:
            Infobulle(b, motif)
    return b


class Infobulle:
    def __init__(self, widget, texte):
        self.w, self.t, self.tip = widget, texte, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip:
            return
        x, y = self.w.winfo_rootx() + 10, self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.t, background="#FFFDE7", relief="solid", borderwidth=1,
                 font=("Segoe UI", 9), wraplength=360, justify="left").pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def info(msg, titre="Information"):
    messagebox.showinfo(titre, msg)


def erreur(msg, titre="Erreur"):
    messagebox.showerror(titre, msg)


def confirmer(msg, titre="Confirmation"):
    return messagebox.askyesno(titre, msg)


def demander_texte(parent, titre, invite, obligatoire=True):
    d = ctk.CTkInputDialog(text=invite, title=titre)
    v = d.get_input()
    if v is None:
        return None
    v = v.strip()
    if obligatoire and not v:
        erreur("Saisie obligatoire.")
        return None
    return v


def champ(master, libelle, largeur=180, valeur=""):
    f = ctk.CTkFrame(master, fg_color="transparent")
    f.pack(side="left", padx=(0, 10))
    ctk.CTkLabel(f, text=libelle, font=ctk.CTkFont(size=11)).pack(anchor="w")
    e = ctk.CTkEntry(f, width=largeur)
    e.pack()
    if valeur:
        e.insert(0, valeur)
    return e
