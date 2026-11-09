"""La note du matin, rédigée par un gabarit à partir de l'analyse du jour (« mode sans IA »).

C'est la version de référence : elle ne contient que des chiffres calculés par le code. La version
rédigée par Claude (kaub/agent) suit la même structure, et chacun de ses chiffres est contrôlé.
"""

from __future__ import annotations

from kaub.format import date_fr, eur, keur, nb, pct

PICTO = {"VERT": "🟢", "ORANGE": "🟠", "ROUGE": "🔴"}
NOMS_PRIX = {
    "ble_euronext": "Blé de meunerie Euronext",
    "mais_euronext": "Maïs Euronext",
    "gaz_ttf": "Gaz TTF (marché de référence européen)",
    "carbone_eua": "Quota carbone européen (EUA)",
}


def _ligne_station(s: dict) -> list[str]:
    seuils = s["seuils_cm"]
    l = [
        f"**{s['nom']}** : {nb(s['niveau_cm'])} cm (tendance {nb(s['tendance_7j_cm_par_jour'], 1, signe=True)} cm/jour sur 7 jours). "
        f"Chenal profond de {nb(s['profondeur_chenal_cm'])} cm : un {s['bateau_type']} charge {pct(s['taux_chargement'])} de sa capacité, "
        f"il faut {nb(s['bateaux_pour_un'], 1)} bateaux pour en remplacer un, et le fret vaut {nb(s['multiplicateur_fret'], 2)} fois son niveau normal."
    ]
    p = s.get("prevision")
    if p:
        jal = p["jalons"]
        traj = " ; ".join(f"{date_fr(j['date'], annee=False)} : {nb(j['median_cm'])} cm ({nb(j['bas_p10_cm'])} à {nb(j['haut_p90_cm'])})" for j in jal[:4])
        l.append(
            f"  Prévision ({p['nb_scenarios']} scénarios, médiane et fourchette 10–90 %) : {traj}. "
            f"Probabilité de rester au moins 7 jours sous {nb(seuils['chargement_moitie'])} cm (péniches à moitié vides) dans les 3 semaines : "
            f"{pct(p['proba_chargement_sous_moitie_7j_dans_3_semaines'])} ; sous {nb(seuils['navigation_risquee'])} cm (navigation à peine rentable) : "
            f"{pct(p['proba_sous_navigation_risquee_7j_dans_3_semaines'])}."
        )
    return l


def _bloc_usine(u: dict) -> list[str]:
    l = [f"### {PICTO[u['niveau_alerte']]} {u['nom']} — {u['niveau_alerte']}", ""]
    l.append(f"Pourquoi : {' ; '.join(u['raisons_alerte'])}.")
    modes = u["cout_rendu"]["modes"]
    morceaux = []
    if "peniche" in modes:
        p = modes["peniche"]
        morceaux.append(
            f"péniche {eur(p['cout_rendu_eur_t'], 1)}/t (fret {eur(p['fret_eur_t'], 1)}/t)" if p["disponible"] else "péniche : voie d'eau fermée"
        )
    morceaux.append(f"rail {eur(modes['rail']['cout_rendu_eur_t'], 1)}/t")
    morceaux.append(f"camion {eur(modes['camion']['cout_rendu_eur_t'], 1)}/t")
    l.append(f"- Coût rendu usine du blé : {', '.join(morceaux)}.")
    m = u["marge"]
    l.append(
        f"- Marge variable : {eur(m['marge_eur_t'], 1)}/t de blé, soit {keur(m['marge_eur_jour'])} par jour "
        f"(produits {eur(m['valeur_produits_eur_t'])}/t − blé rendu {eur(m['ble_rendu_eur_t'], 1)} − gaz {eur(m['gaz_eur_t'], 1)} − carbone {eur(m['carbone_eur_t'], 1)})."
    )
    a = u["autonomie"]
    if a["autonomie_jours"] is None:
        l.append(f"- Stock : {nb(a['stock_jours_consommation'], 1)} jours de consommation ; les arrivées couvrent la consommation au niveau actuel.")
    else:
        l.append(
            f"- Stock : {nb(a['stock_jours_consommation'], 1)} jours de consommation. Au niveau actuel, il manque {nb(a['deficit_t_jour'])} t par jour : "
            f"**{nb(a['autonomie_jours'], 1)} jours d'autonomie** avant de devoir réduire la production."
        )
    opts = [o for o in u["options"] if not o.get("sans_effet")]
    statu = next(o for o in u["options"] if o["option"] == "Ne rien changer")
    if len(opts) > 1:
        l.append(f"- Options chiffrées sur {statu['nb_scenarios']} scénarios et 6 semaines :")
        for i, o in enumerate(opts[:3], 1):
            ecart = "" if o is statu else f", {('économie' if o['ecart_vs_statu_quo_eur'] < 0 else 'surcoût')} de {keur(abs(o['ecart_vs_statu_quo_eur']))} par rapport à ne rien changer"
            l.append(
                f"  {i}. **{o['option']}** : coût moyen {keur(o['cout_moyen_eur'])}{ecart} ; "
                f"risque de rupture {pct(o['proba_rupture'])} (rupture moyenne {nb(o['rupture_moyenne_t'])} t). {o['description']}"
            )
        if statu not in opts[:3]:
            l.append(
                f"  Pour mémoire, ne rien changer : coût moyen {keur(statu['cout_moyen_eur'])}, risque de rupture {pct(statu['proba_rupture'])}, "
                f"rupture moyenne {nb(statu['rupture_moyenne_t'])} t."
            )
        r = u["recommandation"]
        if r["option"] != "Ne rien changer":
            l.append(
                f"- **Recommandation : {r['option']}**, à valider par {r['a_valider_par']} "
                "(règle : l'option la moins chère parmi celles qui gardent le risque de rupture sous 10 %)."
            )
        else:
            l.append("- **Recommandation : pas d'action logistique.**")
    s = u["sensibilites"]
    cles = [k for k in s if k != "base"]
    l.append("- Sensibilité de la marge : " + " ; ".join(f"{_nom_choc(k)} {eur(s[k]['ecart_eur_t'], 1)}/t ({keur(s[k]['ecart_eur_jour'])}/jour)" for k in cles) + ".")
    l.append("")
    return l


def _nom_choc(cle: str) -> str:
    if cle.startswith("gaz_plus_"):
        return f"gaz +{cle.split('_')[2].replace('pct', '')} %"
    if cle.startswith("ble_plus_"):
        return f"blé +{cle.split('_')[2].replace('eur', '')} €/t"
    if cle.startswith("rhin_a_"):
        return f"Rhin à {nb(float(cle.split('_')[2].replace('cm', '')))} cm"
    return "gaz +20 % et Rhin −20 cm"


def rediger(analyse: dict) -> str:
    """Note du matin en Markdown, d'une page environ."""
    l = [
        f"# KAUB — Note du {date_fr(analyse['date'])}",
        "",
        f"**Alerte du jour : {PICTO[analyse['alerte_globale']]} {analyse['alerte_globale']}** · {analyse['mode']} · réseau d'usines **fictif**.",
        "",
        "## Situation",
        "",
    ]
    for s in analyse["stations"].values():
        l += [f"- {x}" if i == 0 else x for i, x in enumerate(_ligne_station(s))]
    if analyse.get("pluie"):
        p = analyse["pluie"]["cumul_7j_mm"]
        l.append("- Pluie prévue sur 7 jours : " + ", ".join(f"{k} {nb(v)} mm" for k, v in p.items()) + ".")
    prix = analyse["prix"]
    l.append(
        "- Prix : "
        + " ; ".join(
            f"{NOMS_PRIX[k]} {nb(prix[k]['valeur'], 2)} {prix[k]['unite'].replace('EUR', '€')}" + (" (approximation)" if prix[k].get("approximation") else "")
            for k in ("ble_euronext", "gaz_ttf", "carbone_eua")
            if k in prix
        )
        + "."
    )
    l += ["", "## Impact et options par usine", ""]
    for u in sorted(analyse["usines"].values(), key=lambda u: {"ROUGE": 0, "ORANGE": 1, "VERT": 2}[u["niveau_alerte"]]):
        l += _bloc_usine(u)
    if analyse.get("avertissements"):
        l += ["## Avertissements", ""] + [f"- {a}" for a in analyse["avertissements"]] + [""]
    l += [
        "## À lire avant de décider",
        "",
        "- Réseau d'usines, stocks et coûts : **fictifs**, inspirés de cas publics (hypothèses dans config/hypotheses.yaml). Niveaux, prévisions et prix : **réels**.",
        "- Chaque chiffre sort d'une fonction testée du modèle ; KAUB propose, **un humain décide**.",
        "- Sources : PEGELONLINE (niveaux et débits du Rhin) ; Open-Meteo et GloFAS, modèle hydrologique du programme Copernicus (prévision d'ensemble et pluie) ; "
        "Euronext (blé) ; Yahoo Finance (gaz TTF, quota carbone) ; Contargo (règles de chargement).",
    ]
    return "\n".join(l)
