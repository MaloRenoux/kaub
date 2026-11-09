"""Rejeu de l'été 2026 : qu'aurait dit KAUB, jour après jour, pendant les basses eaux ?

Règle d'or : chaque jour, KAUB ne voit QUE le passé. Il prévoit avec la méthode de tarissement
(kaub/hydro/prevision.py), qui n'utilise que les niveaux connus ce jour-là.

Deux questions :
1. Anticipation : à partir de quand KAUB aurait-il annoncé que Kaub passerait sous 40 cm (navigation à peine
   rentable selon Contargo), puis sous 25 cm (le record de 2018), dans les trois semaines ? Combien de jours
   avant que cela n'arrive vraiment ?
   - alerte ORANGE : au moins une chance sur deux de passer sous 40 cm dans les 21 jours ;
   - alerte ROUGE  : au moins une chance sur deux de passer sous 25 cm dans les 21 jours.
2. Valeur de l'action : le jour de l'alerte ORANGE, quelle option KAUB aurait-il proposée pour l'usine A, et
   combien aurait coûté chaque option sur les niveaux réellement observés dans les six semaines suivantes ?
   Hypothèse : ce jour-là, l'usine A a son stock habituel (12 jours) et son plan habituel.

Limites : la série de l'été est reconstituée (voir kaub/hydro/reconstitution.py), et la prévision de
tarissement ne voit pas venir la pluie : elle est prudente, ce qui avance les alertes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from kaub.config import Config
from kaub.hydro.prevision import prevision_tarissement
from kaub.modele.options import evaluer_options, options_candidates, recommander

POIDS_SCENARIOS = np.array([0.25, 0.50, 0.25])  # sec, central, persistance
SEUIL_ORANGE_CM = 40.0  # Contargo : en dessous, la navigation n'a presque plus de sens
SEUIL_ROUGE_CM = 25.0  # record de 2018 (25 cm le 22 octobre 2018)
HORIZON_ALERTE = 21


@dataclass
class ResultatRejeu:
    jours: pd.DataFrame
    resume: dict
    options_ex_ante: list[dict]  # ce que KAUB voyait le jour de l'alerte (sa prévision)
    options_a_posteriori: list[dict]  # ce que chaque option aurait vraiment coûté


def _premiere_date(masque: pd.Series):
    return masque.index[masque.values][0] if masque.any() else None


def rejouer(
    cfg: Config,
    serie: pd.DataFrame,
    usine: str = "A",
    debut: str = "2026-06-01",
    fin: str = "2026-10-31",
    marge_eur_t: float = 50.0,
) -> ResultatRejeu:
    u = cfg.usines[usine]
    st_id = u.approvisionnement.peniche.station
    st = cfg.stations[st_id]
    H = cfg.alertes.horizon_jours
    niveaux = serie["niveau_cm"].astype(float)

    lignes = []
    for jour in pd.date_range(debut, fin, freq="D"):
        prev = prevision_tarissement(st_id, st, niveaux[niveaux.index <= jour], horizon=H)
        mins = prev.niveaux_cm[:, :HORIZON_ALERTE].min(axis=1)
        p40 = float(POIDS_SCENARIOS @ (mins < SEUIL_ORANGE_CM))
        p25 = float(POIDS_SCENARIOS @ (mins < SEUIL_ROUGE_CM))
        alerte = "ROUGE" if p25 >= 0.5 else "ORANGE" if p40 >= 0.5 else "VERT"
        lignes.append(
            dict(
                date=jour,
                niveau_cm=float(niveaux.loc[jour]),
                source_niveau=serie.loc[jour, "source"],
                prevision_centrale_j21_cm=round(float(prev.niveaux_cm[1, HORIZON_ALERTE - 1]), 1),
                proba_sous_40cm_21j=p40,
                proba_sous_25cm_21j=p25,
                alerte=alerte,
            )
        )
    jours = pd.DataFrame(lignes).set_index("date")

    reel = niveaux[(niveaux.index >= debut) & (niveaux.index <= fin)]
    d_orange = _premiere_date(jours.alerte.isin(["ORANGE", "ROUGE"]))
    d_rouge = _premiere_date(jours.alerte == "ROUGE")
    d_sous40 = _premiere_date(reel < SEUIL_ORANGE_CM)
    d_sous25 = _premiere_date(reel < SEUIL_ROUGE_CM)
    d_sous10 = _premiere_date(reel <= 10)

    def ecart(a, b):
        return None if a is None or b is None else int((b - a).days)

    options_ex_ante, options_a_posteriori, reco = [], [], None
    if d_orange is not None:
        prev = prevision_tarissement(st_id, st, niveaux[niveaux.index <= d_orange], horizon=H)
        plans = options_candidates(cfg, usine)
        options_ex_ante = recommander(evaluer_options(cfg, usine, prev.niveaux_cm, marge_eur_t, plans=plans, poids=POIDS_SCENARIOS))
        reco = options_ex_ante[0]["option"]
        realise = niveaux[niveaux.index > d_orange].iloc[:H].values
        options_a_posteriori = [o for o in evaluer_options(cfg, usine, realise, marge_eur_t, plans=plans) if not o["sans_effet"]]
        for o in options_a_posteriori:
            o["recommandee_par_kaub"] = o["option"] == reco

    resume = {
        "usine": usine,
        "station": st_id,
        "periode": f"{debut} → {fin}",
        "seuils": {"orange_cm": SEUIL_ORANGE_CM, "rouge_cm": SEUIL_ROUGE_CM, "horizon_jours": HORIZON_ALERTE},
        "premiere_alerte_orange": None if d_orange is None else str(d_orange.date()),
        "niveau_premiere_alerte_orange_cm": None if d_orange is None else round(float(niveaux.loc[d_orange]), 0),
        "premiere_alerte_rouge": None if d_rouge is None else str(d_rouge.date()),
        "niveau_premiere_alerte_rouge_cm": None if d_rouge is None else round(float(niveaux.loc[d_rouge]), 0),
        "premier_passage_sous_40cm": None if d_sous40 is None else str(d_sous40.date()),
        "premier_passage_sous_25cm": None if d_sous25 is None else str(d_sous25.date()),
        "premier_passage_sous_10cm": None if d_sous10 is None else str(d_sous10.date()),
        "avance_orange_sur_40cm_jours": ecart(d_orange, d_sous40),
        "avance_rouge_sur_25cm_jours": ecart(d_rouge, d_sous25),
        "avance_orange_sur_10cm_jours": ecart(d_orange, d_sous10),
        "minimum_aout_cm": round(float(reel.loc["2026-08-01":"2026-08-31"].min()), 0),
        "date_minimum_aout": str(reel.loc["2026-08-01":"2026-08-31"].idxmin().date()),
        "minimum_ete_cm": round(float(reel.min()), 0),
        "date_minimum_ete": str(reel.idxmin().date()),
        "recommandation_jour_alerte": reco,
        "methode_prevision": "tarissement exponentiel vers le débit de base (scénarios sec 25 %, central 50 %, persistance 25 %), données passées uniquement",
    }
    return ResultatRejeu(jours, resume, options_ex_ante, options_a_posteriori)
