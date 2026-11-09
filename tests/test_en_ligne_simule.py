"""Le mode « en ligne » de bout en bout, avec des réponses au format exact des vraies interfaces
(PEGELONLINE, Open-Meteo, Yahoo Finance), servies par un faux réseau. Aucun appel Internet."""

import json

import numpy as np
import pandas as pd
import pytest

from kaub.analyse import analyser
from kaub.situation import REF, situation_en_ligne
from kaub.sources import stockage


class FausseReponse:
    def __init__(self, donnees, status=200):
        self._d, self.status_code = donnees, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture
def faux_reseau(monkeypatch, tmp_path):
    ens = json.loads((REF / "glofas_ensemble_2026-11-09.json").read_text(encoding="utf-8"))
    aujourdhui = pd.Timestamp.now(tz="Europe/Paris").tz_localize(None).normalize()

    def get(url, params=None, headers=None, timeout=None):
        params = params or {}
        if "pegelonline" in url:
            station = url.split("/stations/")[1].split("/")[0]
            base = 11.0 if station == "KAUB" else 147.0
            if url.endswith("currentmeasurement.json"):
                return FausseReponse({"timestamp": "2026-11-09T11:00:00+01:00", "value": base})
            h = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("15min"), periods=96 * 31, freq="15min")
            vals = base + 5 * np.sin(np.arange(len(h)) / 200)
            return FausseReponse([{"timestamp": t.isoformat(), "value": float(v)} for t, v in zip(h, vals)])
        if "flood-api" in url:
            st = "KAUB" if params["latitude"] < 51 else "DUISBURG-RUHRORT"
            m = ens["stations"][st]["membres"]
            n = params["past_days"] + params["forecast_days"]
            dates = pd.date_range(aujourdhui - pd.Timedelta(days=params["past_days"]), periods=n)
            daily = {"time": [d.strftime("%Y-%m-%d") for d in dates]}
            for i, membre in enumerate(m, 1):
                v = (membre * 3)[:n]
                daily[f"river_discharge_member{i:02d}"] = v
            daily["river_discharge"] = daily["river_discharge_member01"]
            return FausseReponse({"daily": daily})
        if "api.open-meteo.com" in url:
            k = len(params["latitude"].split(","))
            jours = [d.strftime("%Y-%m-%d") for d in pd.date_range(aujourdhui, periods=16)]
            return FausseReponse([{"daily": {"time": jours, "precipitation_sum": [1.0] * 16}} for _ in range(k)])
        if "finance.yahoo" in url:
            prix = {"TTF%3DF": 87.01, "TTF=F": 87.01, "CO2.L": 83.04, "ZW=F": 589.25, "EURUSD=X": 1.12}
            sym = url.rsplit("/", 1)[1]
            return FausseReponse({"chart": {"result": [{"meta": {"regularMarketPrice": prix[sym], "regularMarketTime": int(pd.Timestamp.now().timestamp())}}]}})
        raise AssertionError(f"appel inattendu : {url}")

    monkeypatch.setattr("requests.get", get)
    monkeypatch.setattr(stockage, "DOSSIER", tmp_path)
    monkeypatch.setattr(stockage.ajouter_mesures, "__defaults__", (tmp_path,))
    monkeypatch.setattr(stockage.lire_serie, "__defaults__", (tmp_path,))
    monkeypatch.setattr(stockage.ajouter_prix, "__defaults__", (tmp_path,))
    return tmp_path


def test_situation_en_ligne(cfg, faux_reseau):
    s = situation_en_ligne(cfg)
    assert set(s.stations) == {"KAUB", "DUISBURG-RUHRORT"}
    assert s.stations["KAUB"].actuel_cm == 11.0
    assert s.previsions["KAUB"].niveaux_cm.shape[0] == 50
    assert {"gaz_ttf", "carbone_eua", "ble_euronext"} <= set(s.prix)
    assert (faux_reseau / "pegelonline" / "KAUB_W.csv").exists()  # l'historique est archivé
    a = analyser(cfg, s)
    assert a["usines"]["A"]["niveau_alerte"] in {"VERT", "ORANGE", "ROUGE"}
