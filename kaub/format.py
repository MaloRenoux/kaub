"""Mise en forme des nombres à la française (espace des milliers, virgule décimale)."""

from __future__ import annotations

import math

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def nb(x, dec: int = 0, signe: bool = False) -> str:
    """1234.5 → '1 234,5' (espace insécable fine pour les milliers)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n.d."
    s = f"{x:+,.{dec}f}" if signe else f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",").replace("-", "−")


def eur(x, dec: int = 0) -> str:
    return f"{nb(x, dec)} €"


def keur(x) -> str:
    """Montant en milliers d'euros : 671 495 → '671 k€'."""
    return f"{nb(x / 1000, 0)} k€"


def pct(p, dec: int = 0) -> str:
    """0.22 → '22 %'."""
    return f"{nb(100 * p, dec)} %"


def date_fr(iso: str, annee: bool = True) -> str:
    a, m, j = iso[:10].split("-")
    return f"{int(j)} {MOIS[int(m) - 1]}" + (f" {a}" if annee else "")
