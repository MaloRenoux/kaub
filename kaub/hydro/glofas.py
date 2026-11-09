"""Correction des débits simulés par GloFAS (Global Flood Awareness System, système mondial d'alerte
aux crues du programme européen Copernicus, diffusé gratuitement par Open-Meteo).

Constat fait sur les 31 jours où l'on dispose à la fois des mesures officielles et de GloFAS (oct.–nov. 2026) :
1. GloFAS est en retard d'environ un jour sur les mesures ;
2. en période sèche (débit de base), GloFAS surestime le débit d'environ 10 % ;
3. lors d'une montée des eaux après la pluie, GloFAS exagère fortement le pic (jusqu'à +70 %).

D'où une correction en deux parts, simple à expliquer :
    Q_corrigé = a × débit_de_base + b × (Q_GloFAS − débit_de_base)
où le « débit de base » est le minimum de GloFAS sur les N derniers jours (la part lente, alimentée par
les nappes et les lacs alpins) et le reste est la part rapide (le ruissellement après la pluie).
Les coefficients a et b sont calés sur la période où les deux séries existent, puis CONTRÔLÉS sur les
relevés publiés dans la presse pendant l'été 2026, qui n'ont pas servi au calage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CorrectionGlofas:
    decalage_jours: int  # -1 : on avance GloFAS d'un jour pour rattraper son retard
    fenetre_jours: int  # fenêtre du minimum glissant qui définit le débit de base
    coef_base: float  # a
    coef_rapide: float  # b

    def appliquer(self, glofas: pd.Series) -> pd.Series:
        """Transforme une série journalière GloFAS (index de dates) en débit corrigé (m3/s)."""
        g = glofas.astype(float).shift(self.decalage_jours).ffill()
        base = g.rolling(self.fenetre_jours, min_periods=1).min()
        return self.coef_base * base + self.coef_rapide * (g - base)


def caler_correction(
    glofas: pd.Series,
    debit_observe: pd.Series,
    decalage_jours: int = -1,
    fenetres=(7, 10, 15, 21, 30),
) -> tuple[CorrectionGlofas, float]:
    """Choisit la fenêtre et les coefficients a, b qui reproduisent le mieux les débits mesurés.

    Retourne la correction retenue et son erreur quadratique moyenne (m3/s) sur la période de calage.
    """
    meilleure, meilleure_err = None, np.inf
    g = glofas.astype(float).shift(decalage_jours).ffill()
    obs = debit_observe.dropna()
    for fenetre in fenetres:
        base = g.rolling(fenetre, min_periods=1).min()
        X = np.c_[base.reindex(obs.index), (g - base).reindex(obs.index)]
        ok = ~np.isnan(X).any(axis=1)
        coef, *_ = np.linalg.lstsq(X[ok], obs.values[ok], rcond=None)
        err = float(np.sqrt(np.mean((X[ok] @ coef - obs.values[ok]) ** 2)))
        if err < meilleure_err:
            meilleure = CorrectionGlofas(decalage_jours, fenetre, float(coef[0]), float(coef[1]))
            meilleure_err = err
    return meilleure, meilleure_err
