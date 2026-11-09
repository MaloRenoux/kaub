"""Les outils que Claude peut appeler. Chacun enveloppe une fonction testée du modèle.

Le modèle d'IA choisit quels outils appeler et dans quel ordre (c'est ce qui en fait un agent), mais il
ne calcule rien lui-même : tous les chiffres viennent d'ici. Chaque appel est enregistré dans un registre,
que le vérificateur relit ensuite pour contrôler la note.

Deux outils « écrivent » : ils déposent une alerte ou un brouillon de message dans le dossier sorties/.
Rien n'est jamais envoyé : un humain relit et décide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from anthropic import beta_tool

from kaub import journal
from kaub.config import RACINE, Config
from kaub.modele.couts import cout_rendu_usine
from kaub.modele.couverture import simuler
from kaub.modele.marge import marge_usine
from kaub.situation import Situation

SORTIES = RACINE / "sorties"


@dataclass
class Registre:
    """Trace de tous les appels d'outils (nom, arguments, résultat)."""

    appels: list[dict] = field(default_factory=list)

    def noter(self, nom: str, arguments: dict, resultat) -> str:
        self.appels.append({"outil": nom, "arguments": arguments, "resultat": resultat})
        return json.dumps(resultat, ensure_ascii=False, default=float)

    @property
    def resultats(self) -> list:
        return [a["resultat"] for a in self.appels]


@dataclass
class Contexte:
    cfg: Config
    situation: Situation
    analyse: dict
    registre: Registre = field(default_factory=Registre)
    dossier_sorties: Path = SORTIES


def _chemin_affiche(f: Path) -> str:
    try:
        return str(f.relative_to(RACINE))
    except ValueError:
        return str(f)


def _trajectoire(ctx: Contexte, usine: str, scenario: str, niveau_cm: float | None, fermeture_jours: int) -> tuple[np.ndarray | None, str]:
    u = ctx.cfg.usines[usine]
    st = u.approvisionnement.peniche.station if u.approvisionnement.peniche.part > 0 else None
    H = ctx.cfg.alertes.horizon_jours
    if st is None:
        return None, "usine non fluviale : le niveau du Rhin ne joue pas"
    if niveau_cm is not None:
        traj, libelle = np.full(H, float(niveau_cm)), f"niveau constant de {niveau_cm:.0f} cm"
    elif scenario == "niveau_constant" or st not in ctx.situation.previsions:
        niv = ctx.situation.stations[st].actuel_cm
        traj, libelle = np.full(H, niv), f"niveau constant au niveau actuel ({niv:.0f} cm)"
    else:
        prev = ctx.situation.previsions[st]
        q = {"bas": 10, "median": 50, "haut": 90}.get(scenario, 50)
        traj = np.percentile(prev.niveaux_cm, q, axis=0)[:H]
        if len(traj) < H:
            traj = np.r_[traj, np.full(H - len(traj), traj[-1])]
        libelle = f"prévision, scénario {scenario} ({q}e centile des {prev.niveaux_cm.shape[0]} scénarios)"
    if fermeture_jours > 0:
        traj = traj.copy()
        traj[:fermeture_jours] = -100.0  # voie d'eau fermée : plus aucun chargement possible
        libelle += f", voie d'eau fermée les {fermeture_jours} premiers jours"
    return traj, libelle


def fabriquer_outils(ctx: Contexte) -> list:
    """Crée les outils liés à la situation du jour (fermeture sur le contexte)."""
    usines_valides = ", ".join(ctx.cfg.usines)

    def _verifier_usine(usine: str):
        if usine not in ctx.cfg.usines:
            raise ValueError(f"Usine inconnue : {usine}. Usines disponibles : {usines_valides}.")

    @beta_tool
    def lire_niveaux_rhin() -> str:
        """Niveaux actuels du Rhin (Kaub, Duisburg-Ruhrort) et capacité des péniches qui en découle.

        Pour chaque station : niveau à l'échelle (cm), tendance sur 7 jours, minimum des 30 derniers jours,
        profondeur du chenal, taux de chargement du bateau type, nombre de bateaux nécessaires pour en
        remplacer un, multiplicateur du fret par rapport aux eaux normales, seuils utiles, source.
        """
        res = {s: {k: v for k, v in d.items() if k != "prevision"} for s, d in ctx.analyse["stations"].items()}
        return ctx.registre.noter("lire_niveaux_rhin", {}, res)

    @beta_tool
    def lire_prevision(station: str) -> str:
        """Prévision du niveau à six semaines pour une station, issue de 50 scénarios (prévision d'ensemble).

        Renvoie les jalons hebdomadaires (médiane et fourchette 10 %-90 %) et des probabilités : rester au
        moins 7 jours sous le seuil où les péniches chargent à moitié, ou sous le seuil de navigation risquée.

        Args:
            station: identifiant de la station, "KAUB" ou "DUISBURG-RUHRORT".
        """
        d = ctx.analyse["stations"].get(station)
        if d is None or "prevision" not in d:
            raise ValueError(f"Pas de prévision pour {station}. Stations : {', '.join(ctx.analyse['stations'])}.")
        return ctx.registre.noter("lire_prevision", {"station": station}, {"seuils_cm": d["seuils_cm"], **d["prevision"]})

    @beta_tool
    def lire_prix_et_meteo() -> str:
        """Prix du jour (blé et maïs Euronext, gaz TTF, quota carbone EUA) avec leur source et leur date,
        et cumul de pluie prévu à 7 et 14 jours sur le bassin du Rhin."""
        return ctx.registre.noter("lire_prix_et_meteo", {}, {"prix": ctx.analyse["prix"], "pluie": ctx.analyse["pluie"]})

    @beta_tool
    def chiffrer_cout_rendu(usine: str, niveau_cm: float | None = None) -> str:
        """Coût rendu usine d'une tonne de blé (€/t) par péniche, rail et camion, avec le détail du fret.

        Args:
            usine: identifiant de l'usine ("A", "B" ou "C").
            niveau_cm: niveau hypothétique de la station de l'usine, en cm. Laisser vide pour le niveau actuel.
        """
        _verifier_usine(usine)
        u = ctx.cfg.usines[usine]
        st = u.approvisionnement.peniche.station if u.approvisionnement.peniche.part > 0 else None
        niv = niveau_cm if niveau_cm is not None else (ctx.situation.stations[st].actuel_cm if st else None)
        res = cout_rendu_usine(ctx.cfg, usine, niv, ctx.situation.prix["ble_euronext"].valeur)
        return ctx.registre.noter("chiffrer_cout_rendu", {"usine": usine, "niveau_cm": niveau_cm}, res)

    @beta_tool
    def projeter_couverture(usine: str, scenario: str = "median", niveau_cm: float | None = None, fermeture_jours: int = 0) -> str:
        """Projette le stock de l'usine sur six semaines sans changer le plan d'approvisionnement.

        Renvoie le stock minimal (en jours de consommation), le premier jour de rupture éventuel, les tonnes
        de rupture et les coûts. Sert à répondre à « combien de jours d'autonomie si… ? ».

        Args:
            usine: identifiant de l'usine ("A", "B" ou "C").
            scenario: "median", "bas" (10e centile, eau basse) ou "haut" (90e centile) de la prévision, ou "niveau_constant".
            niveau_cm: si renseigné, impose un niveau constant (cm) à la station de l'usine pendant six semaines.
            fermeture_jours: nombre de jours, à partir de demain, pendant lesquels la voie d'eau est fermée.
        """
        _verifier_usine(usine)
        traj, libelle = _trajectoire(ctx, usine, scenario, niveau_cm, fermeture_jours)
        marge = ctx.analyse["usines"][usine]["marge"]["marge_eur_t"] if usine in ctx.analyse["usines"] else 0.0
        sim = simuler(ctx.cfg, usine, traj, marge_eur_t=marge, horizon=ctx.cfg.alertes.horizon_jours)
        t = sim.totaux
        res = {
            "usine": usine,
            "hypothese_niveau": libelle,
            "stock_initial_jours": ctx.cfg.usines[usine].stock_initial_jours,
            "stock_minimal_jours": round(t["stock_min_jours"], 1),
            "premier_jour_rupture": t["premier_jour_rupture"],
            "rupture_t": round(t["rupture_t"], 0),
            "cout_transport_eur": round(t["cout_transport_eur"], 0),
            "cout_rupture_eur": round(t["cout_rupture_eur"], 0),
            "cout_total_eur": round(t["cout_total_eur"], 0),
            "stock_jours_par_semaine": [round(float(x), 1) for x in sim.jours.stock_jours.iloc[6::7]],
        }
        return ctx.registre.noter("projeter_couverture", {"usine": usine, "scenario": scenario, "niveau_cm": niveau_cm, "fermeture_jours": fermeture_jours}, res)

    @beta_tool
    def chiffrer_marge(usine: str, hausse_gaz_pct: float = 0.0, hausse_ble_eur_t: float = 0.0, niveau_cm: float | None = None) -> str:
        """Marge variable de l'usine (€/t de blé et €/jour), éventuellement sous un choc combiné.

        Args:
            usine: identifiant de l'usine ("A", "B" ou "C").
            hausse_gaz_pct: hausse du prix du gaz en pourcentage (20 pour +20 %).
            hausse_ble_eur_t: hausse du prix du blé en €/t.
            niveau_cm: niveau hypothétique de la station de l'usine (cm). Vide : niveau actuel.
        """
        _verifier_usine(usine)
        u = ctx.cfg.usines[usine]
        st = u.approvisionnement.peniche.station if u.approvisionnement.peniche.part > 0 else None
        niv = niveau_cm if niveau_cm is not None else (ctx.situation.stations[st].actuel_cm if st else None)
        p = ctx.situation.prix
        base = marge_usine(ctx.cfg, usine, (ctx.situation.stations[st].actuel_cm if st else None), p["ble_euronext"].valeur, p["gaz_ttf"].valeur, p["carbone_eua"].valeur)
        choc = marge_usine(
            ctx.cfg, usine, niv, p["ble_euronext"].valeur + hausse_ble_eur_t, p["gaz_ttf"].valeur * (1 + hausse_gaz_pct / 100), p["carbone_eua"].valeur
        )
        res = {
            "base": base,
            "choc": choc,
            "ecart_eur_t": round(choc["marge_eur_t"] - base["marge_eur_t"], 2),
            "ecart_eur_jour": round(choc["marge_eur_jour"] - base["marge_eur_jour"], 0),
        }
        return ctx.registre.noter("chiffrer_marge", {"usine": usine, "hausse_gaz_pct": hausse_gaz_pct, "hausse_ble_eur_t": hausse_ble_eur_t, "niveau_cm": niveau_cm}, res)

    @beta_tool
    def comparer_options(usine: str) -> str:
        """Options logistiques chiffrées pour une usine, sur les 50 scénarios de niveau et six semaines.

        Pour chaque option : coût moyen, écart avec « ne rien changer », probabilité et tonnes de rupture.
        Inclut la recommandation calculée, le niveau d'alerte et les options déjà écartées par l'équipe.

        Args:
            usine: identifiant de l'usine ("A", "B" ou "C").
        """
        _verifier_usine(usine)
        r = ctx.analyse["usines"][usine]
        res = {
            "usine": usine,
            "niveau_alerte": r["niveau_alerte"],
            "raisons_alerte": r["raisons_alerte"],
            "autonomie": r["autonomie"],
            "options": [o for o in r["options"] if not o.get("sans_effet")],
            "recommandation": r["recommandation"],
            "options_ecartees_par_l_equipe": journal.options_ecartees(usine),
        }
        return ctx.registre.noter("comparer_options", {"usine": usine}, res)

    @beta_tool
    def consulter_decisions_passees(nombre: int = 10) -> str:
        """Dernières recommandations de KAUB et décisions de l'équipe (option retenue ou écartée, et pourquoi).

        Args:
            nombre: nombre d'entrées à relire (les plus récentes).
        """
        return ctx.registre.noter("consulter_decisions_passees", {"nombre": nombre}, {"entrees": journal.lire(nombre)})

    @beta_tool
    def deposer_alerte(usine: str, niveau: str, message: str) -> str:
        """Dépose une alerte dans le dossier sorties/alertes pour relecture humaine. Rien n'est envoyé.

        Args:
            usine: identifiant de l'usine concernée.
            niveau: "ORANGE" ou "ROUGE".
            message: texte court de l'alerte (deux phrases au plus).
        """
        _verifier_usine(usine)
        d = ctx.dossier_sorties / "alertes"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{ctx.analyse['date']}_usine{usine}_{niveau}.txt"
        f.write_text(f"[{niveau}] Usine {usine} — {datetime.now():%d/%m/%Y %H:%M}\n{message}\n", encoding="utf-8")
        return ctx.registre.noter("deposer_alerte", {"usine": usine, "niveau": niveau}, {"fichier": _chemin_affiche(f), "envoye": False})

    @beta_tool
    def preparer_brouillon_logistique(objet: str, corps: str) -> str:
        """Prépare un brouillon de message à l'équipe logistique (fichier dans sorties/brouillons). Rien n'est envoyé.

        Args:
            objet: objet du message.
            corps: texte du message, prêt à relire.
        """
        d = ctx.dossier_sorties / "brouillons"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{ctx.analyse['date']}_logistique.md"
        f.write_text(f"Objet : {objet}\n\n{corps}\n", encoding="utf-8")
        return ctx.registre.noter("preparer_brouillon_logistique", {"objet": objet}, {"fichier": _chemin_affiche(f), "envoye": False})

    return [
        lire_niveaux_rhin,
        lire_prevision,
        lire_prix_et_meteo,
        chiffrer_cout_rendu,
        projeter_couverture,
        chiffrer_marge,
        comparer_options,
        consulter_decisions_passees,
        deposer_alerte,
        preparer_brouillon_logistique,
    ]
