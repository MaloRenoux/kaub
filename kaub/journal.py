"""Journal des recommandations et des décisions : la mémoire de KAUB.

Chaque jour, KAUB enregistre ce qu'il a recommandé ; l'équipe enregistre ce qu'elle a décidé (et pourquoi).
L'agent relit ces décisions avant de recommander : si une option a déjà été écartée pour une raison
pratique (par exemple « pas de sillons ferroviaires disponibles »), il le signale au lieu de la reproposer
aveuglément.

Format : un objet JSON par ligne (JSONL) dans data/journal/decisions.jsonl, facile à lire et à versionner.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from kaub.config import RACINE

FICHIER = RACINE / "data" / "journal" / "decisions.jsonl"


def _ecrire(entree: dict, fichier: Path = FICHIER) -> dict:
    fichier.parent.mkdir(parents=True, exist_ok=True)
    entree = {"horodatage": datetime.now().isoformat(timespec="seconds"), **entree}
    with open(fichier, "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    return entree


def enregistrer_recommandation(analyse: dict, fichier: Path = FICHIER) -> list[dict]:
    """Garde la trace de ce que KAUB a recommandé ce jour-là, usine par usine."""
    return [
        _ecrire(
            {
                "type": "recommandation",
                "date": analyse["date"],
                "usine": u,
                "alerte": r["niveau_alerte"],
                "option": r["recommandation"]["option"],
                "proba_rupture_sans_action": r["recommandation"]["proba_rupture_avant"],
            },
            fichier,
        )
        for u, r in analyse["usines"].items()
    ]


def enregistrer_decision(date: str, usine: str, option: str, decideur: str, retenue: bool, commentaire: str = "", fichier: Path = FICHIER) -> dict:
    """Ce que l'équipe a décidé : l'option retenue ou écartée, par qui, et pourquoi."""
    return _ecrire(
        {"type": "decision", "date": date, "usine": usine, "option": option, "retenue": retenue, "decideur": decideur, "commentaire": commentaire},
        fichier,
    )


def lire(nombre: int = 20, fichier: Path = FICHIER) -> list[dict]:
    if not Path(fichier).exists():
        return []
    lignes = Path(fichier).read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(l) for l in lignes[-nombre:] if l.strip()]


def options_ecartees(usine: str, fichier: Path = FICHIER) -> dict[str, str]:
    """Options écartées par l'équipe pour cette usine, avec le dernier motif donné."""
    res = {}
    for e in lire(500, fichier):
        if e.get("type") == "decision" and e.get("usine") == usine and not e.get("retenue"):
            res[e["option"]] = f"écartée le {e['date']} par {e['decideur']} : {e.get('commentaire') or 'sans motif'}"
    return res
