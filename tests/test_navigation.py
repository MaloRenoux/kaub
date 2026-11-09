"""Le modèle de navigation reproduit-il les faits publiés ?"""

import pytest

from kaub.modele import navigation as nav


def test_formule_contargo_kaub(cfg):
    # Contargo : TuGlW 190 − GlW 78 + 60 = 172 cm. Avec le GlW actuel (77 cm) : 173 cm.
    assert float(nav.profondeur_chenal_cm(cfg.stations["KAUB"], 60)) == pytest.approx(173)


def test_profondeur_annoncee_le_14_aout(cfg):
    # Le 14/08/2026, à 8 cm, le service des voies navigables annonçait « un peu plus de 1,20 m ».
    assert 119 <= float(nav.profondeur_chenal_cm(cfg.stations["KAUB"], 8)) <= 125


def test_chargement_croit_avec_le_niveau(cfg):
    st, b = cfg.stations["KAUB"], cfg.bateau
    taux = [float(nav.taux_chargement(st, b, w)) for w in (-20, 0, 25, 60, 100, 150, 200, 300)]
    assert taux == sorted(taux)
    assert taux[0] == 0.0 and taux[-1] == 1.0


def test_plein_chargement_vers_150_cm(cfg):
    # Presse : la plupart des bateaux chargent à plein vers 150 cm à Kaub.
    assert float(nav.taux_chargement(cfg.stations["KAUB"], cfg.bateau, 150)) >= 0.8


def test_fret_calibre_sur_la_presse(cfg):
    # VerkehrsRundschau, 4/08/2026 : fret multiplié par 3 à 4 quand Kaub était vers 25 cm.
    m = float(nav.multiplicateur_fret(cfg.stations["KAUB"], cfg.bateau, cfg.marche_fret, 25))
    assert 3.0 <= m <= 4.0


def test_fret_plafonne_et_croissant(cfg):
    st, b, m = cfg.stations["KAUB"], cfg.bateau, cfg.marche_fret
    mults = [float(nav.multiplicateur_fret(st, b, m, w)) for w in (300, 150, 60, 25, 10, -10, -50)]
    assert mults == sorted(mults)
    assert mults[-1] == m.multiplicateur_max


def test_niveau_pour_taux_est_l_inverse(cfg):
    st, b = cfg.stations["KAUB"], cfg.bateau
    w = nav.niveau_pour_taux(st, b, 0.5)
    assert float(nav.taux_chargement(st, b, w)) == pytest.approx(0.5, abs=1e-6)
