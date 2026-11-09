"""Prévisions du niveau d'eau, sous forme de scénarios (une trajectoire de niveaux par scénario).

Deux méthodes :

1. `prevision_ensemble` (usage quotidien) : les 50 scénarios de débit de la prévision d'ensemble GloFAS
   (Global Flood Awareness System, programme européen Copernicus), corrigés de leur biais puis convertis
   en niveaux par la courbe de tarage. On recolle chaque scénario au niveau mesuré aujourd'hui : l'écart du
   premier jour est retiré, puis cette correction s'efface progressivement (constante de 10 jours).
   Avec 50 scénarios, on peut dire « 7 chances sur 10 que… » : c'est la part des scénarios concernés.

2. `prevision_tarissement` (rejeu de l'été 2026, faute de prévisions archivées) : sans pluie, le débit d'un
   grand fleuve décroît à peu près exponentiellement (« courbe de tarissement »). On ajuste cette décroissance
   sur les 14 derniers jours et on la prolonge. Trois scénarios : sec (décroissance plus rapide), central, et
   « persistance » (le niveau reste stable). Méthode volontairement simple et transparente.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from kaub.config import Station


@dataclass
class Prevision:
    station: str
    dates: pd.DatetimeIndex  # jours prévus (à partir de demain)
    niveaux_cm: np.ndarray  # tableau (nb scénarios × nb jours)
    methode: str
    source: str

    @property
    def horizon(self) -> int:
        return self.niveaux_cm.shape[1]

    def centiles(self, qs=(10, 25, 50, 75, 90)) -> pd.DataFrame:
        return pd.DataFrame({f"p{q}": np.percentile(self.niveaux_cm, q, axis=0) for q in qs}, index=self.dates)

    def proba_sous(self, seuil_cm: float) -> pd.Series:
        """Pour chaque jour, part des scénarios sous le seuil."""
        return pd.Series((self.niveaux_cm < seuil_cm).mean(axis=0), index=self.dates)

    def proba_episode_sous(self, seuil_cm: float, jours_consecutifs: int, horizon: int | None = None) -> float:
        """Part des scénarios qui passent au moins `jours_consecutifs` jours d'affilée sous le seuil."""
        h = horizon or self.horizon
        sous = self.niveaux_cm[:, :h] < seuil_cm
        compte = 0
        for ligne in sous:
            serie, maxi = 0, 0
            for v in ligne:
                serie = serie + 1 if v else 0
                maxi = max(maxi, serie)
            compte += maxi >= jours_consecutifs
        return compte / len(sous)

    def resume(self) -> dict:
        c = self.centiles()
        pts = [6, 13, 20, 27, 34, 41]
        return {
            "station": self.station,
            "methode": self.methode,
            "source": self.source,
            "nb_scenarios": int(self.niveaux_cm.shape[0]),
            "centiles_affiches": [10, 50, 90],
            "premier_jour": str(self.dates[0].date()),
            "dernier_jour": str(self.dates[-1].date()),
            "jalons": [
                {
                    "date": str(c.index[i].date()),
                    "bas_p10_cm": round(float(c.p10.iloc[i]), 0),
                    "median_cm": round(float(c.p50.iloc[i]), 0),
                    "haut_p90_cm": round(float(c.p90.iloc[i]), 0),
                }
                for i in pts
                if i < len(c)
            ],
        }


def prevision_ensemble(
    station_id: str,
    station: Station,
    glofas_passe: pd.Series,
    membres: pd.DataFrame,
    niveau_aujourdhui_cm: float,
    aujourdhui: pd.Timestamp,
    horizon: int = 42,
    constante_recollage_jours: float = 10.0,
) -> Prevision:
    """Convertit la prévision d'ensemble GloFAS (débits) en scénarios de niveau à l'échelle.

    glofas_passe : débits GloFAS journaliers passés (au moins 3 semaines), index de dates.
    membres : un scénario par colonne, index de dates (peut commencer avant aujourd'hui).
    """
    correction = station.correction_glofas.correction()
    courbe = station.tarage.courbe()
    aujourdhui = pd.Timestamp(aujourdhui).normalize()
    debut = membres.index[0]
    passe = glofas_passe[glofas_passe.index < debut] if len(glofas_passe) else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    trajectoires = []
    for col in membres.columns:
        serie = pd.concat([passe, membres[col]]).sort_index()
        serie = serie[~serie.index.duplicated(keep="last")]
        niveaux = pd.Series(courbe.niveau(correction.appliquer(serie)), index=serie.index)
        # GloFAS est avancé d'un jour par la correction : le dernier jour de la série devient inconnu
        niveaux = niveaux.iloc[: len(niveaux) + correction.decalage_jours] if correction.decalage_jours < 0 else niveaux
        ecart0 = niveau_aujourdhui_cm - float(niveaux.loc[aujourdhui])
        futur = niveaux[niveaux.index > aujourdhui].iloc[:horizon]
        k = np.arange(1, len(futur) + 1)
        trajectoires.append(futur.values + ecart0 * np.exp(-k / constante_recollage_jours))
    n = min(len(t) for t in trajectoires)
    dates = pd.date_range(aujourdhui + pd.Timedelta(days=1), periods=n, freq="D")
    return Prevision(
        station=station_id,
        dates=dates,
        niveaux_cm=np.array([t[:n] for t in trajectoires]),
        methode=f"ensemble GloFAS corrigé ({len(trajectoires)} scénarios), recollé au niveau mesuré",
        source="Open-Meteo Flood API (GloFAS, Copernicus) + courbe de tarage calée sur PEGELONLINE",
    )


def prevision_tarissement(
    station_id: str,
    station: Station,
    niveaux_passes_cm: pd.Series,
    horizon: int = 42,
    fenetre: int = 14,
) -> Prevision:
    """Prévision « sans pluie » à partir des seuls niveaux observés jusqu'à aujourd'hui (aucune donnée future).

    Modèle : Q(t) = Qb + (Q0 − Qb) × exp(−t / constante), où Qb est le débit de base minimal du fleuve
    (alimenté par les lacs alpins et les nappes, il ne descend pas à zéro).
    """
    courbe = station.tarage.courbe()
    qb = station.debit_plancher_m3s
    w = niveaux_passes_cm.dropna().iloc[-fenetre:]
    q = courbe.debit(w.values)
    excedent = np.clip(q - qb, 1.0, None)
    pente = np.polyfit(np.arange(len(q)), np.log(excedent), 1)[0] if len(q) >= 5 else 0.0
    # constante de tarissement bornée entre 10 et 120 jours ; en montée des eaux, on ne prolonge pas la hausse
    k = float(np.clip(-pente, 1 / 120, 1 / 10)) if pente < 0 else 1 / 120
    q0 = float(np.mean(q[-3:]))
    jours = np.arange(1, horizon + 1)
    scenarios = {
        "sec": qb + (q0 - qb) * np.exp(-1.5 * k * jours),
        "central": qb + (q0 - qb) * np.exp(-k * jours),
        "persistance": np.full(horizon, q0),
    }
    aujourdhui = pd.Timestamp(niveaux_passes_cm.dropna().index[-1]).normalize()
    return Prevision(
        station=station_id,
        dates=pd.date_range(aujourdhui + pd.Timedelta(days=1), periods=horizon, freq="D"),
        niveaux_cm=np.array([courbe.niveau(np.maximum(v, qb)) for v in scenarios.values()]),
        methode=f"tarissement exponentiel vers un débit de base de {qb:.0f} m3/s, ajusté sur {fenetre} jours (constante {1 / k:.0f} jours) : scénarios sec, central, persistance",
        source="niveaux observés jusqu'au jour J uniquement",
    )
