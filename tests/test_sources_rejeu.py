"""Lecture des sources (sans réseau), archivage, et rejeu de l'été 2026."""

import pandas as pd

from kaub.hydro.reconstitution import reconstituer
from kaub.rejeu import rejouer
from kaub.sources import pegelonline, stockage
from kaub.sources.prix import prix_reference
from kaub.situation import REF


def test_agregation_journaliere_et_valeur_de_5h():
    h = pd.date_range("2026-11-08T00:00", periods=96, freq="15min", tz="Europe/Berlin").tz_convert("UTC")
    brut = pd.DataFrame({"horodatage": h, "valeur": range(96)})
    j = pegelonline.journalier(brut)
    assert len(j) == 1
    assert j["valeur_0500"].iloc[0] == 20  # 5 h 00 = 21e quart d'heure
    assert j["nb_mesures"].iloc[0] == 96


def test_archivage_sans_doublon(tmp_path):
    h = pd.date_range("2026-11-08", periods=4, freq="15min", tz="UTC")
    d = pd.DataFrame({"horodatage": h, "valeur": [1, 2, 3, 4]})
    assert stockage.ajouter_mesures("KAUB", "W", d, tmp_path) == 4
    assert stockage.ajouter_mesures("KAUB", "W", d, tmp_path) == 0
    assert len(stockage.lire_serie("KAUB", "W", tmp_path)) == 4


def test_prix_de_reference():
    p = prix_reference(REF / "prix_2026-11-09.csv")
    assert p["ble_euronext"].valeur == 224.0 and p["ble_euronext"].unite == "EUR/t"
    assert p["carbone_eua"].approximation


def test_rejeu_alerte_avant_l_effondrement(cfg):
    serie, _ = reconstituer(cfg, debut="2026-05-01")
    r = rejouer(cfg, serie)
    s = r.resume
    assert s["premiere_alerte_orange"] < s["premier_passage_sous_40cm"]
    assert s["premiere_alerte_rouge"] < s["premier_passage_sous_25cm"]
    assert s["avance_orange_sur_10cm_jours"] > 21
    # a posteriori, l'option proposée par KAUB évite la rupture et coûte moins que ne rien faire
    reco = next(o for o in r.options_a_posteriori if o["recommandee_par_kaub"])
    assert reco["rupture_moyenne_t"] < 1 and reco["ecart_vs_statu_quo_eur"] < 0
