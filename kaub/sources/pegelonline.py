"""Niveaux et débits du Rhin en temps réel : PEGELONLINE.

PEGELONLINE est le service de l'administration fédérale allemande des voies navigables (WSV,
Wasserstraßen- und Schifffahrtsverwaltung des Bundes). Interface REST (Representational State Transfer,
une adresse web par donnée) gratuite, sans clé, licence CC BY 4.0 (réutilisation libre en citant la source).
Documentation : https://www.pegelonline.wsv.de/webservice/dokuRestapi

Attention : l'interface ne garde qu'environ 31 jours d'historique. D'où l'enregistrement quotidien
(voir kaub/sources/stockage.py et .github/workflows/collecte.yml).
"""

from __future__ import annotations

import pandas as pd
import requests

BASE = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations"
ENTETES = {"User-Agent": "KAUB-prototype/0.1 (projet etudiant)"}
SOURCE = "PEGELONLINE (WSV), licence CC BY 4.0"


def mesure_actuelle(station: str, grandeur: str = "W", timeout: float = 20) -> dict:
    """Dernière mesure publiée : {'horodatage', 'valeur', 'unite', 'source'}."""
    url = f"{BASE}/{station}/{grandeur}/currentmeasurement.json"
    r = requests.get(url, headers=ENTETES, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    return {
        "station": station,
        "grandeur": grandeur,
        "horodatage": j["timestamp"],
        "valeur": float(j["value"]),
        "unite": "cm" if grandeur == "W" else "m3/s",
        "source": SOURCE,
    }


def mesures(station: str, grandeur: str = "W", debut: str = "P31D", timeout: float = 30) -> pd.DataFrame:
    """Mesures brutes au pas de 15 minutes (31 jours maximum). Colonnes : horodatage, valeur."""
    url = f"{BASE}/{station}/{grandeur}/measurements.json"
    r = requests.get(url, params={"start": debut}, headers=ENTETES, timeout=timeout)
    if r.status_code == 400 and debut == "P31D":  # selon les jours, la limite est 30 jours
        r = requests.get(url, params={"start": "P30D"}, headers=ENTETES, timeout=timeout)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["horodatage"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[["horodatage", "value"]].rename(columns={"value": "valeur"})


def journalier(brut: pd.DataFrame, fuseau: str = "Europe/Berlin") -> pd.DataFrame:
    """Agrège des mesures brutes par jour local : moyenne, minimum, maximum et valeur de 5 h 00
    (la valeur de référence des contrats de fret selon Contargo)."""
    d = brut.copy()
    local = d["horodatage"].dt.tz_convert(fuseau)
    d["date"] = local.dt.tz_localize(None).dt.normalize()
    d["est_0500"] = (local.dt.hour == 5) & (local.dt.minute == 0)
    g = d.groupby("date")
    out = pd.DataFrame(
        {
            "moyenne": g["valeur"].mean().round(1),
            "min": g["valeur"].min(),
            "max": g["valeur"].max(),
            "valeur_0500": d[d.est_0500].groupby("date")["valeur"].first(),
            "nb_mesures": g["valeur"].size(),
        }
    )
    return out
