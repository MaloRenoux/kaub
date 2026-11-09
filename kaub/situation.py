"""La « situation du jour » : toutes les données d'entrée, chacune avec sa source et sa date.

Deux modes :
- en ligne : on interroge PEGELONLINE, Open-Meteo et les cours de marché, et on archive les niveaux ;
- hors ligne : on relit l'instantané réel du 9 novembre 2026 rangé dans data/reference/ (démonstration
  sans connexion, tests automatiques, et preuve que le projet tourne sur de vraies données).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from kaub.config import RACINE, Config
from kaub.hydro.prevision import Prevision, prevision_ensemble
from kaub.sources import openmeteo, pegelonline, prix as prix_src, stockage

REF = RACINE / "data" / "reference"
DATE_REFERENCE = "2026-11-09"


@dataclass
class EtatStation:
    station: str
    actuel_cm: float
    horodatage: str
    debit_m3s: float | None
    journalier: pd.DataFrame  # index date ; colonnes moyenne, min, max, valeur_0500
    source: str

    @property
    def tendance_7j_cm_par_jour(self) -> float:
        s = self.journalier["moyenne"].dropna().iloc[-8:]
        return float(np.polyfit(np.arange(len(s)), s.values, 1)[0]) if len(s) >= 3 else 0.0


@dataclass
class Situation:
    date: pd.Timestamp
    mode: str
    stations: dict[str, EtatStation]
    previsions: dict[str, Prevision]
    prix: dict[str, prix_src.Prix]
    pluie_mm: pd.DataFrame | None
    avertissements: list[str] = field(default_factory=list)


def _niveaux_reference() -> tuple[dict[str, EtatStation], pd.DataFrame]:
    df = pd.read_csv(REF / "pegelonline_journalier_2026-10-09_2026-11-09.csv", comment="#", parse_dates=["date"])
    etats = {}
    for st, d in df.groupby("station"):
        w = d[d.grandeur == "W"].set_index("date")[["moyenne", "min", "max", "valeur_0500"]]
        q = d[d.grandeur == "Q"].set_index("date")["moyenne"]
        etats[st] = EtatStation(
            station=st,
            actuel_cm=float(w["moyenne"].iloc[-1]),
            horodatage="2026-11-09 (moyenne de la journée jusqu'à 11 h)",
            debit_m3s=float(q.iloc[-1]),
            journalier=w,
            source=pegelonline.SOURCE + ", relevé du 9/11/2026",
        )
    return etats, df


def situation_hors_ligne(cfg: Config) -> Situation:
    """Situation réelle du 9 novembre 2026, reconstruite à partir des fichiers de data/reference/."""
    etats, _ = _niveaux_reference()
    etats = {k: etats[k] for k in cfg.stations if k in etats}  # Kaub d'abord, dans l'ordre du fichier d'hypothèses
    hist = json.loads((REF / "glofas_historique_2026-05-01_2026-11-09.json").read_text(encoding="utf-8"))
    ens = json.loads((REF / "glofas_ensemble_2026-11-09.json").read_text(encoding="utf-8"))
    aujourdhui = pd.Timestamp(ens["aujourdhui"])
    previsions = {}
    for st, etat in etats.items():
        h = hist["stations"][st]
        passe = pd.Series(h["q"], index=pd.date_range(hist["debut"], periods=len(h["q"])), dtype=float)
        m = ens["stations"][st]["membres"]
        membres = pd.DataFrame(np.array(m).T, index=pd.date_range(ens["debut"], periods=len(m[0])))
        previsions[st] = prevision_ensemble(st, cfg.stations[st], passe, membres, etat.actuel_cm, aujourdhui)
    meteo = json.loads((REF / "meteo_2026-11-09.json").read_text(encoding="utf-8"))
    pluie = pd.DataFrame({k: v["pluie_mm"] for k, v in meteo["points"].items()}, index=pd.date_range(meteo["debut"], periods=16))
    return Situation(
        date=aujourdhui,
        mode="hors ligne — données réelles du 9 novembre 2026",
        stations=etats,
        previsions=previsions,
        prix=prix_src.prix_reference(REF / "prix_2026-11-09.csv"),
        pluie_mm=pluie,
    )


def situation_en_ligne(cfg: Config, archiver: bool = True) -> Situation:
    """Interroge les sources publiques ; une source en panne produit un avertissement, pas une erreur."""
    avert: list[str] = []
    etats, previsions = {}, {}
    aujourdhui = pd.Timestamp.now(tz="Europe/Paris").tz_localize(None).normalize()
    for st_id, st in cfg.stations.items():
        try:
            w = pegelonline.mesures(st.pegelonline, "W")
            q = pegelonline.mesures(st.pegelonline, "Q")
            if archiver:
                stockage.ajouter_mesures(st_id, "W", w)
                stockage.ajouter_mesures(st_id, "Q", q)
            # on complète avec l'historique archivé (au-delà des 31 jours de PEGELONLINE)
            w_tout = pd.concat([stockage.lire_serie(st_id, "W"), w]).drop_duplicates("horodatage", keep="last")
            jour = pegelonline.journalier(w_tout)
            actuel = pegelonline.mesure_actuelle(st.pegelonline, "W")
            debit = pegelonline.mesure_actuelle(st.pegelonline, "Q")["valeur"]
            etats[st_id] = EtatStation(st_id, actuel["valeur"], actuel["horodatage"], debit, jour, pegelonline.SOURCE)
        except Exception as e:  # noqa: BLE001
            avert.append(f"Niveaux {st_id} indisponibles ({e.__class__.__name__}).")
            continue
        try:
            membres = openmeteo.glofas_ensemble(st.glofas.latitude, st.glofas.longitude)
            previsions[st_id] = prevision_ensemble(
                st_id, st, pd.Series(dtype=float), membres, etats[st_id].actuel_cm, aujourdhui
            )
        except Exception as e:  # noqa: BLE001
            avert.append(f"Prévision {st_id} indisponible ({e.__class__.__name__}).")
    prix = prix_src.prix_du_jour()
    if archiver and prix:
        stockage.ajouter_prix([p.en_dict() for p in prix.values()])
    for p in ("ble_euronext", "gaz_ttf", "carbone_eua"):
        if p not in prix:
            avert.append(f"Prix {p} indisponible.")
        elif prix[p].date < (aujourdhui - pd.Timedelta(days=4)).strftime("%Y-%m-%d"):
            avert.append(f"Prix {p} ancien (du {prix[p].date}) : pensez à mettre à jour data/historique/prix_manuels.csv.")
    try:
        pluie = openmeteo.pluie_prevue()
    except Exception as e:  # noqa: BLE001
        pluie = None
        avert.append(f"Météo indisponible ({e.__class__.__name__}).")
    return Situation(aujourdhui, "en ligne", etats, previsions, prix, pluie, avert)
