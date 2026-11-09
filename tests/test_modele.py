"""Modèle de coût, simulation du stock, marge et options."""

import numpy as np
import pytest

from kaub.modele.couts import cout_rendu_usine
from kaub.modele.couverture import Plan, autonomie_jours, simuler
from kaub.modele.marge import marge_usine
from kaub.modele.options import evaluer_options, recommander


def test_bilan_matiere_equilibre(cfg):
    """Stock final = stock initial + arrivées − refus − production, au kilo près."""
    traj = np.linspace(80, 10, 42)
    sim = simuler(cfg, "A", traj, Plan(bascule_rail=0.3, camions_appoint=True))
    j = sim.jours
    initial = cfg.usines["A"].stock_initial_jours * cfg.usines["A"].consommation_t_jour
    entrees = (j.arrivees_peniche_t + j.arrivees_rail_t + j.arrivees_camion_t - j.refus_silo_plein_t).sum()
    assert j.stock_t.iloc[-1] == pytest.approx(initial + entrees - j.production_t.sum())
    assert (j.production_t + j.rupture_t).round(6).eq(cfg.usines["A"].consommation_t_jour).all()


def test_jamais_sous_le_stock_de_securite(cfg):
    sim = simuler(cfg, "A", np.full(42, -50.0))  # voie d'eau fermée six semaines
    secu = cfg.usines["A"].stock_securite_jours * cfg.usines["A"].consommation_t_jour
    assert sim.jours.stock_t.min() >= secu - 1e-6
    assert sim.totaux["rupture_t"] > 0


def test_eaux_normales_pas_de_rupture(cfg):
    for u in cfg.usines:
        assert simuler(cfg, u, np.full(42, 250.0)).totaux["rupture_t"] == 0


def test_silo_jamais_deborde(cfg):
    sim = simuler(cfg, "A", np.full(42, 300.0), Plan(avance_peniche_t_jour=5000, avance_jours=30))
    assert sim.jours.stock_t.max() <= cfg.usines["A"].capacite_silo_t + 1e-6


def test_cout_rendu_monte_quand_l_eau_baisse(cfg):
    hauts = cout_rendu_usine(cfg, "A", 200, 224)["modes"]["peniche"]["cout_rendu_eur_t"]
    bas = cout_rendu_usine(cfg, "A", 20, 224)["modes"]["peniche"]["cout_rendu_eur_t"]
    assert bas > hauts


def test_marge_decomposee(cfg):
    m = marge_usine(cfg, "C", None, 224, 87.01, 83.04)
    assert m["marge_eur_t"] == pytest.approx(m["valeur_produits_eur_t"] - m["ble_rendu_eur_t"] - m["gaz_eur_t"] - m["carbone_eur_t"], abs=0.02)
    # gaz : 0,9 MWh/t × 87,01 €/MWh
    assert m["gaz_eur_t"] == pytest.approx(78.31, abs=0.01)


def test_marge_baisse_quand_le_gaz_monte(cfg):
    assert marge_usine(cfg, "A", 50, 224, 100, 80)["marge_eur_t"] < marge_usine(cfg, "A", 50, 224, 80, 80)["marge_eur_t"]


def test_options_et_recommandation(cfg):
    scenarios = np.vstack([np.full(42, 15.0), np.full(42, 30.0), np.linspace(15, 120, 42)])
    res = recommander(evaluer_options(cfg, "A", scenarios, marge_eur_t=40))
    statu = next(o for o in res if o["option"] == "Ne rien changer")
    best = res[0]
    assert statu["proba_rupture"] > 0.5
    assert best["proba_rupture"] <= 0.10
    assert best["ecart_vs_statu_quo_eur"] < 0
    # une option « sans effet » (péniches qui ne peuvent plus charger davantage) n'est jamais recommandée
    assert not best["sans_effet"]


def test_autonomie(cfg):
    a = autonomie_jours(cfg, "A", 11.0)
    assert a["deficit_t_jour"] > 0 and a["autonomie_jours"] > 0
    assert autonomie_jours(cfg, "C", None)["autonomie_jours"] is None
