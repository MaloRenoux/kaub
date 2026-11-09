"""Marge variable d'une usine par tonne de blé transformée.

marge = valeur des produits − blé rendu usine − gaz − carbone

- gaz     = MWh de gaz par tonne × prix du gaz TTF (Title Transfer Facility, marché de référence européen)
- carbone = MWh × facteur d'émission (t CO2/MWh) × part NON couverte par les quotas gratuits × prix du quota
            EUA (European Union Allowance, quota d'émission du marché carbone européen)

C'est une marge sur coûts variables : main-d'œuvre, amortissements et autres frais fixes ne sont pas déduits.
"""

from __future__ import annotations

from kaub.config import Config
from kaub.modele.couts import fret_moyen_plan_eur_t


def marge_usine(
    cfg: Config,
    usine_id: str,
    niveau_cm: float | None,
    prix_ble_eur_t: float,
    prix_gaz_eur_mwh: float,
    prix_co2_eur_t: float,
) -> dict:
    """Décomposition de la marge (€/t de blé) et marge journalière (€/jour) au plan de référence."""
    e = cfg.energie
    usine = cfg.usines[usine_id]
    fret = fret_moyen_plan_eur_t(cfg, usine_id, niveau_cm)
    ble_rendu = prix_ble_eur_t + cfg.produits.base_regionale_ble_eur_t + fret + cfg.couts.manutention_eur_t
    gaz = e.gaz_mwh_par_t_ble * prix_gaz_eur_mwh
    carbone = e.gaz_mwh_par_t_ble * e.facteur_emission_t_co2_par_mwh * (1 - e.part_quotas_gratuits) * prix_co2_eur_t
    valeur = cfg.produits.valeur_eur_par_t_ble
    marge = valeur - ble_rendu - gaz - carbone
    return {
        "usine": usine_id,
        "valeur_produits_eur_t": round(valeur, 2),
        "ble_rendu_eur_t": round(ble_rendu, 2),
        "dont_fret_moyen_eur_t": round(fret, 2),
        "gaz_eur_t": round(gaz, 2),
        "carbone_eur_t": round(carbone, 2),
        "marge_eur_t": round(marge, 2),
        "marge_eur_jour": round(marge * usine.consommation_t_jour, 0),
    }


def sensibilites(
    cfg: Config,
    usine_id: str,
    niveau_cm: float | None,
    prix_ble_eur_t: float,
    prix_gaz_eur_mwh: float,
    prix_co2_eur_t: float,
    hausse_gaz: float = 0.20,
    hausse_ble_eur_t: float = 10.0,
    niveau_choc_cm: float | None = None,
) -> dict:
    """Effet sur la marge (€/t et €/jour) de quelques chocs, un par un puis combinés."""
    base = marge_usine(cfg, usine_id, niveau_cm, prix_ble_eur_t, prix_gaz_eur_mwh, prix_co2_eur_t)
    conso = cfg.usines[usine_id].consommation_t_jour

    def ecart(**kw):
        args = dict(niveau_cm=niveau_cm, prix_ble_eur_t=prix_ble_eur_t, prix_gaz_eur_mwh=prix_gaz_eur_mwh, prix_co2_eur_t=prix_co2_eur_t)
        args.update(kw)
        m = marge_usine(cfg, usine_id, **args)
        d = m["marge_eur_t"] - base["marge_eur_t"]
        return {"marge_eur_t": m["marge_eur_t"], "ecart_eur_t": round(d, 2), "ecart_eur_jour": round(d * conso, 0)}

    res = {
        "base": base,
        f"gaz_plus_{int(hausse_gaz * 100)}pct": ecart(prix_gaz_eur_mwh=prix_gaz_eur_mwh * (1 + hausse_gaz)),
        f"ble_plus_{int(hausse_ble_eur_t)}eur": ecart(prix_ble_eur_t=prix_ble_eur_t + hausse_ble_eur_t),
    }
    if niveau_choc_cm is not None and niveau_cm is not None:
        res[f"rhin_a_{int(niveau_choc_cm)}cm"] = ecart(niveau_cm=niveau_choc_cm)
        res["combine"] = ecart(prix_gaz_eur_mwh=prix_gaz_eur_mwh * (1 + hausse_gaz), niveau_cm=niveau_choc_cm)
    return res
