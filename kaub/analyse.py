"""Analyse du jour : tous les calculs, faits par du code testé, rassemblés en un dictionnaire.

Ce dictionnaire est la matière première de la note du matin, qu'elle soit rédigée par le gabarit
(mode sans IA) ou par Claude (mode agent). Chaque chiffre y figure avec sa source.
"""

from __future__ import annotations

import numpy as np

from kaub.config import Config
from kaub.format import pct
from kaub.modele import navigation as nav
from kaub.modele.couts import cout_rendu_usine
from kaub.modele.couverture import autonomie_jours
from kaub.modele.marge import marge_usine, sensibilites
from kaub.modele.options import evaluer_options, recommander
from kaub.situation import Situation

NIVEAUX_ALERTE = {"VERT": 0, "ORANGE": 1, "ROUGE": 2}


def etat_station(cfg: Config, situation: Situation, st_id: str) -> dict:
    """Niveau, capacité des péniches et prévision pour une station."""
    st = cfg.stations[st_id]
    e = situation.stations[st_id]
    niv = e.actuel_cm
    seuil_moitie = nav.niveau_pour_taux(st, cfg.bateau, 0.5)
    res = {
        "station": st_id,
        "nom": st.nom,
        "niveau_cm": round(niv, 1),
        "horodatage": e.horodatage,
        "debit_m3s": None if e.debit_m3s is None else round(e.debit_m3s, 0),
        "tendance_7j_cm_par_jour": round(e.tendance_7j_cm_par_jour, 1),
        "minimum_30j_cm": round(float(e.journalier["min"].iloc[-31:].min()), 0),
        "profondeur_chenal_cm": round(float(nav.profondeur_chenal_cm(st, niv)), 0),
        "bateau_type": cfg.bateau.nom,
        "taux_chargement": round(float(nav.taux_chargement(st, cfg.bateau, niv)), 3),
        "bateaux_pour_un": round(nav.bateaux_necessaires(st, cfg.bateau, niv), 1),
        "multiplicateur_fret": round(float(nav.multiplicateur_fret(st, cfg.bateau, cfg.marche_fret, niv)), 2),
        "seuils_cm": {
            "chargement_moitie": round(seuil_moitie, 0),
            "fin_obligation_transport": st.seuil_fin_obligation_transport_cm,
            "navigation_risquee": st.seuil_navigation_risquee_cm,
        },
        "source": e.source,
    }
    prev = situation.previsions.get(st_id)
    if prev is not None:
        a = cfg.alertes
        res["prevision"] = prev.resume()
        res["prevision"]["proba_chargement_sous_moitie_7j_dans_3_semaines"] = round(
            prev.proba_episode_sous(seuil_moitie, a.orange_jours_consecutifs, horizon=21), 2
        )
        res["prevision"]["proba_sous_navigation_risquee_7j_dans_3_semaines"] = round(
            prev.proba_episode_sous(st.seuil_navigation_risquee_cm, a.orange_jours_consecutifs, horizon=21), 2
        )
        res["prevision"]["proba_au_dessus_moitie_dans_2_semaines"] = round(float((prev.niveaux_cm[:, 13] >= seuil_moitie).mean()), 2)
    return res


def analyser_usine(cfg: Config, situation: Situation, usine_id: str, stock_initial_t: float | None = None) -> dict:
    u = cfg.usines[usine_id]
    st_id = u.approvisionnement.peniche.station if u.approvisionnement.peniche.part > 0 else None
    niveau = situation.stations[st_id].actuel_cm if st_id and st_id in situation.stations else None
    p = situation.prix
    ble = p["ble_euronext"].valeur
    gaz = p["gaz_ttf"].valeur
    co2 = p["carbone_eua"].valeur
    marge = marge_usine(cfg, usine_id, niveau, ble, gaz, co2)
    sens = sensibilites(cfg, usine_id, niveau, ble, gaz, co2, niveau_choc_cm=(niveau - 20) if niveau is not None else None)
    scenarios = situation.previsions[st_id].niveaux_cm[:, : cfg.alertes.horizon_jours] if st_id in situation.previsions else None
    options = recommander(evaluer_options(cfg, usine_id, scenarios, marge["marge_eur_t"], stock_initial_t))
    statu_quo = next(o for o in options if o["option"] == "Ne rien changer")
    a = cfg.alertes

    # Niveau d'alerte
    raisons = []
    niveau_alerte = "VERT"
    if statu_quo["proba_rupture"] >= a.rouge_proba_rupture:
        niveau_alerte = "ROUGE"
        raisons.append(f"rupture d'approvisionnement dans {pct(statu_quo['proba_rupture'])} des scénarios sans action")
    elif statu_quo["proba_rupture"] >= a.orange_proba_rupture:
        niveau_alerte = "ORANGE"
        raisons.append(f"rupture d'approvisionnement dans {pct(statu_quo['proba_rupture'])} des scénarios sans action")
    if st_id and st_id in situation.previsions:
        p_moitie = etat_station(cfg, situation, st_id)["prevision"]["proba_chargement_sous_moitie_7j_dans_3_semaines"]
        if p_moitie >= 0.5 and niveau_alerte == "VERT":
            niveau_alerte = "ORANGE"
        if p_moitie >= 0.5:
            raisons.append(f"péniches chargées à moins de 50 % pendant au moins 7 jours dans {pct(p_moitie)} des scénarios")
    if not raisons:
        raisons.append("approvisionnement sécurisé dans tous les scénarios")

    meilleure = options[0]
    for o in options:  # arrondis lisibles (l'agent cite ces valeurs telles quelles)
        for k in ("cout_moyen_eur", "cout_p90_eur", "rupture_moyenne_t", "ecart_vs_statu_quo_eur"):
            o[k] = round(o[k], 0)
        for k in ("transport_moyen_eur_t", "stock_min_jours_median"):
            o[k] = round(o[k], 1)
        o["proba_rupture"] = round(o["proba_rupture"], 2)
    return {
        "usine": usine_id,
        "nom": u.nom,
        "station_reference": st_id,
        "consommation_t_jour": u.consommation_t_jour,
        "niveau_alerte": niveau_alerte,
        "raisons_alerte": raisons,
        "cout_rendu": cout_rendu_usine(cfg, usine_id, niveau, ble),
        "marge": marge,
        "sensibilites": sens,
        "autonomie": autonomie_jours(cfg, usine_id, niveau, stock_initial_t),
        "options": options,
        "recommandation": {
            "option": meilleure["option"],
            "gain_moyen_vs_statu_quo_eur": round(-meilleure["ecart_vs_statu_quo_eur"], 0),
            "proba_rupture_avant": round(statu_quo["proba_rupture"], 2),
            "proba_rupture_apres": round(meilleure["proba_rupture"], 2),
            "a_valider_par": "le responsable logistique",
        },
    }


def analyser(cfg: Config, situation: Situation, usines: list[str] | None = None) -> dict:
    """Analyse complète du jour, prête à être rédigée."""
    stations = {s: etat_station(cfg, situation, s) for s in situation.stations}
    ids = usines or list(cfg.usines)
    res_usines = {u: analyser_usine(cfg, situation, u) for u in ids}
    alerte = max((r["niveau_alerte"] for r in res_usines.values()), key=NIVEAUX_ALERTE.get)
    pluie = None
    if situation.pluie_mm is not None:
        p = situation.pluie_mm
        pluie = {
            "cumul_7j_mm": {k: round(float(np.nansum(v.iloc[:7])), 0) for k, v in p.items()},
            "cumul_14j_mm": {k: round(float(np.nansum(v.iloc[:14])), 0) for k, v in p.items()},
            "source": "Open-Meteo, prévision météo",
        }
    return {
        "date": str(situation.date.date()),
        "mode": situation.mode,
        "alerte_globale": alerte,
        "stations": stations,
        "prix": {k: v.en_dict() for k, v in situation.prix.items()},
        "pluie": pluie,
        "usines": res_usines,
        "avertissements": situation.avertissements,
        "hypotheses": "config/hypotheses.yaml — réseau d'usines fictif, aucune donnée interne d'entreprise",
    }
