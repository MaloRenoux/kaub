"""Le vérificateur de chiffres : chaque nombre écrit par l'IA doit venir d'un outil.

Principe : on relève tous les nombres de la note rédigée par Claude, puis on cherche chacun dans les
résultats des outils appelés pendant la rédaction (en tenant compte des arrondis, des pourcentages et des
milliers d'euros). Un chiffre introuvable est signalé : il a pu être inventé, ou calculé de tête par le
modèle, ce que la règle de conception interdit (« le modèle d'IA orchestre, le code calcule »).

Ne sont pas contrôlés : les dates, et les petits entiers (0 à 10) qui servent surtout à compter
(« 3 options », « 6 semaines »).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MOIS = "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
DATES = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"),
    re.compile(rf"\b\d{{1,2}}(?:er)?\s+(?:{MOIS})(?:\s+\d{{4}})?", re.IGNORECASE),
    re.compile(rf"(?:{MOIS})\s+\d{{4}}", re.IGNORECASE),
    re.compile(r"\b(?:19|20)\d{2}\b"),
    re.compile(r"\b\d{1,2}\s?h\s?\d{0,2}\b"),  # heures : 11 h, 5 h 00
]
NOMBRE = re.compile(r"[−-]?\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|[−-]?\d+(?:[.,]\d+)?")


@dataclass
class Rapport:
    controles: int
    verifies: int
    non_verifies: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.non_verifies

    def resume(self) -> str:
        if self.ok:
            return f"✅ {self.verifies}/{self.controles} chiffres retrouvés dans les résultats des outils."
        return (
            f"⚠️ {len(self.non_verifies)} chiffre(s) sur {self.controles} introuvable(s) dans les résultats des outils : "
            + ", ".join(self.non_verifies)
        )


def _nombres_reference(resultats: list) -> list[float]:
    vals: list[float] = []

    def parcourir(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.append(float(x))
        elif isinstance(x, dict):
            for k, v in x.items():
                parcourir(str(k))  # les clés portent aussi des paramètres (ex. « gaz_plus_20pct »)
                parcourir(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                parcourir(v)
        elif isinstance(x, str):
            for m in NOMBRE.finditer(x):
                try:
                    vals.append(_lire(m.group()))
                except ValueError:
                    pass

    for r in resultats:
        parcourir(r if not isinstance(r, str) else json.loads(r) if r.strip().startswith(("{", "[")) else r)
    variantes = []
    for v in vals:
        variantes += [v, abs(v), v * 100, abs(v) * 100, v / 1000, abs(v) / 1000, v / 1e6, abs(v) / 1e6]
    return variantes


def _lire(texte: str) -> float:
    t = texte.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
    return float(t)


def _decimales(texte: str) -> int:
    t = texte.replace(".", ",")
    return len(t.split(",")[1]) if "," in t else 0


def verifier(texte: str, resultats_outils: list) -> Rapport:
    """Contrôle les nombres de `texte` contre les résultats d'outils (dictionnaires ou chaînes JSON)."""
    propre = texte
    for motif in DATES:
        propre = motif.sub(" ", propre)
    refs = _nombres_reference(resultats_outils)
    controles, verifies, absents = 0, 0, []
    for m in NOMBRE.finditer(propre):
        brut = m.group()
        try:
            v = _lire(brut)
        except ValueError:
            continue
        if _decimales(brut) == 0 and abs(v) <= 10:
            continue
        controles += 1
        tol = 0.5 * 10 ** (-_decimales(brut)) + 1e-9
        if any(abs(v - r) <= tol or abs(abs(v) - r) <= tol for r in refs):
            verifies += 1
        else:
            absents.append(brut.strip())
    return Rapport(controles, verifies, absents)
