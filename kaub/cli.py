"""Commandes de KAUB (à lancer depuis le dossier du projet).

    kaub note --hors-ligne          note du matin sur les données réelles du 9 novembre 2026, sans connexion
    kaub note                       note du matin sur les données du jour (mode sans IA)
    kaub note --ia                  note du matin rédigée par Claude (clé d'API nécessaire)
    kaub question "…" [--hors-ligne] poser une question à l'agent
    kaub rejeu                      reconstituer l'été 2026 et rejouer KAUB jour par jour
    kaub collecter                  enregistrer niveaux et prix (lancé chaque jour par GitHub Actions)
    kaub decider …                  enregistrer la décision de l'équipe
    kaub calibrer                   recaler la courbe de tarage et la correction de GloFAS
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kaub.config import RACINE, charger_config

SORTIES = RACINE / "sorties"


def _charger_env() -> None:
    """Lit le fichier .env (clé d'API) s'il existe, sans dépendance supplémentaire."""
    f = RACINE / ".env"
    if f.exists():
        for ligne in f.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.strip().startswith("#"):
                k, v = ligne.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


def _situation(cfg, hors_ligne: bool):
    from kaub.situation import situation_en_ligne, situation_hors_ligne

    return situation_hors_ligne(cfg) if hors_ligne else situation_en_ligne(cfg)


def cmd_note(args) -> None:
    from kaub import journal
    from kaub.analyse import analyser
    from kaub.note import rediger

    cfg = charger_config()
    situation = _situation(cfg, args.hors_ligne)
    analyse = analyser(cfg, situation)
    dossier = SORTIES / "notes"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"analyse_{analyse['date']}.json").write_text(json.dumps(analyse, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if args.ia:
        from kaub.agent.agent import lancer
        from kaub.agent.outils import Contexte

        res = lancer(Contexte(cfg, situation, analyse), modele=args.modele)
        texte = res.texte + f"\n\n---\n*Rédigé par {res.modele} à partir de {len(res.appels)} appels d'outils. Contrôle des chiffres : {res.verification.resume()}*\n"
        nom = f"note_{analyse['date']}_ia.md"
        (dossier / f"appels_outils_{analyse['date']}.json").write_text(json.dumps(res.appels, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    else:
        texte = rediger(analyse)
        nom = f"note_{analyse['date']}.md"
    (dossier / nom).write_text(texte, encoding="utf-8")
    journal.enregistrer_recommandation(analyse)
    print(texte)
    print(f"\n→ Note enregistrée dans sorties/notes/{nom}", file=sys.stderr)


def cmd_question(args) -> None:
    from kaub.agent.agent import lancer
    from kaub.agent.outils import Contexte
    from kaub.analyse import analyser

    cfg = charger_config()
    situation = _situation(cfg, args.hors_ligne)
    res = lancer(Contexte(cfg, situation, analyser(cfg, situation)), demande=args.texte, modele=args.modele)
    print(res.texte)
    print(f"\n[{len(res.appels)} appels d'outils : {', '.join(a['outil'] for a in res.appels)}]")
    print(res.verification.resume())


def cmd_rejeu(args) -> None:
    from kaub.graphiques import figure_rejeu_png
    from kaub.hydro.reconstitution import charger_ancres, reconstituer
    from kaub.rapport_rejeu import rediger
    from kaub.rejeu import rejouer

    cfg = charger_config()
    serie, bilan = reconstituer(cfg, debut="2026-05-01")
    res = rejouer(cfg, serie, debut=args.debut, fin=args.fin)
    d = SORTIES / "rejeu"
    d.mkdir(parents=True, exist_ok=True)
    serie.to_csv(d / "serie_kaub_ete_2026.csv", index_label="date")
    res.jours.round(3).to_csv(d / "rejeu_jour_par_jour.csv", index_label="date")
    (d / "rejeu_resume.json").write_text(
        json.dumps({"resume": res.resume, "bilan_reconstitution": bilan, "options_ex_ante": res.options_ex_ante, "options_a_posteriori": res.options_a_posteriori}, ensure_ascii=False, indent=1, default=float),
        encoding="utf-8",
    )
    figure_rejeu_png(serie, res.jours, res.resume, charger_ancres(), bilan["erreur_validation_croisee_cm"]["moyenne_absolue"], d / "rejeu_ete_2026.png")
    rapport = rediger(res.resume, bilan, res.options_ex_ante, res.options_a_posteriori)
    (d / "rapport_rejeu.md").write_text(rapport, encoding="utf-8")
    print(rapport)
    print("\n→ Résultats dans sorties/rejeu/", file=sys.stderr)


def cmd_collecter(args) -> None:
    from kaub.situation import situation_en_ligne

    cfg = charger_config()
    s = situation_en_ligne(cfg, archiver=True)
    for st, e in s.stations.items():
        print(f"{st} : {e.actuel_cm:.0f} cm ({e.horodatage})")
    for k, p in s.prix.items():
        print(f"{k} : {p.valeur} {p.unite} ({p.date})")
    for a in s.avertissements:
        print(f"Avertissement : {a}")


def cmd_decider(args) -> None:
    from kaub import journal

    e = journal.enregistrer_decision(args.date, args.usine, args.option, args.par, retenue=not args.ecartee, commentaire=args.commentaire or "")
    print("Décision enregistrée :", json.dumps(e, ensure_ascii=False))


def cmd_calibrer(args) -> None:
    import pandas as pd

    from kaub.hydro.glofas import caler_correction
    from kaub.hydro.tarage import caler_courbe
    from kaub.sources import openmeteo, pegelonline, stockage

    cfg = charger_config()
    for st_id, st in cfg.stations.items():
        w = pegelonline.journalier(stockage.lire_serie(st_id, "W"))["moyenne"]
        q = pegelonline.journalier(stockage.lire_serie(st_id, "Q"))["moyenne"]
        commun = w.index.intersection(q.index)
        if len(commun) < 14:
            print(f"{st_id} : seulement {len(commun)} jours archivés, il en faut au moins 14.")
            continue
        courbe, err = caler_courbe(w.loc[commun], q.loc[commun], depart=(st.tarage.W0, st.tarage.c, st.tarage.n))
        g = openmeteo.glofas_historique(st.glofas.latitude, st.glofas.longitude, str(commun.min().date() - pd.Timedelta(days=30)), str(commun.max().date()))
        corr, err_g = caler_correction(g, q.loc[commun])
        print(f"{st_id} : tarage W0={courbe.W0:.4f} c={courbe.c:.7g} n={courbe.n:.6f} (erreur {err:.2f} m3/s) ; "
              f"correction GloFAS fenêtre={corr.fenetre_jours} a={corr.coef_base:.5f} b={corr.coef_rapide:.5f} (erreur {err_g:.1f} m3/s)")
    print("Reportez ces valeurs dans config/hypotheses.yaml si elles améliorent l'erreur.")


def main(argv=None) -> None:
    _charger_env()
    p = argparse.ArgumentParser(prog="kaub", description="KAUB : agent d'aide à la décision sur les basses eaux du Rhin.")
    sp = p.add_subparsers(dest="commande", required=True)

    n = sp.add_parser("note", help="note du matin")
    n.add_argument("--hors-ligne", action="store_true", help="utiliser l'instantané réel du 9 novembre 2026")
    n.add_argument("--ia", action="store_true", help="faire rédiger la note par Claude")
    n.add_argument("--modele", default=None)
    n.set_defaults(f=cmd_note)

    q = sp.add_parser("question", help="poser une question à l'agent")
    q.add_argument("texte")
    q.add_argument("--hors-ligne", action="store_true")
    q.add_argument("--modele", default=None)
    q.set_defaults(f=cmd_question)

    r = sp.add_parser("rejeu", help="rejouer l'été 2026")
    r.add_argument("--debut", default="2026-06-01")
    r.add_argument("--fin", default="2026-10-31")
    r.set_defaults(f=cmd_rejeu)

    sp.add_parser("collecter", help="enregistrer niveaux et prix du jour").set_defaults(f=cmd_collecter)

    d = sp.add_parser("decider", help="enregistrer une décision de l'équipe")
    d.add_argument("--date", required=True)
    d.add_argument("--usine", required=True)
    d.add_argument("--option", required=True)
    d.add_argument("--par", required=True, help="qui décide")
    d.add_argument("--ecartee", action="store_true", help="l'option est écartée (par défaut : retenue)")
    d.add_argument("--commentaire", default="")
    d.set_defaults(f=cmd_decider)

    sp.add_parser("calibrer", help="recaler la courbe de tarage sur l'historique archivé").set_defaults(f=cmd_calibrer)

    args = p.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    main()
