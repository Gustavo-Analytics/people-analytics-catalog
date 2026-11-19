"""Stage 0.5: interprets the period in the question WITHOUT calling any model.

Resolves "outubro de 2026", "out/26", "2026-10", "mês passado" (Portuguese month names). If the
requested month is not in the series, it returns 'out_of_range' and the router answers right away,
without spending an LLM call. To support another language, extend MONTHS and PREVIOUS.
"""
import re
import unicodedata

MONTHS = {"janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "mar": 3, "abril": 4, "abr": 4,
          "maio": 5, "mai": 5, "junho": 6, "jun": 6, "julho": 7, "jul": 7, "agosto": 8, "ago": 8,
          "setembro": 9, "set": 9, "outubro": 10, "out": 10, "novembro": 11, "nov": 11,
          "dezembro": 12, "dez": 12}
ABBR = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))
RE_NAMED = re.compile(rf"\b({_NAMES})\b\.?(?:\s*(?:de|/|-)?\s*(\d{{4}}|\d{{2}})\b)?")
RE_ISO = re.compile(r"\b(\d{4})-(\d{2})\b")
PREVIOUS = ("mes passado", "mes anterior")


def norm(text: str) -> str:
    """Lowercase and accent-free, to compare free text."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def label(iso: str) -> str:
    """'2026-10-01' -> 'out/2026'."""
    year, month, _ = iso.split("-")
    return f"{ABBR[int(month) - 1]}/{year}"


def parse_period(text: str, available: list):
    """Returns (iso | None, status). status: 'none' | 'ok' | 'out_of_range'.

    `available` is the sorted list of the series' months, formatted as 'YYYY-MM-01'.
    """
    nq = norm(text)
    if any(p in nq for p in PREVIOUS):
        return (available[-2], "ok") if len(available) > 1 else (None, "out_of_range")

    m = RE_ISO.search(nq)
    if m:
        iso = f"{m.group(1)}-{m.group(2)}-01"
        return (iso, "ok") if iso in available else (None, "out_of_range")

    m = RE_NAMED.search(nq)
    if m:
        month = MONTHS[m.group(1)]
        year = m.group(2)
        if year:
            year = int(year) + (2000 if len(year) == 2 else 0)
            iso = f"{year}-{month:02d}-01"
            return (iso, "ok") if iso in available else (None, "out_of_range")
        same = [a for a in available if int(a[5:7]) == month]
        return (same[-1], "ok") if same else (None, "out_of_range")

    return None, "none"
