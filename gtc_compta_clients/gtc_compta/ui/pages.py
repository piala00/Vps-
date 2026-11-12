"""Les dix modules de l'application. Chaque bouton execute une action reelle ou est
desactive avec son motif (infobulle)."""
from __future__ import annotations

import json
import platform
import sys
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .. import __version__
from ..excel import preparation as prep
from ..excel.report_parser import ParseurRapport, lire_feuille
from ..money import fmt_fcfa, parse_montant
from ..sage.base import SageIndisponible
from ..services import clients as svc_clients
from ..services import documents as docs
from ..services import imports, pointing, printing, solvency
from ..services import reconciliation as reco
from ..services.ledger import fiche_client
from ..text import normaliser
from .widgets import (BLEU, ORANGE, ROUGE, VERT, Table, barre, bouton, champ, confirmer, demander_texte,
                      erreur, info, titre_page)


def _date(txt: str) -> date:
    txt = (txt or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Date invalide : '{txt}' (format JJ/MM/AAAA)")


def _fd(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso or ""


class Page(ctk.CTkFrame):
    titre = ""
    sous_titre = ""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app, self.ctx = app, app.ctx
        self.db, self.user, self.cfg = self.ctx.db, self.ctx.user, self.ctx.cfg
        titre_page(self, self.titre, self.sous_titre)
        self.construire()

    @property
    def sage(self):
        return self.ctx.sage

    def construire(self):
        raise NotImplementedError

    def autorise(self, action):
        return self.user.peut(action), f"Reserve aux roles autorises ({action})"


# =====================================================================================
class Accueil(Page):
    titre = "Tableau de bord"

    def construire(self):
        db = self.db
        derniere = db.one("SELECT date_rapport, importe_le FROM import_batches ORDER BY date_rapport DESC LIMIT 1")
        d = derniere[0] if derniere else None
        self.sous_titre = ""
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=12)
        stats = {r[0]: r[1] for r in db.query(
            "SELECT statut, COUNT(*) FROM daily_reconciliations WHERE obsolete=0 AND date_arrete=? GROUP BY statut",
            (d,))} if d else {}
        q = printing.file_attente(db, self.cfg["impression"])
        cartes = [
            ("Dernier rapport traite", _fd(d) if d else "aucun", BLEU),
            ("Fiches validees", stats.get("VALIDE", 0), VERT),
            ("Ecarts a analyser", stats.get("ECART_A_ANALYSER", 0) + stats.get("A_RAPPROCHER", 0), ORANGE),
            ("En attente Sage / bloquees", stats.get("EN_ATTENTE_SAGE", 0) + stats.get("BLOQUE", 0), ROUGE),
            ("Clients", db.scalar("SELECT COUNT(*) FROM clients", default=0), BLEU),
            ("Fiches a imprimer", len(q), BLEU),
            ("Anomalies CR ouvertes (impact solde)",
             db.scalar("SELECT COUNT(*) FROM anomalies_cr WHERE statut='OUVERTE' AND impact_solde=1", default=0), ROUGE),
        ]
        for i, (lib, val, col) in enumerate(cartes):
            c = ctk.CTkFrame(grid, fg_color="white", corner_radius=8, border_width=1, border_color="#D0D7E2")
            c.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
            grid.grid_columnconfigure(i % 3, weight=1)
            ctk.CTkLabel(c, text=lib, text_color="#555").pack(anchor="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(c, text=str(val), text_color=col, font=ctk.CTkFont(size=26, weight="bold")).pack(
                anchor="w", padx=14, pady=(0, 10))
        sold = db.one("SELECT SUM(solde_sage) FROM daily_reconciliations WHERE obsolete=0 AND statut='VALIDE' "
                      "AND date_arrete=?", (d,)) if d else None
        ctk.CTkLabel(self, text=f"Total des soldes valides au {_fd(d) if d else '-'} : "
                                f"{fmt_fcfa(sold[0]) if sold and sold[0] is not None else '-'} FCFA     "
                                "Creances echues : non disponible (regle d'echeance Sage a valider)",
                     anchor="w").pack(fill="x", padx=22)
        ctk.CTkLabel(self, text="Alertes ouvertes", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=22, pady=(14, 2))
        t = Table(self, [("date", "Date", 140, "w"), ("type", "Type", 200, "w"), ("ct", "Client", 90, "w"),
                         ("msg", "Message", 700, "w")], height=8)
        t.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        t.remplir(db.query("SELECT * FROM alertes WHERE statut='OUVERTE' ORDER BY id DESC LIMIT 200"),
                  lambda r: (r["cree_le"], r["type"], r["ct_num"] or "", r["message"]))
        self.t_alertes = t
        b = barre(self)
        bouton(b, "Marquer les alertes comme traitees", self.clore_alertes,
               actif=self.user.peut("valider_fiche"), motif="Reserve au comptable controleur").pack(side="left")
        bouton(b, "Verifier dans Sage (recu negatif)", self.verifier_recu, couleur="#455A64",
               actif=self.user.peut("reprise_sage"), motif="Reserve au comptable controleur").pack(side="left", padx=6)

    def verifier_recu(self):
        from ..services import controles
        a = self.t_alertes.selection()
        if not a:
            return erreur("Selectionner une alerte ANNULATION_RECU_A_VERIFIER.")
        try:
            mid = controles.mouvement_de_l_alerte(self.db, a["id"])
        except ValueError as exc:
            return erreur(str(exc))
        self.app.tache("Controle du recu negatif dans Sage",
                       lambda: controles.verifier_recu_negatif_dans_sage(self.db, self.user, self.sage, mid),
                       lambda r: (info("\n".join(r["details"]), f"Resultat : {r['conclusion']}"),
                                  self.app.afficher("accueil")))

    def clore_alertes(self):
        if confirmer("Marquer toutes les alertes ouvertes comme traitees ?"):
            with self.db.transaction():
                self.db.execute("UPDATE alertes SET statut='TRAITEE' WHERE statut='OUVERTE'")
                self.db.audit(self.user.login, "ALERTES_TRAITEES")
            self.app.afficher("accueil")


# =====================================================================================
class Clients(Page):
    titre = "Clients"
    sous_titre = "Referentiel Sage (lecture seule) + champs manuels"

    def construire(self):
        b = barre(self)
        self.recherche = champ(b, "Recherche (code, nom, tel.)", 240)
        self.recherche.bind("<Return>", lambda e: self.charger())
        f = ctk.CTkFrame(b, fg_color="transparent")
        f.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(f, text="Zone", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.zone = ctk.CTkComboBox(f, values=["(toutes)"] + svc_clients.zones(self.db), width=160,
                                    command=lambda _v: self.charger())
        self.zone.set("(toutes)")
        self.zone.pack()
        bouton(b, "Rechercher", self.charger, width=110).pack(side="left", pady=(16, 0))
        ok, m = self.autorise("synchro_sage")
        bouton(b, "Synchroniser depuis Sage", self.synchro, actif=ok, motif=m).pack(side="left", padx=6, pady=(16, 0))
        ok, m = self.autorise("soldes_ouverture")
        bouton(b, "Importer soldes d'ouverture", self.soldes, actif=ok, motif=m).pack(side="left", padx=6, pady=(16, 0))
        ok, m = self.autorise("correspondance_client")
        bouton(b, "Correspondances rapport -> Sage", self.correspondances, actif=ok, motif=m).pack(
            side="left", padx=6, pady=(16, 0))

        corps = ctk.CTkFrame(self, fg_color="transparent")
        corps.pack(fill="both", expand=True, padx=14, pady=8)
        self.table = Table(corps, [("ct", "Code", 80, "w"), ("nom", "Intitule", 260, "w"), ("zone", "Zone", 120, "w"),
                                   ("tel", "Telephone", 110, "w"), ("ville", "Ville", 100, "w"),
                                   ("enc", "Encours autorise", 120, "e"), ("delai", "Delai (j)", 70, "e"),
                                   ("ouv", "Solde ouverture", 120, "e")],
                           height=20, on_select=self.selection)
        self.table.pack(side="left", fill="both", expand=True)
        p = ctk.CTkFrame(corps, width=330, fg_color="white", corner_radius=8)
        p.pack(side="right", fill="y", padx=(10, 0))
        self.lbl = ctk.CTkLabel(p, text="Selectionner un client", font=ctk.CTkFont(size=14, weight="bold"),
                                wraplength=300)
        self.lbl.pack(padx=12, pady=10, anchor="w")
        self.entrees = {}
        for k, lib in [("zone", "Zone geographique"), ("delai_reglement_jours", "Delai de reglement (jours)"),
                       ("telephone_whatsapp", "Telephone WhatsApp"), ("telegram", "Identifiant Telegram"),
                       ("contacts", "Contacts complementaires"), ("preference_communication", "Preference de communication"),
                       ("notes_recouvrement", "Notes de recouvrement")]:
            ctk.CTkLabel(p, text=lib, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12)
            e = ctk.CTkEntry(p, width=300)
            e.pack(padx=12, pady=(0, 6))
            self.entrees[k] = e
        ok, m = self.autorise("champs_manuels")
        bouton(p, "Enregistrer les champs manuels", self.enregistrer, actif=ok, motif=m).pack(padx=12, pady=10)
        self.courant = None
        self.charger()

    def charger(self):
        z = self.zone.get()
        rows = svc_clients.lister_clients(self.db, self.recherche.get().strip(), None if z == "(toutes)" else z,
                                          limite=2000)
        ob = {r[0]: r[1] for r in self.db.query(
            "SELECT ct_num, solde FROM opening_balances o WHERE date_reference=(SELECT MAX(date_reference) "
            "FROM opening_balances WHERE ct_num=o.ct_num)")}
        self.table.remplir(rows, lambda r: (r["ct_num"], r["intitule"], r["zone"] or "", r["telephone"] or "",
                                            r["ville"] or "", fmt_fcfa(r["encours_autorise"]),
                                            r["delai_reglement_jours"] or "", fmt_fcfa(ob.get(r["ct_num"]))))
        self.app.set_statut(f"{len(rows)} client(s) affiche(s)")

    def selection(self, r):
        if not r:
            return
        self.courant = r["ct_num"]
        self.lbl.configure(text=f"{r['intitule']}\n{r['ct_num']}" + ("  (compte collectif)" if r["est_collectif"] else ""))
        for k, e in self.entrees.items():
            e.delete(0, "end")
            if r[k] not in (None, ""):
                e.insert(0, str(r[k]))

    def enregistrer(self):
        if not self.courant:
            return erreur("Selectionner un client.")
        vals = {k: (e.get().strip() or None) for k, e in self.entrees.items()}
        if self.app.action(svc_clients.maj_champs_manuels, self.db, self.user, self.courant, **vals) is None:
            self.app.set_statut(f"Champs manuels de {self.courant} enregistres")
            self.charger()

    def synchro(self):
        coll = self.cfg["rapport"]["comptes_collectifs"]
        self.app.tache("Synchronisation des clients Sage",
                       lambda: svc_clients.synchroniser_clients(self.db, self.user, self.sage, coll),
                       lambda r: (info(f"{r['total']} clients lus : {r['nouveaux']} nouveaux, {r['mis_a_jour']} mis a "
                                       "jour.\nLes champs manuels sont conserves."), self.charger()))

    def soldes(self):
        d = demander_texte(self, "Soldes d'ouverture", "Date de reference Sage (JJ/MM/AAAA) :")
        if not d:
            return
        try:
            dr = _date(d)
        except ValueError as exc:
            return erreur(str(exc))
        if not confirmer(f"Importer les soldes Sage au {dr:%d/%m/%Y} comme soldes d'ouverture ?\n"
                         "Cette date doit etre verifiee dans Sage (balance clients)."):
            return
        self.app.tache("Import des soldes d'ouverture",
                       lambda: svc_clients.importer_soldes_ouverture(self.db, self.user, self.sage, dr),
                       lambda n: (info(f"{n} solde(s) d'ouverture importe(s) au {dr:%d/%m/%Y}."), self.charger()))

    def correspondances(self):
        FenetreCorrespondances(self)


class FenetreCorrespondances(ctk.CTkToplevel):
    def __init__(self, page):
        super().__init__(page)
        self.page, self.db = page, page.db
        self.title("Correspondances libelle du rapport -> code tiers Sage")
        self.geometry("900x560")
        self.transient(page.app)
        ctk.CTkLabel(self, text="Aucune affectation n'est faite sur simple ressemblance : chaque correspondance "
                                "est verifiee et enregistree par un comptable.", wraplength=860).pack(padx=12, pady=8)
        b = ctk.CTkFrame(self, fg_color="transparent")
        b.pack(fill="x", padx=12)
        self.lib = champ(b, "Libelle tel qu'ecrit dans le rapport", 300)
        self.ct = champ(b, "Code tiers Sage", 120)
        bouton(b, "Suggestions", self.suggerer, width=110).pack(side="left", pady=(16, 0))
        bouton(b, "Enregistrer", self.enregistrer, couleur=VERT, width=110).pack(side="left", padx=6, pady=(16, 0))
        b2 = ctk.CTkFrame(self, fg_color="transparent")
        b2.pack(fill="x", padx=12, pady=(4, 0))
        bouton(b2, "1. Generer le fichier a completer depuis un rapport...", self.exporter, couleur="#455A64").pack(side="left")
        bouton(b2, "2. Importer le fichier complete...", self.importer, couleur="#455A64").pack(side="left", padx=6)
        self.sugg = Table(self, [("ct", "Code", 90, "w"), ("nom", "Intitule Sage", 400, "w"), ("s", "Similarite", 90, "e")],
                          height=5, on_double=lambda r: r and (self.ct.delete(0, "end"), self.ct.insert(0, r[0])))
        self.sugg.pack(fill="x", padx=12, pady=6)
        self.t = Table(self, [("lib", "Libelle rapport", 300, "w"), ("ct", "Code", 90, "w"), ("nom", "Intitule Sage", 260, "w"),
                              ("par", "Verifie par", 100, "w"), ("le", "Le", 140, "w")], height=10)
        self.t.pack(fill="both", expand=True, padx=12, pady=6)
        self.charger()

    def charger(self):
        self.t.remplir(self.db.query("SELECT a.*, c.intitule FROM client_aliases a JOIN clients c ON c.ct_num=a.ct_num "
                                     "ORDER BY a.libelle_original"),
                       lambda r: (r["libelle_original"], r["ct_num"], r["intitule"], r["verifie_par"], r["verifie_le"]))

    def exporter(self):
        src = filedialog.askopenfilename(title="Rapport commercial (lecture seule)", filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not src:
            return
        dest = self.page.ctx.data_dir / "exports" / f"CORRESPONDANCES_A_COMPLETER_{datetime.now():%Y%m%d_%H%M}.xlsx"
        self.page.app.tache("Lecture du rapport", lambda: svc_clients.exporter_libelles_a_completer(
            self.db, self.page.cfg["rapport"], src, dest), lambda n: (info(
                f"{n} libelle(s) sans correspondance exporte(s) :\n{dest}\n\nRenseigner la colonne code_tiers_sage "
                "(les suggestions sont a verifier), puis utiliser le bouton 2."), docs.ouvrir_fichier(dest)))

    def importer(self):
        p = filedialog.askopenfilename(title="Fichier de correspondances complete", filetypes=[("Excel", "*.xlsx")])
        if not p:
            return
        r = self.page.app.action(svc_clients.importer_correspondances_xlsx, self.db, self.page.user, p)
        if r:
            ok, err = r
            info(f"{ok} correspondance(s) enregistree(s)." + ("\n\nRejets :\n" + "\n".join(err[:20]) if err else ""))
            self.charger()

    def suggerer(self):
        self.sugg.remplir(svc_clients.suggestions_correspondance(self.db, self.lib.get()), lambda r: r)

    def enregistrer(self):
        lib, ct = self.lib.get().strip(), self.ct.get().strip()
        if not lib or not ct:
            return erreur("Libelle et code tiers obligatoires.")
        if self.page.app.action(svc_clients.definir_correspondance, self.db, self.page.user, lib, ct) is None:
            self.charger()


# =====================================================================================
class Import(Page):
    titre = "Preparation / Importations"
    sous_titre = "Classeur intermediaire -> apercu -> import provisoire -> rapprochement Sage"

    def construire(self):
        b = barre(self)
        ok, m = self.autorise("importer")
        bouton(b, "1. Ouvrir un classeur de preparation (.xlsm / .xlsx)", self.ouvrir, actif=ok, motif=m).pack(side="left")
        bouton(b, "Creer un classeur de preparation depuis une feuille du rapport", self.creer_classeur,
               couleur="#455A64").pack(side="left", padx=8)
        bouton(b, "Historique des BC (mois anterieurs)...", self.historique_bc, couleur="#455A64",
               actif=ok, motif=m).pack(side="left", padx=8)
        self.btn_import = bouton(b, "2. Valider l'import", self.valider, couleur=VERT, actif=False,
                                 motif="Ouvrir d'abord un classeur et verifier l'apercu")
        self.btn_import.pack(side="left", padx=8)
        self.info = ctk.CTkLabel(self, text="Aucun classeur charge.", anchor="w", justify="left", wraplength=1120)
        self.info.pack(fill="x", padx=16)
        tabs = ctk.CTkTabview(self, height=330)
        tabs.pack(fill="both", expand=True, padx=14, pady=4)
        cols_m = [("ct", "Code tiers", 80, "w"), ("cli", "Client (rapport)", 220, "w"), ("ref", "Piece", 110, "w"),
                  ("type", "Type", 100, "w"), ("mt", "Montant", 110, "e"), ("sens", "Sens", 50, "center"),
                  ("bc", "BC origine", 90, "w"), ("ach", "Acheteur (detail)", 140, "w"), ("lig", "Ligne", 60, "e")]
        self.t_mvt = Table(tabs.add("Mouvements retenus"), cols_m, height=12)
        self.t_mvt.pack(fill="both", expand=True)
        self.t_ano = Table(tabs.add("Anomalies"), [("lig", "Ligne", 60, "e"), ("sec", "Section", 100, "w"),
                                                   ("g", "Gravite", 110, "w"), ("motif", "Motif", 420, "w"),
                                                   ("c", "Contenu", 300, "w"), ("p", "Proposition", 260, "w")], height=12)
        self.t_ano.pack(fill="both", expand=True)
        self.t_lots = Table(tabs.add("Historique des lots"), [
            ("id", "Lot", 50, "e"), ("date", "Date rapport", 100, "w"), ("f", "Fichier", 240, "w"),
            ("op", "Operateur", 100, "w"), ("le", "Importe le", 140, "w"), ("st", "Statut", 160, "w"),
            ("i", "Inseres", 70, "e"), ("d", "Deja pres.", 80, "e"), ("c", "Conflits", 70, "e"), ("r", "Rejets", 70, "e")],
            height=12)
        self.t_lots.pack(fill="both", expand=True)
        onglet = tabs.add("Anomalies CR a traiter")
        self.t_acr = Table(onglet, [("d", "Date", 90, "w"), ("code", "Type d'erreur", 200, "w"),
                                    ("cli", "Client (rapport)", 200, "w"), ("ct", "Code", 70, "w"),
                                    ("ref", "Piece", 110, "w"), ("mt", "Montant", 100, "e"),
                                    ("motif", "Motif", 420, "w"), ("lig", "Feuille/ligne", 90, "w")], height=9)
        self.t_acr.pack(fill="both", expand=True)
        ba = ctk.CTkFrame(onglet, fg_color="transparent")
        ba.pack(fill="x", pady=4)
        okc, mc = self.autorise("corriger_mouvement")
        bouton(ba, "Integrer la facture corrigee...", self.integrer_facture, couleur=VERT, actif=okc, motif=mc).pack(side="left")
        bouton(ba, "Reintegrer les lignes rejetees", self.reintegrer, actif=self.user.peut("importer"),
               motif="Reserve aux roles autorises (importer)").pack(side="left", padx=6)
        bouton(ba, "Marquer resolue...", lambda: self.clore_anomalie(False), couleur="#455A64", actif=okc, motif=mc).pack(side="left", padx=6)
        bouton(ba, "Ignorer (sans incidence)...", lambda: self.clore_anomalie(True), couleur=ROUGE, actif=okc, motif=mc).pack(side="left", padx=6)
        self.lignes = None
        self.charger_lots()
        self.charger_anomalies()

    def charger_lots(self):
        self.t_lots.remplir(imports.lots(self.db), lambda r: (r["id"], _fd(r["date_rapport"]), r["fichier"], r["operateur"],
                                                              r["importe_le"], r["statut"], r["nb_inseres"],
                                                              r["nb_deja_presents"], r["nb_conflits"], r["nb_rejets"]))

    def ouvrir(self):
        p = filedialog.askopenfilename(title="Classeur de preparation",
                                       filetypes=[("Classeurs Excel", "*.xlsm *.xlsx")])
        if not p:
            return
        corr = svc_clients.correspondances(self.db)
        self.differences = []
        if self.cfg["rapport"].get("correspondance_auto_intitule_exact"):
            corr = {**svc_clients.correspondances_auto_exactes(self.db), **corr}

        def travail():
            try:
                lignes = prep.lire_export_erp(p)
                source = "EXPORT_ERP (macro)"
            except prep.FormatExportInvalide:
                lignes = []
            res = prep.preparer_depuis_classeur(p, self.cfg["rapport"], corr, self.cfg["agence"])
            if not lignes:   # macros desactivees ou non executees : traitement Python equivalent
                lignes = prep.lignes_export(res)
                source = "COLLAGE traite par l'application (secours)"
            else:            # controle croise macro / application sur les memes donnees
                self.differences = prep.comparer_exports(lignes, prep.lignes_export(res))
                if self.differences:
                    source += f" - ATTENTION {len(self.differences)} difference(s) avec le traitement de controle"
            n = imports.completer_codes(lignes, corr)
            return p, lignes, res, source, n

        self.app.tache("Lecture du classeur", travail, self.apercu)

    def apercu(self, r):
        p, lignes, res, source, n = r
        self.fichier, self.lignes, self.res = p, lignes, res
        self.t_mvt.remplir(lignes, lambda l: (l["code_tiers"] or "?", l["nom_client"], l["reference_piece"],
                                              l["type_mouvement"], fmt_fcfa(l["montant"]), l["sens"],
                                              l["bc_origine"] or "", l["acheteur_detail"] or "", l["source_ligne"]),
                           tag=lambda l: None if l["code_tiers"] else "BLOQUANT")
        anos = res.anomalies if res else []
        self.t_ano.remplir(anos, lambda a: (a.ligne, a.section, a.gravite, a.motif, a.contenu[:80], a.proposition),
                           tag=lambda a: a.gravite)
        sans = sum(1 for l in lignes if not l["code_tiers"])
        tot = {k: sum(l["montant"] for l in lignes if l["type_mouvement"] == k)
               for k in ("FACTURE", "AVOIR", "ACOMPTE", "REGLEMENT")}
        d = lignes[0]["date_rapport"] if lignes else "?"
        st = res.stats if res else {}
        self.info.configure(text=(
            f"Fichier : {Path(p).name}   |   Source : {source}   |   Date du rapport : {_fd(d)}\n"
            f"{len(lignes)} mouvement(s) : factures {fmt_fcfa(tot['FACTURE'])}  avoirs {fmt_fcfa(tot['AVOIR'])}  "
            f"acomptes {fmt_fcfa(tot['ACOMPTE'])}  recouvrements {fmt_fcfa(tot['REGLEMENT'])}  |  {len(anos)} anomalie(s)  |  {sans} ligne(s) sans code tiers "
            f"(seront rejetees)  |  {n} code(s) completes par correspondances verifiees"
            + (f"\nBC/BL seuls ignores : {st.get('bc_seuls_ignores', 0)}  totaux exclus : {st.get('totaux_exclus', 0)}  "
               f"hors perimetre exclus : {st.get('hors_perimetre_exclus', 0)}  annulees : {st.get('annulees', 0)}  "
               f"acomptes : {st.get('acomptes', 0)}" if st else "")
            + ("\nControle des totaux du rapport : " + ("OK - tous les montants sont expliques" if st and all(
                v.get("ecart_non_explique", 0) == 0 and (v["rapport"] is None or v["rapport"] == v["lignes"])
                for v in st.get("controle_totaux", {}).values()) else "ECART - voir Anomalies") if st else "")))
        ok = bool(lignes) and lignes[0]["date_rapport"] and self.user.peut("importer")
        self.btn_import.configure(state="normal" if ok else "disabled", fg_color=VERT if ok else "#9E9E9E")

    def valider(self):
        if not self.lignes:
            return
        if getattr(self, "differences", None) and not confirmer(
                "Le resultat de la macro differe du traitement de controle :\n- " + "\n- ".join(self.differences[:15])
                + "\n\nImporter malgre tout le resultat de la macro ?", "Controle croise"):
            return
        res = getattr(self, "res", None)
        if res is not None and res.date_feuille and res.date_rapport and res.date_feuille != res.date_rapport:
            if not confirmer(f"ATTENTION : la feuille collee est datee du {res.date_feuille:%d/%m/%Y} (cellule A4) mais la "
                             f"date du rapport est le {res.date_rapport:%d/%m/%Y}.\n\nSi la mauvaise journee a ete collee, "
                             "tous les mouvements seraient enregistres a une date fausse.\n\nConfirmez-vous que la "
                             f"feuille est bien celle du {res.date_rapport:%d/%m/%Y} (erreur de date dans le modele) ?",
                             "Date de la feuille"):
                return
            self.db.audit(self.user.login, "DATE_FEUILLE_FORCEE", self.fichier,
                          {"date_imprimee": res.date_feuille.isoformat(), "date_rapport": res.date_rapport.isoformat()})
        if not confirmer(f"Importer {len(self.lignes)} mouvement(s) en zone PROVISOIRE puis lancer le rapprochement "
                         "Sage du jour ?"):
            return
        lignes, fichier = self.lignes, self.fichier
        bons = prep.bons_export(self.res) if getattr(self, "res", None) else []
        anos = prep.anomalies_export(self.res) if getattr(self, "res", None) else []

        def travail():
            rap = imports.importer_lot(self.db, self.user, lignes, fichier, imports.empreinte_fichier(fichier),
                                       bons=bons, anomalies=anos)
            d = date.fromisoformat(lignes[0]["date_rapport"])
            res = [] if rap.deja_importe else reco.rapprocher(self.db, self.user, self.sage, d)
            return rap, res

        def fini(r):
            rap, res = r
            stats = {}
            for x in res:
                stats[x.statut] = stats.get(x.statut, 0) + 1
            info(rap.resume() + (f"\n{rap.alertes_comptant} facture(s) comptant sans acompte connu sur leur BC "
                                 "(voir Accueil > Alertes)" if rap.alertes_comptant else "")
                 + "\n\nRapprochement Sage : " +
                 (", ".join(f"{k} : {v}" for k, v in stats.items()) or "non lance (lot deja importe)") +
                 ("\n\nRejets :\n" + "\n".join(f"ligne {l} : {m}" for l, m in rap.rejets[:15]) if rap.rejets else ""))
            self.btn_import.configure(state="disabled", fg_color="#9E9E9E")
            self.lignes = None
            self.charger_lots()
            self.charger_anomalies()

        self.app.tache("Import et rapprochement", travail, fini)

    def charger_anomalies(self):
        from ..services import anomalies as reg_ano
        rows = reg_ano.lister(self.db, "OUVERTE", impact=True)
        self.t_acr.remplir(rows, lambda r: (_fd(r["date_rapport"]), r["code"], r["client_libelle"], r["ct_num"] or "?",
                                            r["reference"], fmt_fcfa(r["montant"]), r["motif"][:140],
                                            f"{r['feuille'] or ''}/{r['ligne'] or ''}"),
                           tag=lambda r: "BLOQUANT" if r["gravite"] == "BLOQUANT" else "AVERTISSEMENT")

    def integrer_facture(self):
        from ..services import anomalies as reg_ano
        a = self.t_acr.selection()
        if not a:
            return erreur("Selectionner une anomalie (n° de bon a la place de la facture, facture sans numero...).")
        num = demander_texte(self, "Facture corrigee", f"N° de la facture Sage pour la ligne {a['reference'] or ''} "
                                                         f"({a['client_libelle']}, {fmt_fcfa(a['montant'])}) :")
        if not num:
            return
        ct = a["ct_num"] or demander_texte(self, "Client", "Code tiers Sage du client :")
        if ct and self.app.action(reg_ano.integrer_facture_corrigee, self.db, self.user, a["id"], num, ct) is not None:
            info(f"Facture {num.upper()} integree dans la fiche {ct} (provisoire, a rapprocher avec Sage).")
            self.charger_anomalies()

    def reintegrer(self):
        from ..services import anomalies as reg_ano
        r = self.app.action(reg_ano.reintegrer_rejets, self.db, self.user)
        if r:
            info(f"{r['integrees']} ligne(s) reintegree(s) ; {r['toujours_rejetees']} toujours sans code tiers "
                 "(creer les correspondances dans Clients).")
            self.charger_anomalies()

    def clore_anomalie(self, ignorer):
        from ..services import anomalies as reg_ano
        a = self.t_acr.selection()
        if not a:
            return erreur("Selectionner une anomalie.")
        motif = demander_texte(self, "Motif", "Motif (verification effectuee, correction faite...) :")
        if motif and self.app.action(reg_ano.ignorer if ignorer else reg_ano.marquer_resolue, self.db, self.user,
                                     a["id"], motif) is None:
            self.charger_anomalies()

    def historique_bc(self):
        """Charge les acomptes / BP des BC d'un rapport mensuel anterieur (aucun mouvement cree)."""
        src = filedialog.askopenfilename(title="Rapport mensuel anterieur (lecture seule)",
                                         filetypes=[("Excel", "*.xlsx *.xlsm")])
        if src:
            self.app.tache("Chargement de l'historique des bons de commande",
                           lambda: imports.charger_historique_bons(self.db, self.user, src, self.cfg["rapport"],
                                                                  self.cfg["agence"]),
                           lambda n: info(f"{n} ligne(s) de bons de commande enregistree(s) dans le registre.\n"
                                          "Elles servent uniquement a controler les factures comptant."))

    def creer_classeur(self):
        src = filedialog.askopenfilename(title="Rapport commercial (lecture seule)", filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not src:
            return
        feuille = demander_texte(self, "Feuille du jour", "Nom de la feuille (ex. 01) :")
        if not feuille:
            return
        d = demander_texte(self, "Date du rapport", "Date du rapport (JJ/MM/AAAA) :")
        if not d:
            return
        try:
            dr = _date(d)
            rows = lire_feuille(src, feuille)
        except Exception as exc:  # noqa: BLE001
            return erreur(str(exc))
        res = ParseurRapport(self.cfg["rapport"], svc_clients.correspondances(self.db)).analyser(
            rows, "COLLAGE", self.cfg["agence"], dr)
        dest = self.ctx.data_dir / "preparations" / f"GTC_PREPARATION_{dr:%Y%m%d}.xlsx"
        prep.ecrire_classeur_prepare(res, rows, dest, self.user.login)
        self.db.audit(self.user.login, "CLASSEUR_PREPARATION_CREE", str(dest), {"source": src, "feuille": feuille})
        info(f"Classeur de preparation cree (le rapport source n'a pas ete modifie) :\n{dest}\n\n"
             "Verifiez-le puis ouvrez-le avec le bouton 1.")


# =====================================================================================
class Fiches(Page):
    titre = "Fiches clients"
    sous_titre = "Mouvements, solde progressif, factures"

    def construire(self):
        b = barre(self)
        self.ct = champ(b, "Code tiers", 110)
        self.dfin = champ(b, "Arrete au (JJ/MM/AAAA, vide = tout)", 150)
        bouton(b, "Afficher", self.charger, width=100).pack(side="left", pady=(16, 0))
        bouton(b, "Choisir un client...", self.choisir, couleur="#455A64", width=140).pack(side="left", padx=6, pady=(16, 0))
        bouton(b, "Apercu PDF de la fiche", self.apercu, couleur="#455A64").pack(side="left", padx=6, pady=(16, 0))
        self.entete = ctk.CTkLabel(self, text="", anchor="w", justify="left", font=ctk.CTkFont(size=13))
        self.entete.pack(fill="x", padx=16, pady=4)
        self.table = Table(self, [("date", "Date", 90, "w"), ("piece", "Piece", 110, "w"), ("lib", "Libelle", 300, "w"),
                                  ("d", "Debit", 110, "e"), ("c", "Credit", 110, "e"), ("s", "Solde", 120, "e"),
                                  ("st", "Statut", 100, "w"), ("src", "Source", 120, "w")],
                           height=18, on_double=lambda r: self.ouvrir_pdf())
        self.table.pack(fill="both", expand=True, padx=14, pady=4)
        a = barre(self)
        for txt, fn in [("Ouvrir PDF", self.ouvrir_pdf), ("Copier numero", self.copier),
                        ("Preparer envoi WhatsApp", lambda: self.envoi("WHATSAPP")),
                        ("Preparer envoi Telegram", lambda: self.envoi("TELEGRAM"))]:
            bouton(a, txt, fn, width=150).pack(side="left", padx=(0, 6))
        ok, m = self.autorise("corriger_mouvement")
        bouton(a, "Corriger le montant...", self.corriger, couleur=ORANGE, actif=ok, motif=m).pack(side="left", padx=6)
        bouton(a, "Annuler le mouvement...", self.annuler, couleur=ROUGE, actif=ok, motif=m).pack(side="left", padx=6)
        self.fiche = None

    def choisir(self):
        SelecteurClient(self, lambda ct: (self.ct.delete(0, "end"), self.ct.insert(0, ct), self.charger()))

    def charger(self):
        ct = self.ct.get().strip()
        try:
            d = _date(self.dfin.get()) if self.dfin.get().strip() else None
            f = fiche_client(self.db, ct, d)
        except (KeyError, ValueError) as exc:
            return erreur(str(exc))
        self.fiche = f
        r = self.db.one("SELECT statut, date_arrete FROM daily_reconciliations WHERE ct_num=? AND obsolete=0 "
                        "ORDER BY date_arrete DESC LIMIT 1", (ct,))
        from ..services import anomalies as reg_ano
        n_ano, mt_ano = reg_ano.resume_client(self.db, ct)
        garanti = "" if f.solde_garanti else "   ATTENTION : solde d'ouverture absent, solde NON garanti"
        if n_ano:
            garanti += (f"   ATTENTION : {n_ano} anomalie(s) CR non resolue(s) ({fmt_fcfa(mt_ano)} FCFA) peuvent "
                        "affecter ce solde (Preparation / Imports > Anomalies CR)")
        self.entete.configure(text=(
            f"{f.intitule} ({f.ct_num})  zone {f.zone or '-'}   |   Solde anterieur au {_fd(f.date_ouverture) if f.date_ouverture else '-'} : "
            f"{fmt_fcfa(f.solde_ouverture)}   |   Debit {fmt_fcfa(f.total_debit)}  Credit {fmt_fcfa(f.total_credit)}   |   "
            f"Solde final : {fmt_fcfa(f.solde_final)} FCFA{garanti}\n"
            f"Dernier rapprochement Sage : {r[0] + ' au ' + _fd(r[1]) if r else 'aucun'}"),
            text_color=ROUGE if (not f.solde_garanti or n_ano) else "black")
        self.table.remplir(f.lignes, lambda l: (_fd(l.date), l.piece, l.libelle, fmt_fcfa(l.debit) if l.debit else "",
                                                fmt_fcfa(l.credit) if l.credit else "", fmt_fcfa(l.solde), l.statut, l.source),
                           tag=lambda l: "A_RAPPROCHER" if l.statut == "PROVISOIRE" else None)

    def _ligne(self):
        l = self.table.selection()
        if not l:
            erreur("Selectionner une ligne de la fiche.")
        return l

    def ouvrir_pdf(self):
        l = self._ligne()
        if l:
            try:
                p = docs.trouver_pdf(self.db, self.sage, l.piece)
                docs.ouvrir_fichier(p)
            except docs.PdfIntrouvable as exc:
                erreur(str(exc), "PDF indisponible")

    def copier(self):
        l = self._ligne()
        if l:
            self.clipboard_clear()
            self.clipboard_append(l.piece)
            self.app.set_statut(f"Numero {l.piece} copie")

    def envoi(self, canal):
        l = self._ligne()
        if l and self.fiche:
            preparer_envoi(self, canal, self.fiche.ct_num, l.piece, self.fiche.solde_final)

    def corriger(self):
        l = self._ligne()
        if not l:
            return
        v = demander_texte(self, "Correction", f"Nouveau montant pour {l.piece} :")
        motif = v and demander_texte(self, "Correction", "Motif de la correction :")
        if v and motif:
            try:
                mt = parse_montant(v)
            except ValueError as exc:
                return erreur(str(exc))
            if self.app.action(imports.corriger_mouvement, self.db, self.user, l.id, motif, montant=mt) is not None:
                self.charger()

    def annuler(self):
        l = self._ligne()
        if not l:
            return
        motif = demander_texte(self, "Annulation", f"Motif de l'annulation de {l.piece} :")
        if motif and confirmer(f"Annuler le mouvement {l.piece} ? (trace conservee)"):
            self.app.action(imports.corriger_mouvement, self.db, self.user, l.id, motif, annuler=True)
            self.charger()

    def apercu(self):
        if not self.fiche:
            return erreur("Afficher d'abord une fiche.")
        dest = self.ctx.data_dir / "impressions" / f"APERCU_{self.fiche.ct_num}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        printing.generer_apercu(self.db, self.fiche.ct_num, dest, self.cfg)
        docs.ouvrir_fichier(dest)


def preparer_envoi(page, canal, ct, piece, solde):
    c = page.db.one("SELECT c.intitule, c.telephone, m.telephone_whatsapp, m.telegram FROM clients c "
                    "LEFT JOIN client_manual_fields m ON m.ct_num=c.ct_num WHERE c.ct_num=?", (ct,))
    msg = docs.message_facture(c["intitule"], piece, solde)
    try:
        pdf = docs.trouver_pdf(page.db, page.sage, piece)
        dossier = page.cfg["documents"].get("dossier_export") or str(page.ctx.data_dir / "exports")
        copie = docs.exporter_copie(page.db, page.user, pdf, dossier)
        note = f"Copie du PDF prete a joindre :\n{copie}"
    except docs.PdfIntrouvable as exc:
        note = f"{exc}\nLe message sera prepare sans piece jointe."
    try:
        url = (docs.lien_whatsapp(c["telephone_whatsapp"] or c["telephone"], msg) if canal == "WHATSAPP"
               else docs.lien_telegram(c["telegram"], msg))
    except ValueError as exc:
        return erreur(str(exc))
    page.clipboard_clear()
    page.clipboard_append(msg)
    if confirmer(f"{note}\n\nLe message a ete copie dans le presse-papiers.\nOuvrir {canal.title()} maintenant ?\n"
                 "(l'envoi et l'ajout de la piece jointe restent a confirmer par vous dans l'application)"):
        import webbrowser
        webbrowser.open(url)
        docs.journaliser_transmission(page.db, page.user, canal, ct, piece)


class SelecteurClient(ctk.CTkToplevel):
    def __init__(self, page, callback):
        super().__init__(page)
        self.title("Choisir un client")
        self.geometry("620x480")
        self.transient(page.app)
        self.db, self.cb = page.db, callback
        self.e = ctk.CTkEntry(self, placeholder_text="Rechercher...", width=400)
        self.e.pack(padx=10, pady=8)
        self.e.bind("<KeyRelease>", lambda _e: self.charger())
        self.t = Table(self, [("ct", "Code", 90, "w"), ("nom", "Intitule", 330, "w"), ("z", "Zone", 120, "w")], height=14,
                       on_double=self.choisir)
        self.t.pack(fill="both", expand=True, padx=10, pady=6)
        self.charger()

    def charger(self):
        self.t.remplir(svc_clients.lister_clients(self.db, self.e.get().strip(), limite=300),
                       lambda r: (r["ct_num"], r["intitule"], r["zone"] or ""))

    def choisir(self, r):
        if r:
            self.destroy()
            self.cb(r["ct_num"])


# =====================================================================================
class Rapprochement(Page):
    titre = "Rapprochement Sage"
    sous_titre = "Controle quotidien ERP / Sage Comptabilite (lecture seule)"

    def construire(self):
        b = barre(self)
        d = self.db.scalar("SELECT MAX(date_rapport) FROM import_batches")
        self.date = champ(b, "Date d'arrete (JJ/MM/AAAA)", 140, _fd(d) if d else date.today().strftime("%d/%m/%Y"))
        bouton(b, "Afficher", self.charger, width=90).pack(side="left", pady=(16, 0))
        bouton(b, "Lancer le rapprochement", self.lancer).pack(side="left", padx=6, pady=(16, 0))
        bouton(b, "Verifier les ecritures retroactives", self.retro, couleur="#455A64").pack(side="left", padx=6, pady=(16, 0))
        self.t = Table(self, [("ct", "Code", 80, "w"), ("nom", "Client", 230, "w"), ("st", "Statut", 150, "w"),
                              ("erp", "Solde ERP", 110, "e"), ("sage", "Solde Sage", 110, "e"), ("ec", "Ecart", 100, "e"),
                              ("msg", "Message", 300, "w"), ("val", "Valide par", 140, "w")],
                       height=11, on_select=self.detail)
        self.t.pack(fill="both", expand=True, padx=14, pady=4)
        ctk.CTkLabel(self, text="Ecarts du client selectionne", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16)
        self.te = Table(self, [("type", "Type", 150, "w"), ("j", "Journal", 60, "w"), ("p", "Piece Sage", 100, "w"),
                               ("d", "Date", 90, "w"), ("erp", "Montant ERP", 110, "e"), ("sage", "Montant Sage", 110, "e"),
                               ("desc", "Description", 380, "w"), ("st", "Statut", 140, "w")], height=6)
        self.te.pack(fill="both", expand=True, padx=14, pady=4)
        a = barre(self)
        ok, m = self.autorise("valider_fiche")
        bouton(a, "Valider la fiche (statut RAPPROCHE)", self.valider, couleur=VERT, actif=ok, motif=m).pack(side="left")
        ok, m = self.autorise("reprise_sage")
        bouton(a, "Option A : reprendre l'ecriture Sage", self.option_a, couleur=ORANGE, actif=ok, motif=m).pack(side="left", padx=6)
        bouton(a, "Option B : facture Gescom a etablir", lambda: self.resoudre("OPTION_B_FACTURE_GESCOM"),
               couleur="#455A64", actif=ok, motif=m).pack(side="left", padx=6)
        bouton(a, "Ecart explique", lambda: self.resoudre("EXPLIQUE"), couleur="#455A64", actif=ok, motif=m).pack(side="left", padx=6)
        self.charger()

    def _d(self):
        return _date(self.date.get())

    def charger(self):
        try:
            d = self._d()
        except ValueError as exc:
            return erreur(str(exc))
        rows = reco.dernier_statut(self.db, d)
        self.t.remplir(rows, lambda r: (r["ct_num"], r["intitule"], r["statut"], fmt_fcfa(r["solde_erp"]),
                                        fmt_fcfa(r["solde_sage"]), fmt_fcfa(r["ecart"], True), r["message"] or "",
                                        r["valide_par"] or ""), tag=lambda r: r["statut"])
        self.te.remplir([], lambda r: r)

    def detail(self, r):
        if r:
            self.te.remplir(reco.ecarts_ouverts(self.db, r["id"]),
                            lambda x: (x["type"], x["journal"] or "", x["numero_piece"] or "", _fd(x["date_ecriture"]) if x["date_ecriture"] else "",
                                       fmt_fcfa(x["montant_erp"]), fmt_fcfa(x["montant_sage"]), x["description"], x["statut"]))

    def lancer(self):
        try:
            d = self._d()
        except ValueError as exc:
            return erreur(str(exc))

        def fini(res):
            st = {}
            for x in res:
                st[x.statut] = st.get(x.statut, 0) + 1
            self.charger()
            info(f"{len(res)} client(s) controle(s) au {d:%d/%m/%Y}\n" + "\n".join(f"{k} : {v}" for k, v in st.items()))

        self.app.tache("Rapprochement Sage", lambda: reco.rapprocher(self.db, self.user, self.sage, d), fini)

    def retro(self):
        self.app.tache("Controle des ecritures retroactives", lambda: reco.verifier_retroactivite(self.db, self.user, self.sage),
                       lambda a: (self.charger(), info("Aucune modification retroactive detectee." if not a else
                                                       "\n".join(x["message"] for x in a), "Retroactivite")))

    def valider(self):
        r = self.t.selection()
        if r and self.app.action(reco.valider_fiche, self.db, self.user, r["id"]) is None:
            self.charger()

    def option_a(self):
        x = self.te.selection()
        if not x:
            return erreur("Selectionner un ecart de type SAGE_ABSENT_ERP.")
        motif = demander_texte(self, "Reprise d'ecriture Sage", "Motif de la reprise (justification comptable) :")
        if not motif:
            return
        just = demander_texte(self, "Justificatif", "Reference du justificatif (facultatif) :", obligatoire=False) or ""
        if self.app.action(reco.reprendre_ecriture_sage, self.db, self.user, x["id"], motif, just):
            info("Ecriture reprise comme mouvement complementaire lie a l'identifiant Sage (aucune ecriture creee "
                 "dans Sage). Relancez le rapprochement pour valider la fiche.")
            self.lancer()

    def resoudre(self, decision):
        x = self.te.selection()
        if not x:
            return erreur("Selectionner un ecart.")
        motif = demander_texte(self, "Decision", "Motif / analyse :")
        if motif and self.app.action(reco.resoudre_ecart, self.db, self.user, x["id"], decision, motif) is None:
            self.detail(self.t.selection())


# =====================================================================================
class Solvabilite(Page):
    titre = "Solvabilite / Bon de commande"
    sous_titre = "Avis documente avant signature (aucune signature automatique dans Sage)"

    def construire(self):
        b = barre(self)
        self.bc = champ(b, "Numero de BC (abrege ou complet)", 220)
        self.bc.bind("<Return>", lambda e: self.controler())
        ok, m = self.autorise("solvabilite")
        bouton(b, "Controler", self.controler, actif=ok, motif=m).pack(side="left", pady=(16, 0))
        ok, m = self.autorise("derogation")
        bouton(b, "Enregistrer une derogation", self.derogation, couleur=ORANGE, actif=ok, motif=m).pack(
            side="left", padx=6, pady=(16, 0))
        self.res = ctk.CTkTextbox(self, height=230, font=ctk.CTkFont(family="Consolas", size=12))
        self.res.pack(fill="x", padx=14, pady=6)
        self.res.insert("end", "Saisir un numero de bon de commande.\n\nLa formule de risque est celle de Sage "
                               "(Informations client > Solvabilite) ; tant qu'elle n'est pas verifiee sur l'installation "
                               "reelle, l'avis est DONNEES_INSUFFISANTES.")
        self.res.configure(state="disabled")
        self.t = Table(self, [("id", "N°", 50, "e"), ("le", "Le", 140, "w"), ("bc", "BC", 100, "w"), ("ct", "Client", 80, "w"),
                              ("mt", "Montant BC", 110, "e"), ("pl", "Plafond", 110, "e"), ("rp", "Risque projete", 120, "e"),
                              ("v", "Versement", 100, "e"), ("avis", "Avis", 170, "w"), ("par", "Par", 90, "w")], height=10)
        self.t.pack(fill="both", expand=True, padx=14, pady=4)
        self.dernier = None
        self.charger()

    def charger(self):
        self.t.remplir(solvency.historique(self.db), lambda r: (r["id"], r["controle_le"], r["bc_reference"], r["ct_num"] or "",
                                                                fmt_fcfa(r["montant_bc"]), fmt_fcfa(r["plafond"]),
                                                                fmt_fcfa(r["risque_projete"]), fmt_fcfa(r["versement_necessaire"]),
                                                                r["avis"], r["controle_par"]), tag=lambda r: r["avis"])

    def controler(self):
        ref = self.bc.get().strip()
        if not ref:
            return erreur("Saisir un numero de BC.")
        self.app.tache("Controle de solvabilite",
                       lambda: solvency.controler_bc(self.db, self.user, self.sage, ref, self.cfg["solvabilite"]), self.afficher)

    def afficher(self, a):
        self.dernier = a
        nom = self.db.scalar("SELECT intitule FROM clients WHERE ct_num=?", (a.ct_num,), "") if a.ct_num else ""
        inc = {True: "oui (non rajoute)", False: "non (ajoute)", None: "inconnu"}[a.bc_deja_inclus]
        txt = (f"AVIS : {a.avis}\n\nBC : {a.bc}    Client : {a.ct_num or '-'} {nom}\n"
               f"Montant du BC          : {fmt_fcfa(a.montant_bc)}\n"
               f"Plafond / encours aut. : {fmt_fcfa(a.plafond)}\n"
               f"Risque Sage actuel     : {fmt_fcfa(a.risque_sage)}   BC deja inclus : {inc}\n"
               f"Risque projete         : {fmt_fcfa(a.risque_projete)}\n"
               f"Depassement            : {fmt_fcfa(a.depassement)}\n"
               f"Versement necessaire   : {fmt_fcfa(a.versement_necessaire)}\n"
               f"Factures echues        : {len(a.factures_echues)}\n\nMotifs :\n - " + "\n - ".join(a.motifs))
        self.res.configure(state="normal")
        self.res.delete("1.0", "end")
        self.res.insert("end", txt)
        self.res.configure(state="disabled")
        self.charger()

    def derogation(self):
        if not self.dernier or not self.dernier.check_id:
            return erreur("Effectuer d'abord un controle.")
        motif = demander_texte(self, "Derogation", "Motif de la derogation :")
        if motif and self.app.action(solvency.enregistrer_derogation, self.db, self.user, self.dernier.check_id, motif) is None:
            info("Derogation enregistree dans le journal d'audit.")


# =====================================================================================
class Pointage(Page):
    titre = "Pointage client"
    sous_titre = "Confirmation contradictoire du solde (distinct du rapprochement Sage)"

    def construire(self):
        b = barre(self)
        self.ct = champ(b, "Code tiers", 100)
        self.d = champ(b, "Date d'arrete", 110, date.today().strftime("%d/%m/%Y"))
        self.solde = champ(b, "Solde communique par le client", 160)
        self.inter = champ(b, "Interlocuteur", 170)
        f = ctk.CTkFrame(b, fg_color="transparent")
        f.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(f, text="Canal", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.canal = ctk.CTkComboBox(f, values=["TELEPHONE", "WHATSAPP", "TELEGRAM", "VISITE", "COURRIER"], width=130)
        self.canal.pack()
        ok, m = self.autorise("pointage")
        bouton(b, "Enregistrer", self.enregistrer, couleur=VERT, actif=ok, motif=m, width=110).pack(side="left", pady=(16, 0))
        b2 = barre(self)
        bouton(b2, "Historique du client", self.historique, width=150).pack(side="left")
        bouton(b2, "Extrait grand livre Sage (PDF)", self.grand_livre, couleur="#455A64").pack(side="left", padx=6)
        self.lbl = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl.pack(fill="x", padx=16)
        self.th = Table(self, [("id", "N°", 50, "e"), ("d", "Arrete", 90, "w"), ("sc", "Solde client", 110, "e"),
                               ("ss", "Solde Sage", 110, "e"), ("ec", "Ecart", 100, "e"), ("i", "Interlocuteur", 160, "w"),
                               ("c", "Canal", 90, "w"), ("st", "Statut", 160, "w"), ("le", "Le", 140, "w"),
                               ("al", "Alerte retro.", 90, "center")], height=5, on_select=self.lignes)
        self.th.pack(fill="x", padx=14, pady=4)
        self.tl = Table(self, [("d", "Date", 90, "w"), ("p", "Piece", 110, "w"), ("l", "Libelle", 280, "w"),
                               ("dc", "Debit", 100, "e"), ("cr", "Credit", 100, "e"), ("st", "Statut", 130, "w"),
                               ("c", "Commentaire", 260, "w")], height=9)
        self.tl.pack(fill="both", expand=True, padx=14, pady=4)
        a = barre(self)
        for st in ("CONFIRME", "CONTESTE", "MANQUANT", "EN_VERIFICATION"):
            bouton(a, st.replace("_", " ").title(), lambda s=st: self.statut_ligne(s), width=120, actif=ok, motif=m).pack(side="left", padx=(0, 6))
        bouton(a, "Cloturer : solde confirme", lambda: self.cloturer("CONFIRME_PAR_CLIENT"), couleur=VERT, actif=ok, motif=m).pack(side="left", padx=6)
        bouton(a, "Cloturer : conteste", lambda: self.cloturer("CONTESTE"), couleur=ROUGE, actif=ok, motif=m).pack(side="left", padx=6)

    def enregistrer(self):
        try:
            d = _date(self.d.get())
            s = parse_montant(self.solde.get())
            if s is None:
                raise ValueError("Solde communique obligatoire")
        except ValueError as exc:
            return erreur(str(exc))
        ct = self.ct.get().strip()

        def fini(r):
            if r["statut"] == "CONFIRME_PAR_CLIENT":
                self.lbl.configure(text=f"Solde confirme - OK ({fmt_fcfa(r['solde_sage'])} FCFA)", text_color=VERT)
            else:
                self.lbl.configure(text=f"Ecart de {fmt_fcfa(r['ecart'], True)} avec Sage ({fmt_fcfa(r['solde_sage'])}) : "
                                        "pointage detaille ouvert", text_color=ORANGE)
            self.historique()

        self.app.tache("Enregistrement du solde client", lambda: pointing.enregistrer_solde_client(
            self.db, self.user, self.sage, ct, d, s, self.inter.get(), self.canal.get()), fini)

    def historique(self):
        ct = self.ct.get().strip()
        self.th.remplir(pointing.historique(self.db, ct), lambda r: (
            r["id"], _fd(r["date_arrete"]), fmt_fcfa(r["solde_client"]), fmt_fcfa(r["solde_sage"]), fmt_fcfa(r["ecart"], True),
            r["interlocuteur"], r["canal"] or "", r["statut"], r["enregistre_le"], "OUI" if r["alerte_retroactive"] else ""),
            tag=lambda r: r["statut"])
        self.tl.remplir([], lambda r: r)

    def lignes(self, c):
        if c:
            self.tl.remplir(pointing.lignes(self.db, c["id"]), lambda r: (
                _fd(r["date_ecriture"]), r["piece"], r["libelle"], fmt_fcfa(r["montant"]) if r["sens"] == "D" else "",
                fmt_fcfa(r["montant"]) if r["sens"] == "C" else "", r["statut"], r["commentaire"] or ""),
                tag=lambda r: {"CONTESTE": "BLOQUE", "MANQUANT": "ECART_A_ANALYSER", "CONFIRME": "VALIDE"}.get(r["statut"]))

    def statut_ligne(self, st):
        l = self.tl.selection()
        if not l:
            return erreur("Selectionner une ligne de pointage.")
        com = demander_texte(self, "Commentaire", "Commentaire (facultatif) :", obligatoire=False) or ""
        self.app.action(pointing.maj_ligne, self.db, self.user, l["id"], st, com)
        self.lignes(self.th.selection())

    def cloturer(self, st):
        c = self.th.selection()
        if c and self.app.action(pointing.cloturer, self.db, self.user, c["id"], st) is None:
            self.historique()

    def grand_livre(self):
        ct = self.ct.get().strip()
        nom = self.db.scalar("SELECT intitule FROM clients WHERE ct_num=?", (ct,))
        if not nom:
            return erreur("Code tiers inconnu.")
        try:
            d = _date(self.d.get())
        except ValueError as exc:
            return erreur(str(exc))
        dest = self.ctx.data_dir / "exports" / f"GRAND_LIVRE_{ct}_{d:%Y%m%d}.pdf"
        self.app.tache("Extrait du grand livre Sage",
                       lambda: docs.extrait_grand_livre_pdf(self.sage, ct, nom, d, dest, self.cfg["societe"]),
                       lambda p: docs.ouvrir_fichier(p))


# =====================================================================================
class Documents(Page):
    titre = "Documents / Communications"
    sous_titre = "Factures PDF, exports, partage assiste"

    def construire(self):
        b = barre(self)
        self.piece = champ(b, "Numero de piece", 160)
        bouton(b, "Rechercher le PDF", self.rechercher, width=140).pack(side="left", pady=(16, 0))
        dossiers = self.cfg["documents"].get("dossiers_pdf") or []
        bouton(b, "Indexer les dossiers PDF", self.indexer, couleur="#455A64", actif=bool(dossiers),
               motif="Aucun dossier PDF configure (Parametres > documents.dossiers_pdf)").pack(side="left", padx=6, pady=(16, 0))
        self.lbl = ctk.CTkLabel(self, text="", anchor="w", justify="left")
        self.lbl.pack(fill="x", padx=16, pady=6)
        a = barre(self)
        for txt, fn in [("Ouvrir PDF", self.ouvrir), ("Exporter copie", self.exporter), ("Copier numero", self.copier),
                        ("Preparer envoi WhatsApp", lambda: self.envoi("WHATSAPP")),
                        ("Preparer envoi Telegram", lambda: self.envoi("TELEGRAM"))]:
            bouton(a, txt, fn, width=150).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(self, text=(
            "Strategie PDF : la liaison Sage <-> PDF n'est pas encore inventoriee sur l'installation. L'application indexe "
            "les dossiers configures (nom de fichier contenant le numero de piece) et interrogera l'adaptateur Sage des que "
            "la source reelle sera connue. Aucun document n'est genere a la place d'une facture absente."),
            wraplength=1000, justify="left", text_color="#555").pack(fill="x", padx=16, pady=10)
        self.t = Table(self, [("p", "Piece", 120, "w"), ("c", "Chemin", 700, "w"), ("s", "Source", 120, "w"),
                              ("le", "Indexe le", 140, "w")], height=12,
                       on_select=lambda r: r and (self.piece.delete(0, "end"), self.piece.insert(0, r["piece"])))
        self.t.pack(fill="both", expand=True, padx=14, pady=4)
        self.chemin = None
        self.charger()

    def charger(self):
        self.t.remplir(self.db.query("SELECT * FROM invoice_pdf_links ORDER BY piece LIMIT 2000"),
                       lambda r: (r["piece"], r["chemin"], r["source"], r["indexe_le"]))

    def indexer(self):
        self.app.tache("Indexation des PDF", lambda: docs.indexer_dossiers(self.db, self.cfg["documents"]["dossiers_pdf"]),
                       lambda n: (self.charger(), info(f"{n} reference(s) indexee(s).")))

    def rechercher(self):
        try:
            self.chemin = docs.trouver_pdf(self.db, self.sage, self.piece.get())
            self.lbl.configure(text=f"PDF trouve : {self.chemin}", text_color=VERT)
        except docs.PdfIntrouvable as exc:
            self.chemin = None
            self.lbl.configure(text=str(exc), text_color=ROUGE)
        return self.chemin

    def ouvrir(self):
        if self.rechercher():
            docs.ouvrir_fichier(self.chemin)

    def exporter(self):
        if self.rechercher():
            dossier = self.cfg["documents"].get("dossier_export") or str(self.ctx.data_dir / "exports")
            info(f"Copie exportee : {docs.exporter_copie(self.db, self.user, self.chemin, dossier)}")

    def copier(self):
        self.clipboard_clear()
        self.clipboard_append(self.piece.get().strip())

    def envoi(self, canal):
        piece = self.piece.get().strip()
        ct = self.db.scalar("SELECT ct_num FROM normalized_movements WHERE reference_piece=? AND statut<>'ANNULE' LIMIT 1",
                            (piece,))
        if not ct:
            return erreur("Piece inconnue dans les fiches : impossible d'identifier le client destinataire.")
        preparer_envoi(self, canal, ct, piece, None)


# =====================================================================================
class Impressions(Page):
    titre = "Impressions"
    sous_titre = "Fiches A4 recto verso - impression differee et groupee"

    def construire(self):
        lpp = printing.lignes_par_page(self.cfg["impression"])
        ctk.CTkLabel(self, text=(f"Modele PROVISOIRE ({lpp} lignes par page) en attendant les scans de la fiche papier reelle. "
                                 "Chaque client commence sur une nouvelle feuille. Pour le recto verso, choisir "
                                 "'Recto verso - bord long' dans la boite d'impression."),
                     wraplength=1050, justify="left", text_color="#555").pack(fill="x", padx=16, pady=6)
        b = barre(self)
        ok, m = self.autorise("impression")
        bouton(b, "Generer la selection", lambda: self.generer(False), actif=ok, motif=m).pack(side="left")
        bouton(b, "Generer tout (zone puis nom)", lambda: self.generer(True), actif=ok, motif=m).pack(side="left", padx=6)
        bouton(b, "Generer les fiches pleines (recto verso)", self.generer_pleines, actif=ok, motif=m).pack(side="left", padx=6)
        self.tq = Table(self, [("ct", "Code", 80, "w"), ("nom", "Client", 250, "w"), ("z", "Zone", 120, "w"),
                               ("n", "Lignes en attente", 120, "e"), ("p", "Recto verso plein", 120, "center"),
                               ("old", "Plus ancienne", 110, "w"), ("r", "Retroactif", 90, "center")],
                        height=9, selectmode="extended")
        self.tq.pack(fill="both", expand=True, padx=14, pady=4)
        ctk.CTkLabel(self, text="Registre des impressions", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16)
        self.tr = Table(self, [("job", "Job", 50, "e"), ("ct", "Code", 80, "w"), ("nom", "Client", 200, "w"),
                               ("per", "Periode", 180, "w"), ("rep", "Solde reporte", 110, "e"), ("fin", "Solde final", 110, "e"),
                               ("pg", "Pages", 60, "e"), ("v", "Version", 60, "e"), ("st", "Statut", 90, "w"),
                               ("le", "Le", 140, "w"), ("par", "Par", 90, "w")], height=8)
        self.tr.pack(fill="both", expand=True, padx=14, pady=4)
        a = barre(self)
        bouton(a, "Ouvrir / apercu du job", self.ouvrir, width=160).pack(side="left")
        bouton(a, "Imprimer (Windows)", self.imprimer, width=150, actif=sys.platform.startswith("win"),
               motif="Impression directe disponible uniquement sous Windows").pack(side="left", padx=6)
        bouton(a, "Confirmer l'impression", self.confirmer, couleur=VERT, width=170, actif=ok, motif=m).pack(side="left", padx=6)
        bouton(a, "Annuler le job (reimprimer)", self.annuler, couleur=ROUGE, width=190, actif=ok, motif=m).pack(side="left", padx=6)
        self.charger()

    def charger(self):
        self.q = printing.file_attente(self.db, self.cfg["impression"])
        self.tq.remplir(self.q, lambda x: (x["ct_num"], x["intitule"], x["zone"] or "", x["nb_lignes"],
                                           "OUI" if x["pret_recto_verso"] else "", _fd(x["plus_ancienne"]),
                                           "OUI" if x["retroactif"] else ""))
        self.tr.remplir(printing.registre(self.db), lambda r: (
            r["job_id"], r["ct_num"], r["intitule"], f"{_fd(r['periode_debut'])} - {_fd(r['periode_fin'])}",
            fmt_fcfa(r["solde_reporte"]), fmt_fcfa(r["solde_final"]), r["nb_pages"], r["version"], r["statut"],
            r["imprime_le"], r["imprime_par"]))

    def _gen(self, cts):
        if not cts:
            return erreur("Aucun client selectionne / en attente.")
        dest = self.ctx.data_dir / "impressions" / f"FICHES_{datetime.now():%Y%m%d_%H%M%S}.pdf"

        def fini(r):
            self.charger()
            if confirmer(f"{r['clients']} fiche(s), {r['pages']} page(s) generee(s).\n{r['fichier']}\n\nOuvrir l'apercu ?"):
                docs.ouvrir_fichier(r["fichier"])

        self.app.tache("Generation des fiches", lambda: printing.generer_fiches(self.db, self.user, cts, dest, self.cfg), fini)

    def generer(self, tout):
        self._gen([x["ct_num"] for x in (self.q if tout else self.tq.selections())])

    def generer_pleines(self):
        self._gen([x["ct_num"] for x in self.q if x["pret_recto_verso"]])

    def _job(self):
        r = self.tr.selection()
        if not r:
            erreur("Selectionner une ligne du registre.")
        return r

    def ouvrir(self):
        r = self._job()
        if r:
            f = self.db.scalar("SELECT fichier_pdf FROM print_jobs WHERE id=?", (r["job_id"],))
            if f and Path(f).exists():
                docs.ouvrir_fichier(f)
            else:
                erreur(f"Fichier introuvable : {f}")

    def imprimer(self):
        r = self._job()
        if r:
            docs.ouvrir_fichier(self.db.scalar("SELECT fichier_pdf FROM print_jobs WHERE id=?", (r["job_id"],)), imprimer=True)

    def confirmer(self):
        r = self._job()
        if r and confirmer("Confirmer que ce job a ete correctement imprime (recto verso) ?"):
            printing.confirmer_impression(self.db, self.user, r["job_id"])
            self.charger()

    def annuler(self):
        r = self._job()
        if r:
            motif = demander_texte(self, "Annulation", "Motif (ex. bourrage, mauvais papier) :")
            if motif:
                printing.annuler_job(self.db, self.user, r["job_id"], motif)
                self.charger()


# =====================================================================================
class Parametres(Page):
    titre = "Parametres / Administration"

    def construire(self):
        admin = self.user.peut("parametres")
        b = barre(self)
        s = self.cfg["sage"]
        f = ctk.CTkFrame(b, fg_color="transparent")
        f.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(f, text="Mode Sage", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.mode = ctk.CTkComboBox(f, values=["demo", "sql"], width=100)
        self.mode.set(s["mode"])
        self.mode.pack()
        self.server = champ(b, "Serveur SQL", 180, s["server"])
        self.bc = champ(b, "Base Comptabilite", 150, s["database_compta"])
        self.bg = champ(b, "Base Gestion commerciale", 150, s["database_gescom"])
        bouton(b, "Enregistrer", self.enregistrer, actif=admin, motif="Reserve a l'administrateur", width=110).pack(side="left", pady=(16, 0))
        b2 = barre(self)
        bouton(b2, "Tester la connexion Sage", self.tester).pack(side="left")
        ok = self.user.peut("sauvegarde")
        bouton(b2, "Sauvegarder la base", self.sauvegarder, actif=ok, motif="Reserve responsable/admin").pack(side="left", padx=6)
        bouton(b2, "Restaurer une sauvegarde...", self.restaurer, couleur=ROUGE, actif=admin, motif="Reserve a l'administrateur").pack(side="left", padx=6)
        bouton(b2, "Ouvrir le dossier de donnees", lambda: docs.ouvrir_fichier(self.ctx.data_dir), couleur="#455A64").pack(side="left", padx=6)
        self.diag = ctk.CTkTextbox(self, height=170, font=ctk.CTkFont(family="Consolas", size=11))
        self.diag.pack(fill="x", padx=14, pady=6)
        self.diagnostic()
        ctk.CTkLabel(self, text="Journal d'audit (200 derniers evenements)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16)
        t = Table(self, [("le", "Horodatage", 150, "w"), ("u", "Utilisateur", 110, "w"), ("a", "Action", 220, "w"),
                         ("o", "Objet", 140, "w"), ("d", "Details", 600, "w")], height=10)
        t.pack(fill="both", expand=True, padx=14, pady=4)
        t.remplir(self.db.query("SELECT * FROM audit_events ORDER BY id DESC LIMIT 200"),
                  lambda r: (r["horodatage"], r["utilisateur"], r["action"], r["objet"] or "", (r["details"] or "")[:200]))

    def diagnostic(self):
        db = self.db
        lignes = [
            f"Version application : {__version__}    Python {platform.python_version()}    {platform.platform()}",
            f"Configuration : {self.cfg['_path']}",
            f"Base locale : {self.ctx.db_path}",
            f"Migrations : {', '.join(r[0] for r in db.query('SELECT nom FROM schema_migrations ORDER BY version'))}",
            f"Adaptateur Sage : {self.sage.nom}  (demo : {getattr(self.sage, 'est_demo', False)})",
            f"Clients : {db.scalar('SELECT COUNT(*) FROM clients', default=0)}   Mouvements : "
            f"{db.scalar('SELECT COUNT(*) FROM normalized_movements', default=0)}   Lots : "
            f"{db.scalar('SELECT COUNT(*) FROM import_batches', default=0)}",
            f"Integrite SQLite : {db.scalar('PRAGMA integrity_check')}",
            "Regles du rapport (provisoires) : " + json.dumps(self.cfg["rapport"]["types_documents"], ensure_ascii=False),
        ]
        self.diag.delete("1.0", "end")
        self.diag.insert("end", "\n".join(lignes))

    def enregistrer(self):
        from ..config import save_config
        s = self.cfg["sage"]
        s.update(mode=self.mode.get(), server=self.server.get().strip(), database_compta=self.bc.get().strip(),
                 database_gescom=self.bg.get().strip())
        p = save_config(self.cfg)
        self.db.audit(self.user.login, "PARAMETRES_SAGE", str(p), {k: s[k] for k in ("mode", "server", "database_compta",
                                                                                      "database_gescom")})
        self.ctx.recharger_sage()
        self.app.maj_bandeau()
        info(f"Parametres enregistres dans {p}")
        self.diagnostic()

    def tester(self):
        self.app.tache("Test de connexion Sage", self.sage.ping, lambda _r: info(f"Connexion reussie : {self.sage.nom}"),
                       lambda e: erreur(f"Connexion impossible : {e}"))

    def sauvegarder(self):
        dest = self.ctx.data_dir / "sauvegardes" / f"gtc_compta_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
        self.db.backup(dest)
        self.db.audit(self.user.login, "SAUVEGARDE", str(dest))
        info(f"Sauvegarde creee :\n{dest}")

    def restaurer(self):
        p = filedialog.askopenfilename(title="Sauvegarde a restaurer", initialdir=self.ctx.data_dir / "sauvegardes",
                                       filetypes=[("Base SQLite", "*.sqlite3")])
        if not p or not confirmer("La base actuelle sera remplacee (une sauvegarde de securite est faite avant). "
                                  "L'application devra etre redemarree. Continuer ?"):
            return
        from ..db import Database
        secu = self.ctx.data_dir / "sauvegardes" / f"avant_restauration_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
        self.db.backup(secu)
        self.db.close()
        try:
            Database.restore(p, self.ctx.db_path)
        except ValueError as exc:
            erreur(str(exc))
        info("Restauration effectuee. L'application va se fermer : relancez-la.")
        self.app.destroy()


PAGES = {"accueil": Accueil, "clients": Clients, "import": Import, "fiches": Fiches, "rapprochement": Rapprochement,
         "solvabilite": Solvabilite, "pointage": Pointage, "documents": Documents, "impressions": Impressions,
         "parametres": Parametres}

_ = (SageIndisponible, normaliser)  # reexports utiles aux extensions
