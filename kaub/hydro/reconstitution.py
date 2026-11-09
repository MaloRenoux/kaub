"""Reconstitution des niveaux de l'été 2026, que PEGELONLINE n'a plus en mémoire.

Méthode, en trois étapes, entièrement à partir de données publiques :
1. Débits simulés par GloFAS (Global Flood Awareness System, programme Copernicus) du 1er mai au 9 novembre,
   corrigés de leur biais (correction calée sur octobre–novembre, où l'on a les mesures officielles).
2. Conversion en niveaux par la courbe de tarage de Kaub.
3. Ancrage sur les relevés publiés dans la presse (date et valeur connues) : on mesure l'écart entre la série
   et chaque relevé, on interpole cet écart dans le temps, et on l'ajoute à la série. Entre deux relevés, la
   forme de la courbe vient de GloFAS ; aux dates des relevés, la série passe par les valeurs publiées.

Contrôle honnête de la qualité : validation croisée « en laissant un relevé de côté » (on reconstruit sans
le relevé i, puis on mesure l'erreur sur ce relevé). Cette erreur est l'ordre de grandeur de l'incertitude
de la série entre deux relevés. À partir du 10 octobre, on utilise directement les mesures officielles.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from kaub.config import RACINE, Config

REF = RACINE / "data" / "reference"


def charger_ancres(station: str = "KAUB") -> pd.DataFrame:
    a = pd.read_csv(REF / "releves_presse_2026.csv", comment="#", parse_dates=["date"])
    return a[a.station == station].reset_index(drop=True)


def niveaux_glofas(cfg: Config, station: str) -> pd.Series:
    """Niveaux déduits de GloFAS corrigé (étapes 1 et 2), un par jour."""
    h = json.loads((REF / "glofas_historique_2026-05-01_2026-11-09.json").read_text(encoding="utf-8"))
    q = h["stations"][station]["q"]
    g = pd.Series(q, index=pd.date_range(h["debut"], periods=len(q)), dtype=float)
    st = cfg.stations[station]
    w = st.tarage.courbe().niveau(st.correction_glofas.correction().appliquer(g))
    w = pd.Series(w, index=g.index)
    return w.iloc[:-1]  # le dernier jour n'est pas connu après le décalage d'un jour


def niveaux_officiels(station: str) -> pd.Series:
    df = pd.read_csv(REF / "pegelonline_journalier_2026-10-09_2026-11-09.csv", comment="#", parse_dates=["date"])
    d = df[(df.station == station) & (df.grandeur == "W") & (df.nb_mesures >= 90)]
    return d.set_index("date")["moyenne"]


def ancrer(brute: pd.Series, ancres: pd.DataFrame, decroissance_jours: float = 7.0) -> pd.Series:
    """Étape 3 : ajoute à la série l'écart aux relevés, interpolé linéairement entre relevés et qui
    s'efface progressivement avant le premier et après le dernier relevé."""
    a = ancres.sort_values("date")
    ecarts = pd.Series(a["niveau_cm"].values - brute.reindex(a["date"]).values, index=pd.DatetimeIndex(a["date"]))
    ecarts = ecarts.dropna()
    if ecarts.empty:
        return brute.copy()
    t = (brute.index - brute.index[0]).days.values.astype(float)
    ta = (ecarts.index - brute.index[0]).days.values.astype(float)
    corr = np.interp(t, ta, ecarts.values)
    avant, apres = t < ta[0], t > ta[-1]
    corr[avant] = ecarts.values[0] * np.exp(-(ta[0] - t[avant]) / decroissance_jours)
    corr[apres] = ecarts.values[-1] * np.exp(-(t[apres] - ta[-1]) / decroissance_jours)
    return brute + corr


def reconstituer(cfg: Config, station: str = "KAUB", debut: str = "2026-06-01") -> tuple[pd.DataFrame, dict]:
    """Série journalière du `debut` au 8 novembre 2026, avec sa source jour par jour, et le bilan de qualité."""
    brute = niveaux_glofas(cfg, station)
    officiel = niveaux_officiels(station)
    ancres = charger_ancres(station)
    utilisables = ancres[(ancres.fiabilite != "approx") & (ancres.date < officiel.index.min())]
    ancree = ancrer(brute, utilisables)

    # Validation croisée : on retire chaque relevé à tour de rôle
    erreurs_loo, erreurs_brutes = [], []
    for i, ligne in utilisables.iterrows():
        sans = ancrer(brute, utilisables.drop(index=i))
        erreurs_loo.append(float(sans.loc[ligne.date] - ligne.niveau_cm))
        erreurs_brutes.append(float(brute.loc[ligne.date] - ligne.niveau_cm))
    commun = officiel.index.intersection(brute.index)
    serie = ancree.copy()
    source = pd.Series("reconstitué (GloFAS corrigé, ancré sur la presse)", index=serie.index)
    serie.loc[commun] = officiel.loc[commun]
    source.loc[commun] = "mesure officielle PEGELONLINE"
    df = pd.DataFrame({"niveau_cm": serie.round(1), "source": source, "glofas_corrige_cm": brute.round(1)})
    df = df[df.index >= pd.Timestamp(debut)]
    controles = ancres[ancres.date >= officiel.index.min()]
    bilan = {
        "station": station,
        "nb_releves_ancrage": int(len(utilisables)),
        "erreur_avant_ancrage_cm": {"moyenne_absolue": round(float(np.mean(np.abs(erreurs_brutes))), 1), "max": round(float(np.max(np.abs(erreurs_brutes))), 1)},
        "erreur_validation_croisee_cm": {"moyenne_absolue": round(float(np.mean(np.abs(erreurs_loo))), 1), "max": round(float(np.max(np.abs(erreurs_loo))), 1)},
        "detail_validation_croisee": [
            {"date": str(l.date.date()), "releve_cm": float(l.niveau_cm), "reconstitue_sans_ce_releve_cm": round(float(l.niveau_cm + e), 1)}
            for (_, l), e in zip(utilisables.iterrows(), erreurs_loo)
        ],
        "erreur_glofas_corrige_sur_mesures_officielles_cm": round(float(np.sqrt(np.mean((brute.loc[commun] - officiel.loc[commun]) ** 2))), 1),
        "controle_presse_vs_officiel": [
            {"date": str(l.date.date()), "presse_cm": float(l.niveau_cm), "officiel_moyenne_jour_cm": float(officiel.get(l.date, np.nan))} for _, l in controles.iterrows()
        ],
    }
    return df, bilan
