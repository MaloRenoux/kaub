"""Rédaction du rapport de rejeu (Markdown), à partir des résultats chiffrés."""

from __future__ import annotations

from kaub.format import date_fr, keur, nb, pct


def rediger(resume: dict, bilan: dict, options_ex_ante: list[dict], options_a_posteriori: list[dict]) -> str:
    r = resume
    l = [
        "# KAUB — Rejeu de l'été 2026",
        "",
        "**Question : si KAUB avait tourné chaque matin pendant les basses eaux de 2026, qu'aurait-il annoncé, et quand ?**",
        "",
        "Règle du rejeu : chaque jour, KAUB ne voit que les niveaux passés. Il prévoit avec une méthode de tarissement "
        "(sans pluie) et applique des seuils fixés à l'avance : alerte orange s'il y a au moins une chance sur deux que Kaub "
        f"passe sous {nb(r['seuils']['orange_cm'])} cm dans les {r['seuils']['horizon_jours']} jours (navigation à peine rentable selon Contargo), "
        f"rouge pour {nb(r['seuils']['rouge_cm'])} cm (le record de 2018).",
        "",
        "## Ce que KAUB aurait vu venir",
        "",
        "| | Alerte KAUB | Ce qui s'est passé | Avance |",
        "|---|---|---|---|",
        f"| Passage sous 40 cm | orange le {date_fr(r['premiere_alerte_orange'], False)} (Kaub à {nb(r['niveau_premiere_alerte_orange_cm'])} cm) | "
        f"{date_fr(r['premier_passage_sous_40cm'], False)} | **{r['avance_orange_sur_40cm_jours']} jours** |",
        f"| Passage sous 25 cm (record de 2018) | rouge le {date_fr(r['premiere_alerte_rouge'], False)} (Kaub à {nb(r['niveau_premiere_alerte_rouge_cm'])} cm) | "
        f"{date_fr(r['premier_passage_sous_25cm'], False)} | **{r['avance_rouge_sur_25cm_jours']} jours** |",
        f"| Passage sous 10 cm (navigation quasi impossible) | orange dès le {date_fr(r['premiere_alerte_orange'], False)} | "
        f"{date_fr(r['premier_passage_sous_10cm'], False)} | **{r['avance_orange_sur_10cm_jours']} jours** |",
        "",
        f"Phrase à retenir : **KAUB aurait alerté {r['avance_orange_sur_10cm_jours']} jours avant que Kaub passe sous 10 cm**, "
        f"alors que le fleuve était encore à {nb(r['niveau_premiere_alerte_orange_cm'])} cm.",
        "",
        "L'alerte retombe parfois quelques jours après une averse, puis revient : c'est le comportement attendu d'un indicateur "
        "qui ne regarde que les trois semaines suivantes.",
        "",
    ]
    if options_a_posteriori:
        statu = next(o for o in options_a_posteriori if o["option"] == "Ne rien changer")
        reco = next((o for o in options_a_posteriori if o.get("recommandee_par_kaub")), None)
        ex = next((o for o in options_ex_ante if o["option"] == (reco or {}).get("option")), None)
        l += [
            f"## Ce que l'action aurait changé pour l'usine A (fictive), à partir du {date_fr(r['premiere_alerte_orange'], False)}",
            "",
            f"Ce jour-là, KAUB aurait proposé : **{r['recommandation_jour_alerte']}**"
            + (f" (d'après sa prévision : risque de rupture {pct(ex['proba_rupture'])} contre {pct(next(o for o in options_ex_ante if o['option'] == 'Ne rien changer')['proba_rupture'])} sans rien faire)." if ex else "."),
            "",
            "Coût réel de chaque option sur les six semaines suivantes, calculé sur les niveaux réellement observés "
            "(hypothèse : 12 jours de stock et le plan d'approvisionnement habituel ce jour-là) :",
            "",
            "| Option | Coût total | Écart avec « ne rien changer » | Production perdue |",
            "|---|---|---|---|",
        ]
        for o in sorted(options_a_posteriori, key=lambda o: o["cout_moyen_eur"]):
            marque = " ← proposée par KAUB" if o.get("recommandee_par_kaub") else ""
            l.append(
                f"| {o['option']}{marque} | {keur(o['cout_moyen_eur'])} | {'—' if o is statu else keur(o['ecart_vs_statu_quo_eur'])} | {nb(o['rupture_moyenne_t'])} t |"
            )
        l += [
            "",
            f"Sans action, l'usine aurait perdu {nb(statu['rupture_moyenne_t'])} t de production en six semaines. "
            + (f"L'option proposée par KAUB l'évitait pour un coût inférieur de {keur(-reco['ecart_vs_statu_quo_eur'])}." if reco and reco["rupture_moyenne_t"] < 1 else ""),
            "Le coût total comprend le transport, le stockage et la production perdue (marge perdue et pénalités, hypothèses dans config/hypotheses.yaml).",
            "",
        ]
    l += [
        "## Fiabilité de la série de l'été",
        "",
        "PEGELONLINE ne garde qu'un mois d'historique : la série de juin à début octobre est **reconstituée** à partir des débits du "
        "modèle GloFAS (Copernicus), corrigés sur les mesures officielles d'octobre–novembre, convertis en niveaux par la courbe de tarage, "
        f"puis ancrés sur {bilan['nb_releves_ancrage']} relevés datés publiés dans la presse.",
        "",
        f"- Erreur du modèle seul face aux relevés : {nb(bilan['erreur_avant_ancrage_cm']['moyenne_absolue'], 1)} cm en moyenne (maximum {nb(bilan['erreur_avant_ancrage_cm']['max'], 1)} cm).",
        f"- Validation croisée (chaque relevé retiré puis prédit par les autres) : {nb(bilan['erreur_validation_croisee_cm']['moyenne_absolue'], 1)} cm en moyenne "
        f"(maximum {nb(bilan['erreur_validation_croisee_cm']['max'], 1)} cm). C'est l'ordre de grandeur de l'incertitude entre deux relevés.",
        f"- Contrôle indépendant : la série atteint son minimum d'août le {date_fr(r['date_minimum_aout'], False)} à {nb(r['minimum_aout_cm'])} cm ; "
        "la presse parlait de 6 cm « à la mi-août », relevé volontairement non utilisé pour l'ancrage.",
        "- **Avant le 24 juillet, aucun relevé n'ancre la série** : la date de la première alerte (fin juin) et celle du passage sous 40 cm "
        "sont indicatives, avec une incertitude de l'ordre de 15 cm sur le niveau. Les passages sous 25 cm et sous 10 cm, eux, tombent dans la période ancrée.",
        "- La prévision du rejeu (tarissement) ne voit pas venir la pluie : elle est prudente. Au quotidien, KAUB utilise la prévision d'ensemble GloFAS (50 scénarios).",
        "",
        "Fichiers : rejeu_jour_par_jour.csv (une ligne par jour), serie_kaub_ete_2026.csv (série et source de chaque valeur), rejeu_ete_2026.png.",
    ]
    return "\n".join(l)
