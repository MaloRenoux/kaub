"""Coût rendu usine : ce que coûte une tonne de blé une fois arrivée dans le silo de l'usine.

coût rendu = prix du blé (Euronext + base régionale) + fret du mode de transport + manutention
"""

from __future__ import annotations

from kaub.config import Config, Usine
from kaub.modele import navigation as nav


def fret_peniche_eur_t(cfg: Config, usine: Usine, niveau_cm: float) -> dict:
    """Fret par péniche (€/t) pour l'usine, au niveau donné de sa station de référence."""
    appro = usine.approvisionnement.peniche
    if appro.part <= 0 or appro.station is None:
        return {"disponible": False, "raison": "usine non desservie par la voie d'eau"}
    station = cfg.stations[appro.station]
    taux = float(nav.taux_chargement(station, cfg.bateau, niveau_cm))
    ouvert = bool(nav.voie_eau_ouverte(station, cfg.bateau, cfg.marche_fret, niveau_cm))
    mult = float(nav.multiplicateur_fret(station, cfg.bateau, cfg.marche_fret, niveau_cm))
    return {
        "disponible": ouvert,
        "station": appro.station,
        "niveau_cm": round(float(niveau_cm), 1),
        "profondeur_chenal_cm": round(float(nav.profondeur_chenal_cm(station, niveau_cm)), 1),
        "taux_chargement": round(taux, 3),
        "bateaux_pour_un": round(nav.bateaux_necessaires(station, cfg.bateau, niveau_cm), 1) if taux > 0 else None,
        "multiplicateur_fret": round(mult, 2),
        "fret_base_eur_t": appro.fret_base_eur_t,
        "fret_eur_t": round(appro.fret_base_eur_t * mult, 2),
        "raison": None if ouvert else "taux de chargement sous le minimum : voie d'eau considérée comme fermée",
    }


def fret_rail_eur_t(cfg: Config, usine: Usine, crise: bool = False) -> float:
    base = usine.approvisionnement.rail.fret_eur_t
    return round(base * (1 + cfg.couts.rail_surcout_crise) if crise else base, 2)


def fret_camion_eur_t(cfg: Config, usine: Usine) -> float:
    """Camion de la part routière habituelle (blé collecté près de l'usine)."""
    return round(cfg.couts.camion_eur_t_km * usine.approvisionnement.camion.distance_km, 2)


def fret_camion_appoint_eur_t(cfg: Config, usine: Usine) -> float:
    """Camion d'appoint : il remplace la péniche, donc va chercher le blé à la même origine (même distance)."""
    a = usine.approvisionnement
    distance = a.peniche.distance_km if a.peniche.part > 0 else a.camion.distance_km
    return round(cfg.couts.camion_eur_t_km * distance, 2)


def cout_rendu_usine(cfg: Config, usine_id: str, niveau_cm: float | None, prix_ble_eur_t: float) -> dict:
    """Coût rendu usine (€/t) par mode de transport, avec le détail du calcul.

    `niveau_cm` est le niveau de la station de référence de l'usine (None si l'usine n'est pas fluviale).
    """
    usine = cfg.usines[usine_id]
    ble = prix_ble_eur_t + cfg.produits.base_regionale_ble_eur_t
    manut = cfg.couts.manutention_eur_t
    modes = {}

    if usine.approvisionnement.peniche.part > 0 and niveau_cm is not None:
        p = fret_peniche_eur_t(cfg, usine, niveau_cm)
        modes["peniche"] = {**p, "cout_rendu_eur_t": round(ble + p["fret_eur_t"] + manut, 2) if p["disponible"] else None}

    rail_normal = fret_rail_eur_t(cfg, usine)
    rail_crise = fret_rail_eur_t(cfg, usine, crise=True)
    modes["rail"] = {
        "fret_eur_t": rail_normal,
        "fret_supplementaire_eur_t": rail_crise,
        "cout_rendu_eur_t": round(ble + rail_normal + manut, 2),
        "cout_rendu_supplementaire_eur_t": round(ble + rail_crise + manut, 2),
    }
    camion = fret_camion_eur_t(cfg, usine)
    appoint = fret_camion_appoint_eur_t(cfg, usine)
    modes["camion"] = {
        "fret_eur_t": camion,
        "cout_rendu_eur_t": round(ble + camion + manut, 2),
        "fret_appoint_eur_t": appoint,
        "cout_rendu_appoint_eur_t": round(ble + appoint + manut, 2),
    }

    return {
        "usine": usine_id,
        "prix_ble_eur_t": prix_ble_eur_t,
        "base_regionale_eur_t": cfg.produits.base_regionale_ble_eur_t,
        "manutention_eur_t": manut,
        "modes": modes,
    }


def fret_moyen_plan_eur_t(cfg: Config, usine_id: str, niveau_cm: float | None) -> float:
    """Fret moyen pondéré par les parts du plan d'approvisionnement de référence (€/t)."""
    usine = cfg.usines[usine_id]
    a = usine.approvisionnement
    total, parts = 0.0, 0.0
    if a.peniche.part > 0 and niveau_cm is not None:
        p = fret_peniche_eur_t(cfg, usine, niveau_cm)
        # voie d'eau fermée : on valorise la part fluviale au fret maximal coté (hypothèse prudente, qui garde
        # le coût croissant quand l'eau baisse) ; le détail du report sur le rail et la route est dans la simulation
        fret = p["fret_eur_t"] if p["disponible"] else a.peniche.fret_base_eur_t * cfg.marche_fret.multiplicateur_max
        total += a.peniche.part * fret
        parts += a.peniche.part
    total += a.rail.part * fret_rail_eur_t(cfg, usine) + a.camion.part * fret_camion_eur_t(cfg, usine)
    parts += a.rail.part + a.camion.part
    return round(total / parts, 2) if parts else 0.0
