"""Enregistrement de l'historique : on garde nous-mêmes ce que PEGELONLINE efface au bout d'un mois.

Fichiers (un par station et par grandeur) : data/historique/pegelonline/KAUB_W.csv, etc.
Colonnes : horodatage (UTC), valeur. Les doublons sont supprimés à chaque ajout, donc on peut lancer la
collecte aussi souvent qu'on veut.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from kaub.config import RACINE

DOSSIER = RACINE / "data" / "historique"


def chemin_serie(station: str, grandeur: str, dossier: Path = DOSSIER) -> Path:
    return dossier / "pegelonline" / f"{station}_{grandeur}.csv"


def ajouter_mesures(station: str, grandeur: str, nouvelles: pd.DataFrame, dossier: Path = DOSSIER) -> int:
    """Fusionne de nouvelles mesures avec l'historique ; renvoie le nombre de lignes ajoutées."""
    chemin = chemin_serie(station, grandeur, dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nouvelles = nouvelles[["horodatage", "valeur"]].copy()
    nouvelles["horodatage"] = pd.to_datetime(nouvelles["horodatage"], utc=True)
    if chemin.exists():
        ancien = pd.read_csv(chemin, parse_dates=["horodatage"])
        ancien["horodatage"] = pd.to_datetime(ancien["horodatage"], utc=True)
        avant = len(ancien)
        tout = pd.concat([ancien, nouvelles]).drop_duplicates("horodatage", keep="last")
    else:
        avant = 0
        tout = nouvelles.drop_duplicates("horodatage", keep="last")
    tout = tout.sort_values("horodatage")
    tout.to_csv(chemin, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    return len(tout) - avant


def lire_serie(station: str, grandeur: str, dossier: Path = DOSSIER) -> pd.DataFrame:
    chemin = chemin_serie(station, grandeur, dossier)
    if not chemin.exists():
        return pd.DataFrame(columns=["horodatage", "valeur"])
    df = pd.read_csv(chemin)
    df["horodatage"] = pd.to_datetime(df["horodatage"], utc=True)
    return df


def ajouter_prix(lignes: list[dict], dossier: Path = DOSSIER) -> None:
    """Archive les prix récupérés automatiquement (un fichier pour tous les produits)."""
    chemin = dossier / "prix_auto.csv"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(lignes)
    if chemin.exists():
        df = pd.concat([pd.read_csv(chemin), df]).drop_duplicates(["date", "produit"], keep="last")
    df.sort_values(["date", "produit"]).to_csv(chemin, index=False)
