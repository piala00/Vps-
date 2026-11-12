"""Montants en FCFA : stockes en entiers (unites), jamais en flottants."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class MontantInvalide(ValueError):
    pass


_SPACES = re.compile(r"[\s  ']")


def parse_montant(value) -> int | None:
    """Convertit une valeur de cellule Excel en montant entier FCFA.

    Retourne None pour une cellule vide. Leve MontantInvalide si la valeur
    n'est pas interpretable ou comporte des centimes non nuls (cas a signaler).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise MontantInvalide(f"valeur booleenne inattendue : {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        dec = Decimal(repr(value))
    elif isinstance(value, Decimal):
        dec = value
    else:
        text = str(value).strip()
        if not text or text in {"-", "–"}:
            return None
        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative, text = True, text[1:-1]
        text = re.sub(r"(?i)\s*(f\s*cfa|fcfa|xaf|f)$", "", text)
        text = _SPACES.sub("", text)
        if text.startswith("-"):
            negative, text = not negative, text[1:]
        # 1.250.000 (separateur de milliers) vs 1250,50 (decimale)
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
            text = text.replace(".", "")
        elif re.fullmatch(r"\d{1,3}(,\d{3})+", text):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        try:
            dec = Decimal(text)
        except InvalidOperation as exc:
            raise MontantInvalide(f"montant illisible : {value!r}") from exc
        if negative:
            dec = -dec
    rounded = dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if abs(dec - rounded) >= Decimal("0.01"):
        raise MontantInvalide(f"montant avec centimes non nuls : {value!r}")
    return int(rounded)


def fmt_fcfa(amount: int | None, signe: bool = False) -> str:
    if amount is None:
        return ""
    s = f"{abs(int(amount)):,}".replace(",", " ")
    if amount < 0:
        return "-" + s
    return ("+" + s) if signe and amount > 0 else s
