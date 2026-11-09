"""Hydrologie : courbe de tarage, correction de GloFAS, prévisions et reconstitution."""

import numpy as np
import pandas as pd
import pytest

from kaub.hydro.prevision import prevision_tarissement
from kaub.hydro.reconstitution import ancrer, charger_ancres, reconstituer
from kaub.hydro.tarage import caler_courbe


def test_courbe_kaub_passe_par_l_annuaire(cfg):
    c = cfg.stations["KAUB"].tarage.courbe()
    # Annuaire hydrologique BfG 2025 : NW 79 cm ↔ NQ 784 m3/s ; HW 498 cm ↔ HQ 3 720 m3/s
    assert float(c.niveau(784)) == pytest.approx(79, abs=2)
    assert float(c.niveau(3720)) == pytest.approx(498, abs=5)
    # et le module MQ 1 640 m3/s tombe dans la plage des niveaux moyens (MW 208 cm)
    assert 190 <= float(c.niveau(1640)) <= 250


def test_courbe_inversible(cfg):
    c = cfg.stations["DUISBURG-RUHRORT"].tarage.courbe()
    for w in (120, 150, 240, 400):
        assert float(c.niveau(c.debit(w))) == pytest.approx(w, abs=1e-6)


def test_calage_retrouve_une_courbe_connue():
    vraie_W0, vraie_c, vraie_n = -150.0, 0.2, 1.5
    w = np.linspace(0, 300, 40)
    q = vraie_c * (w - vraie_W0) ** vraie_n
    courbe, err = caler_courbe(w, q)
    assert err < 1e-3
    assert courbe.W0 == pytest.approx(vraie_W0, rel=1e-3)


def test_prevision_ensemble_du_9_novembre(situation):
    p = situation.previsions["KAUB"]
    assert p.niveaux_cm.shape[0] == 50
    assert p.dates[0] == pd.Timestamp("2026-11-10")
    # recollage : le premier jour prévu reste proche du niveau mesuré (11 cm)
    assert abs(np.median(p.niveaux_cm[:, 0]) - 11) < 15
    assert 0 <= p.proba_episode_sous(124, 7, horizon=21) <= 1


def test_tarissement_ne_regarde_pas_l_avenir(cfg):
    st = cfg.stations["KAUB"]
    idx = pd.date_range("2026-07-01", periods=30)
    passe = pd.Series(np.linspace(80, 50, 30), index=idx)
    p1 = prevision_tarissement("KAUB", st, passe)
    # ajouter des données APRÈS le jour J ne doit rien changer si on coupe au jour J
    futur = pd.concat([passe, pd.Series([200.0] * 5, index=pd.date_range("2026-07-31", periods=5))])
    p2 = prevision_tarissement("KAUB", st, futur[futur.index <= idx[-1]])
    assert np.allclose(p1.niveaux_cm, p2.niveaux_cm)
    # en décrue, le scénario sec est sous le scénario central, lui-même sous la persistance
    assert p1.niveaux_cm[0, -1] < p1.niveaux_cm[1, -1] < p1.niveaux_cm[2, -1]
    # et le débit de base empêche de descendre sous le plancher du fleuve
    assert p1.niveaux_cm.min() >= float(st.tarage.courbe().niveau(st.debit_plancher_m3s)) - 1e-6


def test_ancrage_passe_par_les_releves():
    idx = pd.date_range("2026-07-01", periods=60)
    brute = pd.Series(np.linspace(100, 0, 60), index=idx)
    ancres = pd.DataFrame({"date": [idx[10], idx[40]], "niveau_cm": [70.0, 20.0]})
    a = ancrer(brute, ancres)
    assert a.loc[idx[10]] == pytest.approx(70.0)
    assert a.loc[idx[40]] == pytest.approx(20.0)


def test_reconstitution_ete(cfg):
    serie, bilan = reconstituer(cfg, debut="2026-06-01")
    # les mesures officielles sont reprises telles quelles
    assert (serie.loc["2026-10-15", "source"]).startswith("mesure officielle")
    # validation croisée : erreur moyenne inférieure à 10 cm
    assert bilan["erreur_validation_croisee_cm"]["moyenne_absolue"] < 10
    # contrôle indépendant : minimum d'août autour de 6 cm à la mi-août (relevé non utilisé pour l'ancrage)
    aout = serie.loc["2026-08-01":"2026-08-31", "niveau_cm"]
    assert aout.idxmin() in pd.date_range("2026-08-12", "2026-08-20")
    assert abs(aout.min() - 6) <= 5
    # la presse recoupe les mesures officielles
    for c in bilan["controle_presse_vs_officiel"]:
        assert abs(c["presse_cm"] - c["officiel_moyenne_jour_cm"]) < 5
    assert len(charger_ancres()) >= 10
