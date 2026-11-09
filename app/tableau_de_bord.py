"""Tableau de bord KAUB (Streamlit). Lancer depuis le dossier du projet :

    streamlit run app/tableau_de_bord.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kaub.analyse import analyser  # noqa: E402
from kaub.config import CHEMIN_CONFIG, charger_config  # noqa: E402
from kaub.format import date_fr, keur, nb, pct  # noqa: E402
from kaub.graphiques import figure_niveau_et_prevision, figure_options, figure_rejeu  # noqa: E402
from kaub.note import PICTO, rediger  # noqa: E402

st.set_page_config(page_title="KAUB — basses eaux du Rhin", page_icon="🌊", layout="wide")

QUESTIONS_TYPES = [
    "Si Duisburg-Ruhrort reste à 150 cm pendant six semaines, combien me coûte l'approvisionnement de l'usine B ?",
    "Vaut-il mieux avancer des livraisons par péniche ou basculer 30 % des volumes sur le rail pour l'usine A ?",
    "Combien de jours d'autonomie pour l'usine A si le Rhin devient impraticable pendant dix jours ?",
    "Quel est l'effet combiné d'une hausse du gaz de 20 % et d'une baisse du Rhin de 20 cm sur la marge de l'usine A ?",
]


@st.cache_resource(show_spinner="Lecture des données…")
def situation_du_jour(mode: str):
    from kaub.situation import situation_en_ligne, situation_hors_ligne

    cfg = charger_config()
    return situation_hors_ligne(cfg) if mode == "hors_ligne" else situation_en_ligne(cfg, archiver=False)


@st.cache_resource(show_spinner="Rejeu de l'été 2026 (une dizaine de secondes)…")
def rejeu():
    from kaub.hydro.reconstitution import charger_ancres, reconstituer
    from kaub.rapport_rejeu import rediger as rediger_rejeu
    from kaub.rejeu import rejouer

    cfg = charger_config()
    serie, bilan = reconstituer(cfg, debut="2026-05-01")
    r = rejouer(cfg, serie)
    return serie, bilan, r, charger_ancres(), rediger_rejeu(r.resume, bilan, r.options_ex_ante, r.options_a_posteriori)


def config_ajustee(stocks: dict[str, float], hausse_gaz: float):
    cfg = charger_config().model_copy(deep=True)
    for u, j in stocks.items():
        cfg.usines[u].stock_initial_jours = j
    return cfg, hausse_gaz


# ------------------------------------------------------------------ barre latérale
with st.sidebar:
    st.title("🌊 KAUB")
    st.caption("Agent d'aide à la décision : niveau du Rhin, prix du blé, du gaz et du carbone, marge d'un réseau **fictif** d'usines d'amidon.")
    mode = st.radio(
        "Données",
        ["hors_ligne", "en_ligne"],
        format_func=lambda m: "Instantané réel du 9 novembre 2026" if m == "hors_ligne" else "Données du jour (connexion requise)",
    )
    st.divider()
    st.subheader("Hypothèses à tester")
    cfg0 = charger_config()
    stocks = {u: st.slider(f"Stock initial usine {u} (jours)", 2.0, 30.0, float(cfg0.usines[u].stock_initial_jours), 1.0) for u in cfg0.usines}
    hausse_gaz = st.slider("Choc sur le gaz (%)", -50, 100, 0, 5)
    st.divider()
    cle = st.text_input("Clé d'API Anthropic (pour poser des questions)", type="password", value=os.environ.get("ANTHROPIC_API_KEY", ""))
    st.caption("Sans clé, tous les calculs fonctionnent ; seule la conversation avec l'agent est désactivée.")

try:
    situation = situation_du_jour(mode)
except Exception as e:  # noqa: BLE001
    st.error(f"Impossible de lire les données du jour ({e}). Passez en mode « instantané du 9 novembre 2026 ».")
    st.stop()

cfg, _ = config_ajustee(stocks, hausse_gaz)
if hausse_gaz:
    from dataclasses import replace

    situation.prix = {**situation.prix, "gaz_ttf": replace(situation.prix["gaz_ttf"], valeur=round(situation.prix["gaz_ttf"].valeur * (1 + hausse_gaz / 100), 2), source=situation.prix["gaz_ttf"].source + f" (choc {hausse_gaz:+d} % appliqué)")}
analyse = analyser(cfg, situation)

# ------------------------------------------------------------------ en-tête
alerte = analyse["alerte_globale"]
st.markdown(f"## {PICTO[alerte]} Alerte du jour : {alerte} — {date_fr(analyse['date'])}")
st.caption(f"{analyse['mode']} · réseau d'usines fictif · chaque chiffre sort d'une fonction testée · KAUB propose, un humain décide")
for a in analyse["avertissements"]:
    st.warning(a)

onglets = st.tabs(["📝 Note du matin", "🌊 Rhin", "🏭 Usines", "⏪ Rejeu de l'été 2026", "💬 Poser une question", "⚙️ Hypothèses"])

with onglets[0]:
    note = rediger(analyse)
    st.download_button("Télécharger la note (.md)", note, file_name=f"note_kaub_{analyse['date']}.md")
    st.markdown(note)

with onglets[1]:
    for st_id, s in analyse["stations"].items():
        st.markdown(f"#### {s['nom']}")
        c = st.columns(5)
        c[0].metric("Niveau à l'échelle", f"{nb(s['niveau_cm'])} cm", f"{nb(s['tendance_7j_cm_par_jour'], 1, signe=True)} cm/jour (7 j)", delta_color="normal")
        c[1].metric("Profondeur du chenal", f"{nb(s['profondeur_chenal_cm'])} cm")
        c[2].metric("Chargement du bateau type", pct(s["taux_chargement"]))
        c[3].metric("Bateaux pour en remplacer un", nb(s["bateaux_pour_un"], 1))
        c[4].metric("Fret / eaux normales", f"× {nb(s['multiplicateur_fret'], 2)}")
        st.plotly_chart(figure_niveau_et_prevision(situation.stations[st_id].journalier, situation.previsions.get(st_id), s["seuils_cm"], s["nom"]), width="stretch")
        if "prevision" in s:
            p = s["prevision"]
            st.caption(
                f"{p['methode']}. Probabilité de rester au moins 7 jours sous {nb(s['seuils_cm']['chargement_moitie'])} cm dans les 3 semaines : "
                f"**{pct(p['proba_chargement_sous_moitie_7j_dans_3_semaines'])}**. Source : {p['source']}."
            )
    if analyse.get("pluie"):
        st.markdown("#### Pluie prévue sur le bassin")
        st.dataframe(pd.DataFrame(analyse["pluie"]).drop(columns="source").rename(columns={"cumul_7j_mm": "7 jours (mm)", "cumul_14j_mm": "14 jours (mm)"}), width="stretch")

with onglets[2]:
    for u_id, u in sorted(analyse["usines"].items(), key=lambda kv: {"ROUGE": 0, "ORANGE": 1, "VERT": 2}[kv[1]["niveau_alerte"]]):
        with st.expander(f"{PICTO[u['niveau_alerte']]} {u['nom']} — {u['niveau_alerte']}", expanded=u["niveau_alerte"] != "VERT"):
            st.write("Pourquoi : " + " ; ".join(u["raisons_alerte"]) + ".")
            c = st.columns(4)
            a = u["autonomie"]
            c[0].metric("Autonomie au niveau actuel", "suffisante" if a["autonomie_jours"] is None else f"{nb(a['autonomie_jours'], 1)} jours")
            c[1].metric("Marge variable", f"{nb(u['marge']['marge_eur_t'], 1)} €/t", f"{keur(u['marge']['marge_eur_jour'])} par jour", delta_color="off")
            modes = u["cout_rendu"]["modes"]
            if "peniche" in modes and modes["peniche"]["disponible"]:
                c[2].metric("Blé rendu par péniche", f"{nb(modes['peniche']['cout_rendu_eur_t'], 1)} €/t", f"fret × {nb(modes['peniche']['multiplicateur_fret'], 2)}", delta_color="inverse")
            c[3].metric("Blé rendu par rail", f"{nb(modes['rail']['cout_rendu_eur_t'], 1)} €/t")
            if len([o for o in u["options"] if not o.get("sans_effet")]) > 1:
                st.plotly_chart(figure_options(u["options"], u_id), width="stretch")
                tableau = pd.DataFrame(
                    [
                        {
                            "Option": o["option"],
                            "Coût moyen": keur(o["cout_moyen_eur"]),
                            "Écart vs ne rien changer": keur(o["ecart_vs_statu_quo_eur"]),
                            "Risque de rupture": pct(o["proba_rupture"]),
                            "Rupture moyenne (t)": nb(o["rupture_moyenne_t"]),
                            "Coût dans un mauvais scénario (90 %)": keur(o["cout_p90_eur"]),
                        }
                        for o in u["options"]
                        if not o.get("sans_effet")
                    ]
                )
                st.dataframe(tableau, hide_index=True, width="stretch")
                st.success(f"Recommandation : **{u['recommandation']['option']}** — à valider par {u['recommandation']['a_valider_par']}.")

with onglets[3]:
    serie, bilan, r, ancres, rapport = rejeu()
    s = r.resume
    c = st.columns(3)
    c[0].metric("Avance sur le passage sous 10 cm", f"{s['avance_orange_sur_10cm_jours']} jours", f"1re alerte le {date_fr(s['premiere_alerte_orange'], False)}", delta_color="off")
    c[1].metric("Avance sur le record de 2018 (25 cm)", f"{s['avance_rouge_sur_25cm_jours']} jours")
    c[2].metric("Incertitude de la série (validation croisée)", f"± {nb(bilan['erreur_validation_croisee_cm']['moyenne_absolue'], 1)} cm")
    st.plotly_chart(figure_rejeu(serie, r.jours, ancres), width="stretch")
    st.markdown(rapport)
    with st.expander("Voir le rejeu jour par jour"):
        st.dataframe(r.jours, width="stretch")

with onglets[4]:
    st.write("L'agent choisit lui-même les calculs à lancer, puis répond. Chaque chiffre de sa réponse est contrôlé.")
    choix = st.selectbox("Questions types", [""] + QUESTIONS_TYPES)
    question = st.text_area("Votre question", value=choix, height=90)
    if st.button("Demander à KAUB", type="primary", disabled=not (cle and question.strip())):
        os.environ["ANTHROPIC_API_KEY"] = cle
        from kaub.agent.agent import lancer
        from kaub.agent.outils import Contexte

        with st.spinner("KAUB réfléchit et lance ses calculs…"):
            try:
                res = lancer(Contexte(cfg, situation, analyse), demande=question)
            except Exception as e:  # noqa: BLE001
                st.error(f"L'appel à Claude a échoué : {e}")
                st.stop()
        st.markdown(res.texte)
        (st.success if res.verification.ok else st.warning)(res.verification.resume())
        with st.expander(f"Les {len(res.appels)} calculs lancés par l'agent"):
            for a in res.appels:
                st.markdown(f"**{a['outil']}** — arguments : `{a['arguments']}`")
                st.json(a["resultat"], expanded=False)
    if not cle:
        st.info("Ajoutez une clé d'API dans la barre latérale pour activer la conversation.")

with onglets[5]:
    st.markdown(
        "Toutes les hypothèses sont dans un seul fichier, **config/hypotheses.yaml**, avec leur source. "
        "Le réseau d'usines est fictif ; les niveaux, prévisions et prix sont réels."
    )
    st.markdown("#### Contrôle du modèle de navigation face aux faits publiés")
    from kaub.modele import navigation as nav

    k = cfg.stations["KAUB"]
    st.dataframe(
        pd.DataFrame(
            [
                {"Fait publié": "14/08/2026 : chenal « un peu plus de 1,20 m » à 8 cm (service des voies navigables)", "Modèle": f"{nb(float(nav.profondeur_chenal_cm(k, 8)))} cm"},
                {"Fait publié": "La plupart des bateaux chargent à plein vers 150 cm (presse, 3/09/2026)", "Modèle": f"chargement {pct(float(nav.taux_chargement(k, cfg.bateau, 150)))}"},
                {"Fait publié": "Vers 25 cm, un tiers à la moitié de la charge (VerkehrsRundschau, 4/08/2026)", "Modèle": f"chargement {pct(float(nav.taux_chargement(k, cfg.bateau, 25)))}"},
                {"Fait publié": "Vers 25 cm, fret multiplié par 3 à 4 (VerkehrsRundschau, 4/08/2026)", "Modèle": f"× {nb(float(nav.multiplicateur_fret(k, cfg.bateau, cfg.marche_fret, 25)), 2)} (calage)"},
                {"Fait publié": "À −6 cm, 14 bateaux au lieu de 3 pour 4 600 t (Transport Online, 2/10/2026)", "Modèle": f"chargement {pct(float(nav.taux_chargement(k, cfg.bateau, -6)))} : prudent par eaux extrêmement basses"},
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.code(Path(CHEMIN_CONFIG).read_text(encoding="utf-8"), language="yaml")
