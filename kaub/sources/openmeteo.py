"""Prévisions hydrologiques (GloFAS) et météo : Open-Meteo.

- Flood API : débits du modèle GloFAS (Global Flood Awareness System, programme européen Copernicus),
  passés et prévus, y compris les 50 scénarios de la prévision d'ensemble.
- Forecast API : cumul de pluie prévu sur le bassin du Rhin.
Gratuit pour un usage non commercial, sans clé, licence CC BY 4.0. https://open-meteo.com
"""

from __future__ import annotations

import pandas as pd
import requests

FLOOD = "https://flood-api.open-meteo.com/v1/flood"
METEO = "https://api.open-meteo.com/v1/forecast"
SOURCE_GLOFAS = "Open-Meteo Flood API (GloFAS, Copernicus), licence CC BY 4.0"
SOURCE_METEO = "Open-Meteo, prévision météo, licence CC BY 4.0"

POINTS_BASSIN = {
    "Bâle (Rhin alpin)": (47.56, 7.59),
    "Karlsruhe (Rhin supérieur)": (49.01, 8.40),
    "Francfort (bassin du Main)": (50.11, 8.68),
    "Trèves (bassin de la Moselle)": (49.75, 6.64),
    "Kaub (Rhin moyen)": (50.09, 7.76),
}


def glofas_historique(latitude: float, longitude: float, debut: str, fin: str, timeout: float = 30) -> pd.Series:
    """Débits journaliers GloFAS (m3/s) entre deux dates (AAAA-MM-JJ)."""
    r = requests.get(
        FLOOD,
        params={"latitude": latitude, "longitude": longitude, "daily": "river_discharge", "start_date": debut, "end_date": fin},
        timeout=timeout,
    )
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.Series(d["river_discharge"], index=pd.to_datetime(d["time"]), name="glofas_m3s", dtype=float)


def glofas_ensemble(latitude: float, longitude: float, jours_passes: int = 31, jours_prevus: int = 43, timeout: float = 60) -> pd.DataFrame:
    """Prévision d'ensemble : une colonne par scénario (50), index de dates (passé récent compris)."""
    r = requests.get(
        FLOOD,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": "river_discharge",
            "past_days": jours_passes,
            "forecast_days": jours_prevus,
            "ensemble": "true",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    d = r.json()["daily"]
    cols = sorted(k for k in d if k.startswith("river_discharge_member"))
    return pd.DataFrame({c.replace("river_discharge_", ""): d[c] for c in cols}, index=pd.to_datetime(d["time"]), dtype=float)


def pluie_prevue(jours: int = 16, timeout: float = 30) -> pd.DataFrame:
    """Cumul de pluie journalier prévu (mm) aux points du bassin ; une colonne par point."""
    lat = ",".join(str(p[0]) for p in POINTS_BASSIN.values())
    lon = ",".join(str(p[1]) for p in POINTS_BASSIN.values())
    r = requests.get(
        METEO,
        params={"latitude": lat, "longitude": lon, "daily": "precipitation_sum", "forecast_days": jours, "timezone": "Europe/Berlin"},
        timeout=timeout,
    )
    r.raise_for_status()
    res = r.json()
    res = res if isinstance(res, list) else [res]
    return pd.DataFrame(
        {nom: x["daily"]["precipitation_sum"] for nom, x in zip(POINTS_BASSIN, res)},
        index=pd.to_datetime(res[0]["daily"]["time"]),
    )
