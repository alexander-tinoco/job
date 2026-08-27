import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Turn a title into a URL-safe slug.

    Accents are folded rather than dropped so "Diseñador Gráfico" becomes
    "disenador-grafico" instead of "dise-ador-gr-fico".
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_ALNUM.sub("-", ascii_only).strip("-") or "opening"
