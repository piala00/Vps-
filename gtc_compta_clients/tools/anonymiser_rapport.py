"""Produit une copie ANONYMISEE de feuilles du rapport commercial (jeu de test).
Remplace les noms de clients (colonne D des pieces et recus) et les noms d'acheteurs /
agents (colonne E) par des pseudonymes stables ; conserve la structure, les numeros de
pieces et les montants (necessaires aux controles de totaux).
Usage : python tools/anonymiser_rapport.py RAPPORT.xlsx SORTIE.xlsx 01,03,12,14"""
import re
import sys
import unicodedata

from openpyxl import Workbook, load_workbook

GARDER_D = {"CLIENTS DETAILS BTA", "COMPTE DE LIAISON"}
GARDER_E = re.compile(r"^(EN COMPTE( \d+)?|COMPTANT|ANNULEE?)$")
PIECE = re.compile(r"^\d*[A-Z]{2,5}\d")


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
        for row in wb[n].iter_rows(values_only=True):
            row = list(row[:9])
            c = str(row[2] or "").replace(" ", "")
            if len(row) > 4 and PIECE.match(c):
                if row[3] and norm(row[3]) not in GARDER_D and not re.search(r"VERSEMENT|CAISSE|LIAISON", norm(row[3])):
                    row[3] = pseudo(clients, "CLIENT", row[3])
                e = norm(row[4]) if row[4] else ""
                if e and not GARDER_E.match(e):
                    m = re.match(r"^(BP|CASH)\s*/", e)
                    row[4] = f"{m.group(1)}/AGENT {pseudo(autres, '', e).strip()}" if m else pseudo(autres, "ACHETEUR", e)
            ws.append(row)
    out.save(dest)
    print(f"{dest} : {len(clients)} clients et {len(autres)} references pseudonymises")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(","))
