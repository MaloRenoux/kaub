"""Projection du stock d'une usine jour par jour, et coût logistique associé.

Chaque jour t :
  stock(t+1) = stock(t) + arrivées péniche + arrivées rail + arrivées camion − consommation

- Arrivées péniche : le plan prévoit une quantité par jour ; la flotte réellement disponible charge
  moins quand l'eau baisse : livrable = min(prévu, flotte_flexible × part fluviale × consommation × taux de chargement).
  Ce qui ne peut pas être chargé n'arrive pas (il faut le remplacer par un autre mode).
- Arrivées rail et camion : fixées par le plan ; les bascules et les camions d'appoint arrivent après leur délai.
- Consommation : normale, sauf si le stock tomberait sous le stock de sécurité ; on réduit alors la production.
  Les tonnes non produites forment la « rupture ».

Le plan (classe Plan) décrit les décisions possibles : avancer des livraisons, basculer sur le rail,
appeler des camions. C'est ce qui permet de chiffrer et de comparer les options.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from kaub.config import Config
from kaub.modele import navigation as nav
from kaub.modele.couts import fret_camion_appoint_eur_t, fret_camion_eur_t, fret_rail_eur_t


@dataclass(frozen=True)
class Plan:
    """Écarts au plan d'approvisionnement de référence."""

    nom: str = "Ne rien changer"
    avance_peniche_t_jour: float = 0.0  # tonnes fluviales en plus chaque jour…
    avance_jours: int = 0  # … pendant les N premiers jours
    bascule_rail: float = 0.0  # part de la consommation transférée de la péniche vers le rail
    camions_appoint: bool = False  # camions d'urgence pour remonter le stock vers sa cible
    description: str = ""


@dataclass
class Simulation:
    usine: str
    plan: Plan
    jours: pd.DataFrame  # une ligne par jour
    totaux: dict = field(default_factory=dict)


def simuler(
    cfg: Config,
    usine_id: str,
    niveaux_cm: np.ndarray | None,
    plan: Plan = Plan(),
    marge_eur_t: float = 0.0,
    stock_initial_t: float | None = None,
    dates: pd.DatetimeIndex | None = None,
    horizon: int | None = None,
) -> Simulation:
    """Projette le stock et les coûts sur l'horizon, pour une trajectoire de niveaux de la station de l'usine."""
    u = cfg.usines[usine_id]
    c = cfg.couts
    a = u.approvisionnement
    conso = u.consommation_t_jour
    H = horizon or (len(niveaux_cm) if niveaux_cm is not None else cfg.alertes.horizon_jours)
    stock = u.stock_initial_jours * conso if stock_initial_t is None else stock_initial_t
    secu = u.stock_securite_jours * conso
    cible = secu + 4 * conso  # niveau visé par les camions d'appoint
    fluviale = a.peniche.part > 0 and a.peniche.station is not None and niveaux_cm is not None
    station = cfg.stations[a.peniche.station] if fluviale else None

    rail_supp = min(plan.bascule_rail, c.rail_part_max_supplementaire) * conso
    fret_rail = fret_rail_eur_t(cfg, u)
    fret_rail_supp = fret_rail_eur_t(cfg, u, crise=True)
    fret_camion = fret_camion_eur_t(cfg, u)
    fret_appoint = fret_camion_appoint_eur_t(cfg, u)
    penalite = max(marge_eur_t, 0.0) + c.penalite_rupture_eur_t

    lignes = []
    for t in range(H):
        niveau = float(niveaux_cm[t]) if fluviale else np.nan
        # --- péniche
        if fluviale:
            taux = float(nav.taux_chargement(station, cfg.bateau, niveau))
            ouvert = taux >= cfg.marche_fret.taux_chargement_min_navigation
            prevu = a.peniche.part * conso
            if t >= c.rail_delai_jours:
                prevu = max(prevu - rail_supp, 0.0)
            if t < plan.avance_jours:
                prevu += plan.avance_peniche_t_jour
            capacite = cfg.marche_fret.flotte_flexible * a.peniche.part * conso * taux if ouvert else 0.0
            peniche = min(prevu, capacite)
            mult = float(nav.multiplicateur_fret(station, cfg.bateau, cfg.marche_fret, niveau))
            cout_peniche = peniche * (a.peniche.fret_base_eur_t * mult + c.manutention_eur_t)
        else:
            taux, mult, peniche, cout_peniche = np.nan, np.nan, 0.0, 0.0
        # --- rail (bascule effective après le délai d'obtention des sillons)
        rail_base = a.rail.part * conso
        rail_bascule = rail_supp if t >= c.rail_delai_jours else 0.0
        cout_rail = rail_base * (fret_rail + c.manutention_eur_t) + rail_bascule * (fret_rail_supp + c.manutention_eur_t)
        # --- camion (part de base + appoint si le stock passe sous la cible)
        camion = a.camion.part * conso
        appoint = 0.0
        if plan.camions_appoint and t >= c.camion_delai_jours:
            attendu = stock + peniche + rail_base + rail_bascule + camion - conso
            appoint = float(np.clip(cible - attendu, 0.0, c.camion_max_t_jour))
        cout_camion = camion * (fret_camion + c.manutention_eur_t) + appoint * (fret_appoint + c.manutention_eur_t)
        arrivees = peniche + rail_base + rail_bascule + camion + appoint
        # --- silo plein : on ne peut pas recevoir plus que la place disponible
        trop_plein = max(stock + arrivees - u.capacite_silo_t, 0.0)
        # --- consommation, réduite si l'on passerait sous le stock de sécurité
        disponible = stock + arrivees - trop_plein
        production = min(conso, max(disponible - secu, 0.0))
        rupture = conso - production
        stock = disponible - production
        cout_stockage = stock * c.stockage_eur_t_semaine / 7
        lignes.append(
            dict(
                jour=t,
                niveau_cm=niveau,
                taux_chargement=taux,
                multiplicateur_fret=mult,
                arrivees_peniche_t=peniche,
                arrivees_rail_t=rail_base + rail_bascule,
                arrivees_camion_t=camion + appoint,
                dont_appoint_camion_t=appoint,
                refus_silo_plein_t=trop_plein,
                production_t=production,
                rupture_t=rupture,
                stock_t=stock,
                stock_jours=stock / conso,
                cout_transport_eur=cout_peniche + cout_rail + cout_camion,
                cout_stockage_eur=cout_stockage,
                cout_rupture_eur=rupture * penalite,
            )
        )
    jours = pd.DataFrame(lignes)
    if dates is not None:
        jours.insert(0, "date", dates[:H])
    rupture_tot = float(jours.rupture_t.sum())
    premier = jours.index[jours.rupture_t > 1e-6]
    totaux = {
        "cout_transport_eur": float(jours.cout_transport_eur.sum()),
        "cout_stockage_eur": float(jours.cout_stockage_eur.sum()),
        "cout_rupture_eur": float(jours.cout_rupture_eur.sum()),
        "cout_total_eur": float(jours[["cout_transport_eur", "cout_stockage_eur", "cout_rupture_eur"]].sum().sum()),
        "rupture_t": rupture_tot,
        "premier_jour_rupture": int(premier[0]) if len(premier) else None,
        "stock_min_jours": float(jours.stock_jours.min()),
        "tonnes_recues": float(jours[["arrivees_peniche_t", "arrivees_rail_t", "arrivees_camion_t"]].sum().sum() - jours.refus_silo_plein_t.sum()),
    }
    return Simulation(usine_id, plan, jours, totaux)


def autonomie_jours(cfg: Config, usine_id: str, niveau_cm: float | None, stock_t: float | None = None) -> dict:
    """Jours d'autonomie si le niveau reste celui d'aujourd'hui (aucune action, aucune pluie).

    = (stock − stock de sécurité) / déficit journalier, où le déficit est la consommation moins ce qui
    peut encore arriver par péniche, rail et camion au rythme du plan.
    """
    u = cfg.usines[usine_id]
    conso = u.consommation_t_jour
    stock = u.stock_initial_jours * conso if stock_t is None else stock_t
    sim = simuler(cfg, usine_id, np.full(1, niveau_cm if niveau_cm is not None else np.nan), stock_initial_t=stock, horizon=1)
    j = sim.jours.iloc[0]
    arrivees = j.arrivees_peniche_t + j.arrivees_rail_t + j.arrivees_camion_t
    deficit = conso - arrivees
    reserve = stock - u.stock_securite_jours * conso
    return {
        "usine": usine_id,
        "stock_t": round(float(stock), 0),
        "stock_jours_consommation": round(float(stock / conso), 1),
        "arrivees_possibles_t_jour": round(float(arrivees), 0),
        "deficit_t_jour": round(float(max(deficit, 0.0)), 0),
        "autonomie_jours": None if deficit <= 0 else round(float(reserve / deficit), 1),
    }
