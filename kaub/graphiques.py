"""Graphiques : une image fixe pour le rapport de rejeu (matplotlib) et des graphiques interactifs pour le
tableau de bord (plotly). Couleurs : une palette validée pour les daltoniens, couleurs d'état réservées
aux niveaux d'alerte."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.ticker  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

BLEU, ORANGE_SERIE, GRIS = "#2a78d6", "#eb6834", "#898781"
ENCRE, ENCRE_2, GRILLE, AXE, FOND = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
ETATS = {"VERT": "#0ca30c", "ORANGE": "#fab219", "ROUGE": "#d03b3b"}
LIBELLES_ETAT = {"VERT": "vert", "ORANGE": "orange : < 40 cm probable sous 3 sem.", "ROUGE": "rouge : < 25 cm probable sous 3 sem."}


def _style_axes(ax):
    ax.set_facecolor(FOND)
    for c in ("top", "right"):
        ax.spines[c].set_visible(False)
    for c in ("left", "bottom"):
        ax.spines[c].set_color(AXE)
    ax.tick_params(colors=ENCRE_2, labelsize=9)
    ax.grid(axis="y", color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)


def figure_rejeu_png(serie: pd.DataFrame, jours: pd.DataFrame, resume: dict, ancres: pd.DataFrame, erreur_cm: float, chemin) -> None:
    """Niveau de Kaub pendant l'été 2026, relevés de presse, seuils, et alertes que KAUB aurait données."""
    plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]
    fig = plt.figure(figsize=(11, 6.2), facecolor=FOND)
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 11], hspace=0.08)
    ax_a, ax = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    debut, fin = jours.index.min(), jours.index.max()
    s = serie.loc[debut:fin]
    reco = s.source.str.startswith("reconstitué")

    # Bande d'incertitude de la série reconstituée (erreur moyenne de la validation croisée)
    ax.fill_between(s.index, s.niveau_cm - erreur_cm, s.niveau_cm + erreur_cm, where=reco, color=BLEU, alpha=0.12, linewidth=0, label=f"incertitude de la reconstitution (± {erreur_cm:.0f} cm)")
    ax.plot(s.index[reco], s.niveau_cm[reco], color=BLEU, linewidth=2, label="Kaub, série reconstituée (GloFAS corrigé, ancré sur la presse)")
    off = s[~reco]
    ax.plot(off.index, off.niveau_cm, color="#184f95", linewidth=2, label="Kaub, mesure officielle (PEGELONLINE)")
    a = ancres[(ancres.date >= debut) & (ancres.date <= fin)]
    ax.scatter(a.date, a.niveau_cm, s=46, color=ORANGE_SERIE, edgecolor=FOND, linewidth=1.5, zorder=5, label="relevé publié dans la presse")
    for y, txt in ((40, "40 cm : navigation à peine rentable (Contargo)"), (25, "25 cm : record de 2018")):
        ax.axhline(y, color=GRIS, linewidth=1, linestyle=(0, (4, 3)))
        ax.text(debut + pd.Timedelta(days=2), y + 1.5, txt, ha="left", va="bottom", fontsize=8.5, color=ENCRE_2)

    # Repères : première alerte et passage sous 10 cm
    o = pd.Timestamp(resume["premiere_alerte_orange"]) if resume.get("premiere_alerte_orange") else None
    d10 = pd.Timestamp(resume["premier_passage_sous_10cm"]) if resume.get("premier_passage_sous_10cm") else None
    haut = float(s.niveau_cm.max()) * 1.05
    if o is not None:
        ax.vlines(o, float(s.niveau_cm.loc[o]), haut, color=ENCRE, linewidth=1)
        ax.annotate(
            f"1re alerte KAUB\n{o:%d/%m} — Kaub à {resume['niveau_premiere_alerte_orange_cm']:.0f} cm",
            xy=(o, haut), xytext=(6, 0), textcoords="offset points", fontsize=9, color=ENCRE, va="top",
        )
    if d10 is not None:
        ax.vlines(d10, float(s.niveau_cm.loc[d10]), haut, color=ENCRE, linewidth=1)
        ax.annotate(
            f"sous 10 cm\n{d10:%d/%m}" + (f" — {resume['avance_orange_sur_10cm_jours']} jours plus tard" if resume.get("avance_orange_sur_10cm_jours") else ""),
            xy=(d10, haut), xytext=(6, 0), textcoords="offset points", fontsize=9, color=ENCRE, va="top",
        )
    _style_axes(ax)
    ax.set_ylabel("niveau à l'échelle de Kaub (cm)", color=ENCRE_2, fontsize=9.5)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: mois[mdates.num2date(x).month - 1]))
    ax.set_xlim(debut, fin)
    ax.legend(loc="lower left", fontsize=8.5, frameon=False, labelcolor=ENCRE_2)

    # Bandeau des alertes
    couleurs = [ETATS[x] for x in jours.alerte]
    ax_a.bar(jours.index, np.ones(len(jours)), width=1.0, color=couleurs, linewidth=0, align="edge")
    ax_a.set_xlim(debut, fin)
    ax_a.set_yticks([])
    ax_a.set_xticks([])
    for c in ax_a.spines.values():
        c.set_visible(False)
    ax_a.set_title(
        "Rejeu de l'été 2026 : ce que KAUB aurait annoncé chaque matin, en ne voyant que le passé",
        loc="left", fontsize=12, color=ENCRE, pad=26, fontweight="semibold",
    )
    for x, (k, lib) in zip((0.0, 0.10, 0.45), LIBELLES_ETAT.items()):
        ax_a.text(x, 1.18, "■", transform=ax_a.transAxes, color=ETATS[k], fontsize=11, va="bottom")
        ax_a.text(x + 0.018, 1.18, f"alerte {lib}", transform=ax_a.transAxes, color=ENCRE_2, fontsize=8.5, va="bottom")
    fig.text(0.01, 0.01, "Sources : PEGELONLINE (WSV), Open-Meteo / GloFAS (Copernicus), presse allemande (relevés datés), Contargo. Réseau d'usines fictif.", fontsize=7.5, color=GRIS)
    fig.savefig(chemin, dpi=160, bbox_inches="tight", facecolor=FOND)
    plt.close(fig)


# ---------------------------------------------------------------- graphiques interactifs (tableau de bord)

def _mise_en_page(fig: go.Figure, titre: str, y_titre: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=titre, x=0, font=dict(size=15, color=ENCRE)),
        plot_bgcolor=FOND,
        paper_bgcolor=FOND,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=ENCRE_2, size=12),
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.15, x=0),
        yaxis=dict(title=y_titre, gridcolor=GRILLE, zeroline=False),
        xaxis=dict(gridcolor=GRILLE, showgrid=False, linecolor=AXE),
    )
    return fig


def figure_niveau_et_prevision(journalier: pd.DataFrame, prevision, seuils: dict, nom: str) -> go.Figure:
    """30 derniers jours mesurés, puis éventail de la prévision (10–90 %) et médiane."""
    fig = go.Figure()
    passe = journalier["moyenne"].dropna().iloc[-31:]
    fig.add_trace(go.Scatter(x=passe.index, y=passe.values, name="mesuré (moyenne du jour)", line=dict(color="#184f95", width=2), hovertemplate="%{y:.0f} cm"))
    if prevision is not None:
        c = prevision.centiles()
        fig.add_trace(go.Scatter(x=c.index, y=c.p90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=c.index, y=c.p10, fill="tonexty", fillcolor="rgba(42,120,214,0.15)", line=dict(width=0), name="prévision : 80 % des scénarios", hovertemplate="10 % : %{y:.0f} cm"))
        fig.add_trace(go.Scatter(x=c.index, y=c.p50, name="prévision médiane", line=dict(color=BLEU, width=2, dash="dot"), hovertemplate="médiane : %{y:.0f} cm"))
    for cle, lib in (("chargement_moitie", "péniches à moitié vides"), ("navigation_risquee", "navigation à peine rentable")):
        fig.add_hline(y=seuils[cle], line=dict(color=GRIS, width=1, dash="dash"), annotation_text=f"{seuils[cle]:.0f} cm : {lib}", annotation_font_color=ENCRE_2, annotation_position="top left")
    return _mise_en_page(fig, f"{nom} : niveau mesuré et prévision à six semaines", "cm à l'échelle")


def figure_options(options: list[dict], usine: str) -> go.Figure:
    """Coût moyen des options (barres) ; le risque de rupture est écrit sur chaque barre."""
    opts = [o for o in options if not o.get("sans_effet")]
    noms = [o["option"] for o in opts][::-1]
    couts = [o["cout_moyen_eur"] / 1000 for o in opts][::-1]
    risques = [o["proba_rupture"] for o in opts][::-1]
    couleurs = [BLEU if i == len(opts) - 1 else "#86b6ef" for i in range(len(opts))]
    fig = go.Figure(
        go.Bar(
            x=couts, y=noms, orientation="h", marker=dict(color=couleurs, line=dict(color=FOND, width=2)),
            text=[f"{c:,.0f} k€ · rupture {r:.0%}".replace(",", " ") for c, r in zip(couts, risques)], textposition="outside",
            hovertemplate="%{y}<br>coût moyen : %{x:,.0f} k€<extra></extra>",
        )
    )
    fig = _mise_en_page(fig, f"Usine {usine} : coût moyen sur six semaines (recommandée en foncé)", "")
    fig.update_layout(hovermode="closest", xaxis=dict(title="k€", gridcolor=GRILLE, showgrid=True), height=60 + 55 * len(opts))
    return fig


def figure_rejeu(serie: pd.DataFrame, jours: pd.DataFrame, ancres: pd.DataFrame) -> go.Figure:
    debut, fin = jours.index.min(), jours.index.max()
    s = serie.loc[debut:fin]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.niveau_cm, name="Kaub (reconstitué puis officiel)", line=dict(color=BLEU, width=2), customdata=s.source, hovertemplate="%{y:.0f} cm · %{customdata}<extra></extra>"))
    a = ancres[(ancres.date >= debut) & (ancres.date <= fin)]
    fig.add_trace(go.Scatter(x=a.date, y=a.niveau_cm, mode="markers", name="relevé de presse", marker=dict(size=9, color=ORANGE_SERIE, line=dict(color=FOND, width=2)), customdata=a.source, hovertemplate="%{y:.0f} cm · %{customdata}<extra></extra>"))
    for etat in ("ORANGE", "ROUGE"):
        j = jours[jours.alerte == etat]
        fig.add_trace(go.Scatter(x=j.index, y=[s.niveau_cm.max() * 1.08] * len(j), mode="markers", marker=dict(symbol="square", size=7, color=ETATS[etat]), name=f"alerte {etat.lower()}", hovertemplate=f"alerte {etat.lower()}<extra></extra>"))
    for y, lib in ((40, "40 cm"), (25, "25 cm (record 2018)")):
        fig.add_hline(y=y, line=dict(color=GRIS, width=1, dash="dash"), annotation_text=lib, annotation_position="top left", annotation_font_color=ENCRE_2)
    return _mise_en_page(fig, "Rejeu de l'été 2026 à Kaub", "cm à l'échelle")
