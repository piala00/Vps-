import re
import unicodedata


def normaliser(texte) -> str:
    """Majuscules, sans accents, espaces compactes (comparaison de libelles)."""
    if texte is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texte))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def normaliser_reference(ref) -> str:
    """Reference de piece comparable : majuscules, sans espaces ni separateurs."""
    return re.sub(r"[\s\-_/.]", "", normaliser(ref))
