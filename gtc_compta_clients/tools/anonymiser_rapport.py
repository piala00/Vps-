"""Produit une copie ANONYMISEE de feuilles du rapport commercial (jeu de test).
Remplace TOUS les noms (colonne D : clients ; colonne E : acheteurs / agents) a partir de la
ligne 8, sauf les libelles structurels (totaux, versements, en-tetes, comptes conteneurs), par des
pseudonymes stables ; conserve la structure, les numeros de
pieces et les montants (necessaires aux controles de totaux).
Usage : python tools/anonymiser_rapport.py RAPPORT.xlsx SORTIE.xlsx 01,03,12,14"""
import re
import sys
import unicodedata

from openpyxl import Workbook, load_workbook

GARDER_D = {"CLIENTS DETAILS BTA", "COMPTE DE LIAISON"}
GARDER_E = re.compile(r"^(EN COMPTE( \d+)?|COMPTANT|ANNULEE?)$")
PIECE = re.compile(r"^\d*[A-Z]{2,5}\d")
# Libelles structurels conserves (totaux, versements, en-tetes, signatures) : jamais des personnes.
STRUCTUREL = re.compile(r"TOTAL|VERSEMENT|CAISSE|REPORT|SOLDE|RECETTE|ENTREES|OPERATIONS|NOMS ET PRENOMS|"
                        r"REFRENCES|REFERENCES|RECOUVREMENTS|AUTRES|RESPONSABLE|COMMERCIAL|CAISSIER|MONTANT|"
                        r"BON DE COMMANDE|FACTURE")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip().upper()


def main(src, dest, feuilles):
    wb = load_workbook(src, data_only=True, read_only=True)
    out = Workbook()
    out.remove(out.active)
    clients, autres = {}, {}

    def pseudo(table, prefixe, v):
        k = norm(v)
        if k not in table:
            table[k] = f"{prefixe} {len(table) + 1:03d}"
        return table[k]

    for n in feuilles:
        ws = out.create_sheet(n)
        for i, row in enumerate(wb[n].iter_rows(values_only=True), 1):
            row = list(row[:9])
            if i >= 8 and len(row) > 4:
                b = norm(row[1]) if isinstance(row[1], str) else ""
                if (b and not re.match(r"^BC\s*\d", b) and len(b) > 3 and re.search(r"[A-Z]{2}", b)
                        and not STRUCTUREL.search(b)):
                    row[1] = pseudo(autres, "REF", row[1])       # nom ecrit a la place du n° de BC
                d = norm(row[3]) if row[3] else ""
                if d and not STRUCTUREL.search(d) and d not in GARDER_D:
                    if re.match(r"^(ANNULATION|ANNULE|ERREUR|CORRECTION|REGUL)", d):
                        row[3] = d.split()[0] + " (COMMENTAIRE ANONYMISE)"
                    else:
                        row[3] = pseudo(clients, "CLIENT", row[3])
                e = norm(row[4]) if row[4] else ""
                if e and not GARDER_E.match(e) and not STRUCTUREL.search(e):
                    m = re.match(r"^(BP|CASH|COMPTANT)\s*/", e)
                    row[4] = f"{m.group(1)}/AGENT {pseudo(autres, '', e).strip()}" if m else pseudo(autres, "ACHETEUR", e)
            ws.append(row)
    out.save(dest)
    print(f"{dest} : {len(clients)} clients et {len(autres)} references pseudonymises")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(","))
