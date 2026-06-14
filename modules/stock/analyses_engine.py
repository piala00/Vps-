#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/stock/analyses_engine.py
NEXORA v2.0 — Moteur d'analyses BI du module Stock
Toutes les fonctions travaillent sur une liste de mouvements Sage
(voir core.sage_connector.get_mouvements) :
DL_MvtStock=1 (entree) / DL_MvtStock=3 (sortie)
"""
from datetime import date, timedelta
from typing import List, Dict, Optional


def kpis(mvts):
    total_e = sum(float(m.get("entree") or 0) for m in mvts)
    total_s = sum(float(m.get("sortie") or 0) for m in mvts)
    ca = sum(float(m.get("montant_ht") or 0) for m in mvts)
    arts = set(m.get("code_article", "") for m in mvts if m.get("code_article"))
    arts_s = set(m.get("code_article", "") for m in mvts if float(m.get("sortie") or 0) > 0)
    clients = set(m.get("code_client", "") for m in mvts if m.get("code_client"))
    pieces = set(m.get("no_piece", "") for m in mvts if m.get("no_piece"))
    return {
        "total_entrees": round(total_e, 2), "total_sorties": round(total_s, 2),
        "montant_total": round(ca, 2), "nb_articles": len(arts),
        "nb_articles_sortis": len(arts_s), "nb_clients": len(clients),
        "nb_pieces": len(pieces), "nb_mouvements": len(mvts),
    }


def top_articles(mvts, limit=20):
    t = {}
    for m in mvts:
        code = m.get("code_article", "")
        if not code:
            continue
        if code not in t:
            t[code] = {"code_article": code, "designation": m.get("designation", ""),
                       "famille": m.get("famille", ""), "volume_sortie": 0,
                       "volume_entree": 0, "montant_ht": 0, "nb_mouvements": 0,
                       "nb_clients": set(), "nb_pieces": set(), "derniere_sortie": None}
        r = t[code]
        s = float(m.get("sortie") or 0)
        e = float(m.get("entree") or 0)
        r["volume_sortie"] += s
        r["volume_entree"] += e
        r["montant_ht"] += float(m.get("montant_ht") or 0)
        r["nb_mouvements"] += 1
        if m.get("code_client"):
            r["nb_clients"].add(m["code_client"])
        if m.get("no_piece"):
            r["nb_pieces"].add(m["no_piece"])
        if s > 0:
            d = str(m.get("date_mvt", ""))[:10]
            if not r["derniere_sortie"] or d > r["derniere_sortie"]:
                r["derniere_sortie"] = d
    result = []
    for r in t.values():
        r["nb_clients"] = len(r["nb_clients"])
        r["nb_pieces"] = len(r["nb_pieces"])
        r["volume_sortie"] = round(r["volume_sortie"], 2)
        r["volume_entree"] = round(r["volume_entree"], 2)
        r["montant_ht"] = round(r["montant_ht"], 2)
        result.append(r)
    result.sort(key=lambda x: x["volume_sortie"], reverse=True)
    return result[:limit]


def stocks_dormants(mvts, jours=60):
    arts = {}
    today = date.today()
    for m in mvts:
        code = m.get("code_article", "")
        if not code:
            continue
        if code not in arts:
            arts[code] = {"code_article": code, "designation": m.get("designation", ""),
                          "famille": m.get("famille", ""), "stock_actuel": 0,
                          "derniere_sortie": None, "vol_sortie": 0}
        a = arts[code]
        a["stock_actuel"] += float(m.get("entree") or 0) - float(m.get("sortie") or 0)
        s = float(m.get("sortie") or 0)
        a["vol_sortie"] += s
        if s > 0:
            d = str(m.get("date_mvt", ""))[:10]
            if not a["derniere_sortie"] or d > a["derniere_sortie"]:
                a["derniere_sortie"] = d
    result = []
    for a in arts.values():
        if a["stock_actuel"] <= 0:
            continue
        if a["derniere_sortie"]:
            try:
                j = (today - date.fromisoformat(a["derniere_sortie"])).days
            except (ValueError, TypeError):
                j = 9999
        else:
            j = 9999
        if j < jours:
            continue
        a["jours_sans_mvt"] = j
        a["statut"] = "DORMANT" if j >= jours * 2 else "A SURVEILLER"
        if a["vol_sortie"] <= 0:
            a["cause"] = "Jamais sorti - demande inexistante"
            a["action"] = "Arret achat ou liquidation"
        elif j >= 90:
            a["cause"] = "Sortie ancienne - article a relancer"
            a["action"] = "Relancer commercialement"
        else:
            a["cause"] = "Faible rotation sur la periode"
            a["action"] = "Reduire les achats"
        a["stock_actuel"] = round(a["stock_actuel"], 2)
        result.append(a)
    result.sort(key=lambda x: x["jours_sans_mvt"], reverse=True)
    return result


def besoins_reappro(mvts, semaines=4):
    today = date.today()
    dr = today - timedelta(weeks=semaines)
    stock = {}
    sorties_rec = {}
    for m in mvts:
        code = m.get("code_article", "")
        if not code:
            continue
        if code not in stock:
            stock[code] = {"code_article": code, "designation": m.get("designation", ""),
                          "famille": m.get("famille", ""), "stock_actuel": 0}
        stock[code]["stock_actuel"] += float(m.get("entree") or 0) - float(m.get("sortie") or 0)
        d = str(m.get("date_mvt", ""))[:10]
        try:
            if date.fromisoformat(d) >= dr:
                sorties_rec[code] = sorties_rec.get(code, 0) + float(m.get("sortie") or 0)
        except (ValueError, TypeError):
            pass
    result = []
    for code, s in stock.items():
        vol = sorties_rec.get(code, 0)
        sa = max(0, s["stock_actuel"])
        besoin = max(0, vol - sa)
        if sa <= 0 and vol > 0:
            prio = "CRITIQUE"
        elif besoin > 0:
            prio = "URGENT"
        elif vol > 0 and sa > vol * 3:
            prio = "SURSTOCK"
        elif vol <= 0 and sa > 0:
            prio = "DORMANT"
        else:
            prio = "NORMAL"
        cov = round(sa / vol, 1) if vol > 0 else None
        result.append({"code_article": code, "designation": s["designation"],
                        "famille": s["famille"], "stock_actuel": round(sa, 2),
                        "vol_sortie_ref": round(vol, 2), "besoin_appro": round(besoin, 2),
                        "couverture": cov, "priorite": prio})
    ordre = {"CRITIQUE": 0, "URGENT": 1, "NORMAL": 2, "SURSTOCK": 3, "DORMANT": 4}
    result.sort(key=lambda x: (ordre.get(x["priorite"], 9), -x["besoin_appro"]))
    return result


def consommation_clients(mvts, code_article=None):
    clients = {}
    today = date.today()
    for m in mvts:
        if float(m.get("sortie") or 0) <= 0:
            continue
        art = m.get("code_article", "")
        if code_article and art != code_article:
            continue
        code = m.get("code_client", "") or "COMPTANT"
        key = (code, art if code_article else "ALL")
        if key not in clients:
            clients[key] = {"code_client": code,
                            "client_nom": m.get("client_nom", "") or "Client comptant",
                            "code_article": art, "designation": m.get("designation", ""),
                            "qte_totale": 0, "montant_ht": 0, "nb_commandes": set(),
                            "premiere_cmd": None, "derniere_cmd": None}
        c = clients[key]
        c["qte_totale"] += float(m.get("sortie") or 0)
        c["montant_ht"] += float(m.get("montant_ht") or 0)
        if m.get("no_piece"):
            c["nb_commandes"].add(m["no_piece"])
        d = str(m.get("date_mvt", ""))[:10]
        if d:
            if not c["premiere_cmd"] or d < c["premiere_cmd"]:
                c["premiere_cmd"] = d
            if not c["derniere_cmd"] or d > c["derniere_cmd"]:
                c["derniere_cmd"] = d
    result = []
    for c in clients.values():
        nb = len(c["nb_commandes"])
        c["nb_commandes"] = nb
        freq = None
        if nb >= 2 and c["premiere_cmd"] and c["derniere_cmd"]:
            try:
                j = (date.fromisoformat(c["derniere_cmd"]) - date.fromisoformat(c["premiere_cmd"])).days
                freq = round(j / (nb - 1), 0) if nb > 1 else None
            except (ValueError, TypeError):
                pass
        c["frequence_jours"] = freq
        if freq and c["derniere_cmd"]:
            try:
                p = date.fromisoformat(c["derniere_cmd"]) + timedelta(days=int(freq))
                c["prochaine_cmd"] = p.isoformat()
                c["jours_restants"] = (p - today).days
            except (ValueError, TypeError):
                c["prochaine_cmd"] = None
                c["jours_restants"] = None
        else:
            c["prochaine_cmd"] = None
            c["jours_restants"] = None
        c["qte_totale"] = round(c["qte_totale"], 2)
        c["montant_ht"] = round(c["montant_ht"], 2)
        result.append(c)
    result.sort(key=lambda x: x["qte_totale"], reverse=True)
    return result


GRANULARITES = ("jour", "semaine", "mois", "trimestre")


def periode_label(d, granularite="mois"):
    try:
        dt = date.fromisoformat(str(d)[:10])
    except (ValueError, TypeError):
        return ""
    if granularite == "jour":
        return dt.isoformat()
    if granularite == "semaine":
        y, w, _ = dt.isocalendar()
        return "%s-S%02d" % (y, w)
    if granularite == "trimestre":
        return "%s-T%d" % (dt.year, (dt.month - 1) // 3 + 1)
    return dt.strftime("%Y-%m")


def evolution_temporelle(mvts, granularite="mois"):
    if granularite not in GRANULARITES:
        granularite = "mois"
    buckets = {}
    for m in mvts:
        d = str(m.get("date_mvt", ""))[:10]
        cle = periode_label(d, granularite)
        if not cle:
            continue
        if cle not in buckets:
            buckets[cle] = {"periode": cle, "entrees": 0, "sorties": 0, "montant_ht": 0,
                            "nb_mvt": 0, "nb_clients": set(), "nb_pieces": set()}
        t = buckets[cle]
        t["entrees"] += float(m.get("entree") or 0)
        t["sorties"] += float(m.get("sortie") or 0)
        t["montant_ht"] += float(m.get("montant_ht") or 0)
        t["nb_mvt"] += 1
        if m.get("code_client"):
            t["nb_clients"].add(m["code_client"])
        if m.get("no_piece"):
            t["nb_pieces"].add(m["no_piece"])
    result = []
    for t in sorted(buckets.values(), key=lambda x: x["periode"]):
        t["nb_clients"] = len(t["nb_clients"])
        t["nb_pieces"] = len(t["nb_pieces"])
        t["entrees"] = round(t["entrees"], 2)
        t["sorties"] = round(t["sorties"], 2)
        t["montant_ht"] = round(t["montant_ht"], 2)
        result.append(t)
    return result


def evolution_dormants(mvts, jours=60, granularite="mois"):
    """Evolution du nombre et de la quantite d'articles dormants periode par periode."""
    if granularite not in GRANULARITES:
        granularite = "mois"

    def snapshot(arts, ref_date, periode):
        count = 0
        qty = 0.0
        for a in arts.values():
            stock = a["stock_actuel"]
            if stock <= 0:
                continue
            if a["derniere_sortie"]:
                try:
                    j = (date.fromisoformat(ref_date) - date.fromisoformat(a["derniere_sortie"])).days
                except (ValueError, TypeError):
                    j = 9999
            else:
                j = 9999
            if j >= jours:
                count += 1
                qty += stock
        return {"periode": periode, "dormants_count": count, "dormants_qty": round(qty, 2)}

    mvts_tries = sorted((m for m in mvts if str(m.get("date_mvt", ""))[:10]),
                         key=lambda m: str(m.get("date_mvt", ""))[:10])
    arts = {}
    result = []
    bucket_courant = None
    date_fin = None
    for m in mvts_tries:
        d = str(m.get("date_mvt", ""))[:10]
        cle = periode_label(d, granularite)
        if not cle:
            continue
        if bucket_courant is not None and cle != bucket_courant:
            result.append(snapshot(arts, date_fin, bucket_courant))
        bucket_courant = cle
        if date_fin is None or d > date_fin:
            date_fin = d
        code = m.get("code_article", "")
        if not code:
            continue
        if code not in arts:
            arts[code] = {"designation": m.get("designation", ""),
                          "stock_actuel": 0, "derniere_sortie": None}
        a = arts[code]
        a["stock_actuel"] += float(m.get("entree") or 0) - float(m.get("sortie") or 0)
        s = float(m.get("sortie") or 0)
        if s > 0 and (not a["derniere_sortie"] or d > a["derniere_sortie"]):
            a["derniere_sortie"] = d
    if bucket_courant is not None:
        result.append(snapshot(arts, date_fin, bucket_courant))
    return result


def repartition_familles(mvts):
    fams = {}
    for m in mvts:
        if float(m.get("sortie") or 0) <= 0:
            continue
        fam = m.get("famille", "") or "Autre"
        if fam not in fams:
            fams[fam] = {"famille": fam, "volume_sortie": 0, "montant_ht": 0, "nb_articles": set()}
        fams[fam]["volume_sortie"] += float(m.get("sortie") or 0)
        fams[fam]["montant_ht"] += float(m.get("montant_ht") or 0)
        fams[fam]["nb_articles"].add(m.get("code_article", ""))
    total = sum(f["volume_sortie"] for f in fams.values()) or 1
    result = []
    for f in fams.values():
        f["nb_articles"] = len(f["nb_articles"])
        f["part_pct"] = round(f["volume_sortie"] / total * 100, 1)
        f["volume_sortie"] = round(f["volume_sortie"], 2)
        f["montant_ht"] = round(f["montant_ht"], 2)
        result.append(f)
    result.sort(key=lambda x: x["volume_sortie"], reverse=True)
    return result


def equilibre_inter_magasins(mvts):
    """Analyse l'equilibre des stocks entre depots."""
    articles = {}
    for m in mvts:
        code = m.get("code_article", "")
        depot = m.get("depot", "") or "?"
        if not code:
            continue
        key = (code, depot)
        if key not in articles:
            articles[key] = {"code_article": code, "depot": depot,
                             "designation": m.get("designation", ""),
                             "famille": m.get("famille", ""),
                             "stock_actuel": 0, "volume_sortie": 0, "derniere_sortie": None}
        a = articles[key]
        a["stock_actuel"] += float(m.get("entree") or 0) - float(m.get("sortie") or 0)
        s = float(m.get("sortie") or 0)
        a["volume_sortie"] += s
        if s > 0:
            d = str(m.get("date_mvt", ""))[:10]
            if not a["derniere_sortie"] or d > a["derniere_sortie"]:
                a["derniere_sortie"] = d

    par_article = {}
    for (code, depot), a in articles.items():
        if code not in par_article:
            par_article[code] = {"code_article": code, "designation": a["designation"],
                                  "famille": a["famille"], "depots": []}
        sa = max(0, a["stock_actuel"])
        vol = a["volume_sortie"]
        cov = round(sa / vol, 1) if vol > 0 else None
        par_article[code]["depots"].append({
            "depot": depot, "stock": round(sa, 2), "volume_sortie": round(vol, 2),
            "couverture": cov,
            "statut": "MANQUE" if (cov is not None and cov < 0.5) or sa <= 0
                     else "SURPLUS" if (cov is not None and cov > 5 and vol > 0)
                     else "OK"
        })

    result = []
    for art in par_article.values():
        depots = art["depots"]
        manques = [d for d in depots if d["statut"] == "MANQUE"]
        surplus = [d for d in depots if d["statut"] == "SURPLUS"]
        if manques or surplus:
            art["nb_manques"] = len(manques)
            art["nb_surplus"] = len(surplus)
            art["transfert_conseille"] = ""
            if manques and surplus:
                art["transfert_conseille"] = (
                    "Transferer de " + surplus[0]["depot"] + " vers " + manques[0]["depot"])
            result.append(art)
    result.sort(key=lambda x: x["nb_manques"], reverse=True)
    return result


def analyse_comparative(mvts1, mvts2, label1="periode1", label2="periode2"):
    """Compare deux periodes article par article."""
    def aggregate(mvts):
        t = {}
        for m in mvts:
            code = m.get("code_article", "")
            if not code:
                continue
            if code not in t:
                t[code] = {"designation": m.get("designation", ""),
                          "sortie": 0, "entree": 0, "montant": 0}
            t[code]["sortie"] += float(m.get("sortie") or 0)
            t[code]["entree"] += float(m.get("entree") or 0)
            t[code]["montant"] += float(m.get("montant_ht") or 0)
        return t

    a1 = aggregate(mvts1)
    a2 = aggregate(mvts2)
    codes = set(a1) | set(a2)
    result = []
    for code in codes:
        d1 = a1.get(code, {"sortie": 0, "entree": 0, "montant": 0})
        d2 = a2.get(code, {"sortie": 0, "entree": 0, "montant": 0})
        desig = (a1.get(code) or a2.get(code) or {}).get("designation", "")
        s1 = d1["sortie"]
        s2 = d2["sortie"]
        evol = round((s2 - s1) / s1 * 100, 1) if s1 > 0 else (100.0 if s2 > 0 else 0.0)
        result.append({
            "code_article": code, "designation": desig,
            "sortie_periode1": round(s1, 2),
            "sortie_periode2": round(s2, 2),
            "montant_periode1": round(d1["montant"], 2),
            "montant_periode2": round(d2["montant"], 2),
            "evolution_pct": evol,
            "tendance": "HAUSSE" if evol > 5 else "BAISSE" if evol < -5 else "STABLE"
        })
    result.sort(key=lambda x: abs(x["evolution_pct"]), reverse=True)
    return result
