"""Courbe de tarage : la relation entre le niveau d'eau lu à l'échelle (W, en cm) et le débit (Q, en m3/s).

Pourquoi en a-t-on besoin ? Les modèles hydrologiques (comme GloFAS, Global Flood Awareness System,
le système mondial d'alerte aux crues du programme européen Copernicus) prévoient un DÉBIT, alors que
la navigation se pilote au NIVEAU lu à l'échelle de Kaub. La courbe de tarage fait le pont.

Forme retenue (classique en hydrométrie) : Q = c × (W − W0)^n
- W0 : niveau « fictif » pour lequel le débit serait nul (le zéro de l'échelle n'est pas le fond du fleuve) ;
- c et n : coefficients ajustés sur des couples (W, Q) mesurés.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import curve_fit


@dataclass(frozen=True)
class CourbeTarage:
    """Paramètres d'une courbe de tarage Q = c × (W − W0)^n."""

    W0: float
    c: float
    n: float

    def debit(self, niveau_cm):
        """Débit (m3/s) correspondant à un niveau à l'échelle (cm)."""
        w = np.asarray(niveau_cm, dtype=float)
        return self.c * np.clip(w - self.W0, 1e-9, None) ** self.n

    def niveau(self, debit_m3s):
        """Niveau à l'échelle (cm) correspondant à un débit (m3/s) : la courbe inversée."""
        q = np.clip(np.asarray(debit_m3s, dtype=float), 1e-9, None)
        return self.W0 + (q / self.c) ** (1.0 / self.n)


def caler_courbe(niveaux_cm, debits_m3s, poids=None, depart=(-150.0, 0.1, 1.6)) -> tuple[CourbeTarage, float]:
    """Ajuste W0, c et n par moindres carrés sur des couples (niveau, débit) mesurés.

    Retourne la courbe et l'erreur quadratique moyenne en débit (m3/s), pour juger la qualité du calage.
    `poids` permet de donner plus d'importance à quelques points de référence (par exemple les valeurs
    principales de l'annuaire hydrologique), qui étendent la courbe au-delà des 31 derniers jours.
    """
    w = np.asarray(niveaux_cm, dtype=float)
    q = np.asarray(debits_m3s, dtype=float)
    sigma = None if poids is None else 1.0 / np.asarray(poids, dtype=float)

    def modele(w_, W0, c, n):
        return c * np.clip(w_ - W0, 1e-9, None) ** n

    (W0, c, n), _ = curve_fit(modele, w, q, p0=depart, sigma=sigma, maxfev=50_000)
    courbe = CourbeTarage(float(W0), float(c), float(n))
    rmse = float(np.sqrt(np.mean((courbe.debit(w) - q) ** 2)))
    return courbe, rmse
