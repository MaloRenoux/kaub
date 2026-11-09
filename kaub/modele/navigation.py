"""Du niveau d'eau à la capacité des péniches et au prix du fret.

La chaîne de calcul, étape par étape (chaque étape est une fonction testée) :

1. Profondeur du chenal = TuGlW − GlW + niveau à l'échelle
   (TuGlW = profondeur garantie quand l'eau est au niveau d'étiage de référence GlW).
   Exemple publié par Contargo pour Kaub : 190 − 78 + 60 = 172 cm. Le 14 août 2026, à 8 cm, le service des
   voies navigables annonçait « un peu plus de 1,20 m » : la formule donne 190 − 77 + 8 = 121 cm.
2. Tirant d'eau possible = profondeur − pied de pilote (marge sous la quille, 20 cm selon Contargo).
3. Charge utile = (tirant d'eau possible − tirant d'eau à vide) × tonnes par centimètre d'enfoncement,
   plafonnée au port en lourd du bateau.
4. Taux de chargement = charge utile / port en lourd.
5. Multiplicateur du fret = taux de chargement ^ (−élasticité), plafonné.
   Idée : un voyage coûte à peu près la même chose quel que soit le chargement, donc moins on charge,
   plus chaque tonne coûte cher ; le marché ne répercute qu'une partie de cet effet (élasticité < 1).
"""

from __future__ import annotations

import numpy as np

from kaub.config import Bateau, MarcheFret, Station


def profondeur_chenal_cm(station: Station, niveau_cm):
    """Profondeur garantie du chenal (cm) pour un niveau lu à l'échelle."""
    return station.tuglw_cm - station.glw_cm + np.asarray(niveau_cm, dtype=float)


def tonnes_par_cm(bateau: Bateau) -> float:
    """Tonnes de cargaison supplémentaires par centimètre d'enfoncement du bateau."""
    return bateau.port_en_lourd_t / (bateau.tirant_eau_max_cm - bateau.tirant_eau_lege_cm)


def charge_utile_t(station: Station, bateau: Bateau, niveau_cm):
    """Cargaison qu'un bateau peut prendre (t) quand la station est à ce niveau."""
    tirant_possible = profondeur_chenal_cm(station, niveau_cm) - bateau.pied_de_pilote_cm
    charge = (tirant_possible - bateau.tirant_eau_lege_cm) * tonnes_par_cm(bateau)
    return np.clip(charge, 0.0, bateau.port_en_lourd_t)


def taux_chargement(station: Station, bateau: Bateau, niveau_cm):
    """Part du port en lourd utilisable (entre 0 et 1)."""
    return charge_utile_t(station, bateau, niveau_cm) / bateau.port_en_lourd_t


def bateaux_necessaires(station: Station, bateau: Bateau, niveau_cm) -> float:
    """Nombre de bateaux nécessaires pour transporter ce qu'un seul bateau à pleine charge emporterait."""
    t = float(taux_chargement(station, bateau, niveau_cm))
    return float("inf") if t <= 0 else 1.0 / t


def voie_eau_ouverte(station: Station, bateau: Bateau, marche: MarcheFret, niveau_cm):
    """Vrai si la navigation commerciale reste possible (taux de chargement au-dessus du minimum)."""
    return taux_chargement(station, bateau, niveau_cm) >= marche.taux_chargement_min_navigation


def multiplicateur_fret(station: Station, bateau: Bateau, marche: MarcheFret, niveau_cm):
    """Combien de fois le fret de base coûte-t-il à ce niveau ? (1 = eaux normales)."""
    t = np.clip(taux_chargement(station, bateau, niveau_cm), marche.taux_chargement_min_navigation, 1.0)
    return np.minimum(t ** (-marche.elasticite), marche.multiplicateur_max)


def niveau_pour_taux(station: Station, bateau: Bateau, taux: float) -> float:
    """Niveau à l'échelle (cm) à partir duquel le bateau charge ce taux (calcul inverse, utile pour les seuils)."""
    tirant = bateau.tirant_eau_lege_cm + taux * bateau.port_en_lourd_t / tonnes_par_cm(bateau)
    return float(tirant + bateau.pied_de_pilote_cm - station.tuglw_cm + station.glw_cm)
