"""Chiffrage des options sur l'ensemble des scénarios de niveau d'eau.

Pour chaque option (un « plan ») et chaque scénario de la prévision d'ensemble (50 trajectoires du Rhin),
on simule six semaines de stock et de coûts. On obtient pour chaque option :
- le coût moyen (transport + stockage + rupture), et l'écart avec « ne rien changer » ;
- la probabilité de rupture (part des scénarios où l'usine doit réduire sa production) ;
- les tonnes de rupture attendues, et le coût dans un mauvais scénario (90e centile).

Une option est recommandée si elle réduit le coût moyen ; à coût proche, la moins risquée l'emporte.
"""

from __future__ import annotations

import numpy as np

from kaub.config import Config
from kaub.format import pct
from kaub.modele.couts import fret_camion_appoint_eur_t
from kaub.modele.couverture import Plan, simuler


def options_candidates(cfg: Config, usine_id: str) -> list[Plan]:
    """La liste des options étudiées pour une usine (dépend de ses modes de transport)."""
    u = cfg.usines[usine_id]
    a = u.approvisionnement
    conso = u.consommation_t_jour
    max_rail = cfg.couts.rail_part_max_supplementaire
    plans = [Plan(description="On garde le plan d'approvisionnement actuel.")]
    if a.peniche.part > 0 and a.peniche.station:
        surplus = (cfg.marche_fret.flotte_flexible - 1) * a.peniche.part * conso
        plans += [
            Plan(
                nom="Avancer des livraisons fluviales",
                avance_peniche_t_jour=surplus,
                avance_jours=10,
                description=f"Affréter des péniches en plus pendant 10 jours (jusqu'à {surplus:.0f} t/jour) tant qu'elles chargent encore.",
            ),
            Plan(
                nom=f"Basculer {pct(max_rail)} des volumes sur le rail",
                bascule_rail=max_rail,
                description=f"Transférer {pct(max_rail)} de la consommation de la péniche vers le rail, effectif après {cfg.couts.rail_delai_jours} jours.",
            ),
            Plan(
                nom="Avancer les péniches et basculer sur le rail",
                avance_peniche_t_jour=surplus,
                avance_jours=10,
                bascule_rail=max_rail,
                description="Combinaison des deux options précédentes.",
            ),
        ]
    plans += [
        Plan(
            nom="Camions d'appoint",
            camions_appoint=True,
            description=(
                f"Appeler jusqu'à {cfg.couts.camion_max_t_jour:.0f} t/jour de camions ({fret_camion_appoint_eur_t(cfg, u):.0f} €/t de fret) "
                f"dès que le stock passe sous sa cible (délai {cfg.couts.camion_delai_jours} jours)."
            ),
        )
    ]
    if a.peniche.part > 0 and a.peniche.station:
        plans.append(
            Plan(
                nom="Rail et camions d'appoint",
                bascule_rail=max_rail,
                camions_appoint=True,
                description="Bascule sur le rail, complétée par des camions tant que le rail n'est pas en place.",
            )
        )
    return plans


def evaluer_options(
    cfg: Config,
    usine_id: str,
    scenarios_cm: np.ndarray | None,
    marge_eur_t: float,
    stock_initial_t: float | None = None,
    plans: list[Plan] | None = None,
    poids: list[float] | None = None,
) -> list[dict]:
    """Évalue chaque option sur chaque scénario. `scenarios_cm` : tableau (nb scénarios × nb jours).

    `poids` (facultatif) : probabilité de chaque scénario ; par défaut, scénarios équiprobables.
    """
    plans = plans or options_candidates(cfg, usine_id)
    if scenarios_cm is None:
        scenarios = [None]
    else:
        scenarios = list(np.atleast_2d(scenarios_cm))
    w = np.full(len(scenarios), 1.0 / len(scenarios)) if poids is None else np.asarray(poids, dtype=float) / np.sum(poids)
    resultats = []
    for plan in plans:
        totaux = [
            simuler(cfg, usine_id, s, plan, marge_eur_t, stock_initial_t, horizon=None if s is not None else cfg.alertes.horizon_jours).totaux
            for s in scenarios
        ]
        couts = np.array([t["cout_total_eur"] for t in totaux])
        ruptures = np.array([t["rupture_t"] for t in totaux])
        recues = np.array([t["tonnes_recues"] for t in totaux])
        transport = np.array([t["cout_transport_eur"] for t in totaux])
        resultats.append(
            {
                "option": plan.nom,
                "description": plan.description,
                "cout_moyen_eur": float(w @ couts),
                "cout_p90_eur": _quantile_pondere(couts, w, 0.9),
                "transport_moyen_eur_t": float((w @ transport) / max(w @ recues, 1.0)),
                "proba_rupture": float(w @ (ruptures > 1.0)),
                "rupture_moyenne_t": float(w @ ruptures),
                "stock_min_jours_median": _quantile_pondere(np.array([t["stock_min_jours"] for t in totaux]), w, 0.5),
                "nb_scenarios": len(scenarios),
            }
        )
    base = resultats[0]["cout_moyen_eur"]
    for i, r in enumerate(resultats):
        r["ecart_vs_statu_quo_eur"] = r["cout_moyen_eur"] - base
        # Une option qui donne exactement le même résultat qu'une option plus simple n'apporte rien
        # aujourd'hui (ex. : avancer des péniches quand elles ne peuvent plus charger davantage).
        r["sans_effet"] = any(
            abs(r["cout_moyen_eur"] - p["cout_moyen_eur"]) < 1.0 and abs(r["rupture_moyenne_t"] - p["rupture_moyenne_t"]) < 0.5
            for p in resultats[:i]
        )
    return resultats


def _quantile_pondere(valeurs: np.ndarray, poids: np.ndarray, q: float) -> float:
    ordre = np.argsort(valeurs)
    cumul = np.cumsum(poids[ordre])
    return float(valeurs[ordre][np.searchsorted(cumul, q - 1e-12)])


def recommander(resultats: list[dict], risque_max: float = 0.10) -> list[dict]:
    """Classe les options.

    Règle (un « taux de service » minimal, classique en logistique) : on cherche d'abord l'option la moins
    chère en moyenne parmi celles qui gardent la probabilité de rupture sous `risque_max` (10 %) ; viennent
    ensuite les autres, de la moins chère à la plus chère. Les options sans effet propre passent en dernier.
    """
    def cle(r):
        return (r.get("sans_effet", False), r["proba_rupture"] > risque_max, r["cout_moyen_eur"])
    return sorted(resultats, key=cle)
