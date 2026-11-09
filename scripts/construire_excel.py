"""Construit la version Excel du modèle de coût (excel/modele_cout_kaub.xlsx), pour qu'un trader puisse le lire
et le modifier sans Python. Toutes les cellules de calcul sont des formules ; les hypothèses viennent de
config/hypotheses.yaml (en bleu dans le classeur), et une feuille « Contrôle » compare Excel et Python.

    python scripts/construire_excel.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kaub.config import RACINE, charger_config  # noqa: E402
from kaub.modele.couts import cout_rendu_usine  # noqa: E402
from kaub.modele.marge import marge_usine  # noqa: E402
from kaub.modele import navigation as nav  # noqa: E402
from kaub.situation import REF  # noqa: E402
from kaub.sources.prix import prix_reference  # noqa: E402

POLICE = "Arial"
BLEU = Font(name=POLICE, color="0000FF")
NOIR = Font(name=POLICE, color="000000")
VERT = Font(name=POLICE, color="008000")
GRAS = Font(name=POLICE, bold=True)
TITRE = Font(name=POLICE, bold=True, size=14)
JAUNE = PatternFill("solid", start_color="FFFF00")
ENTETE = PatternFill("solid", start_color="E8EEF8")
FILET = Border(bottom=Side(style="thin", color="C3C2B7"))


def construire(chemin: Path) -> None:
    cfg = charger_config()
    prix = prix_reference(REF / "prix_2026-11-09.csv")
    k, b, m, c, e, u = cfg.stations["KAUB"], cfg.bateau, cfg.marche_fret, cfg.couts, cfg.energie, cfg.usines["A"]
    wb = Workbook()

    # ------------------------------------------------------------ Hypothèses
    h = wb.active
    h.title = "Hypothèses"
    h["A1"] = "KAUB — modèle de coût de l'usine A (fictive), version Excel"
    h["A1"].font = TITRE
    h["A2"] = "Bleu : hypothèse modifiable · Noir : formule · Vert : lien vers une autre feuille · Jaune : levier de scénario. Réseau d'usines FICTIF."
    h["A2"].font = Font(name=POLICE, italic=True, color="52514E")
    lignes = [
        ("Scénario", None, None, None),
        ("Niveau de Kaub (cm)", 11, "cm", "Levier : niveau lu à l'échelle de Kaub (PEGELONLINE, 9/11/2026 : 11 cm)"),
        ("Station de Kaub", None, None, None),
        ("GlW (niveau d'étiage de référence)", k.glw_cm, "cm", "PEGELONLINE, valeurs caractéristiques (valable depuis 2023)"),
        ("TuGlW (profondeur garantie au GlW)", k.tuglw_cm, "cm", "PEGELONLINE"),
        ("Bateau type", None, None, None),
        ("Port en lourd", b.port_en_lourd_t, "t", "Hypothèse : automoteur vrac de 2 000 t"),
        ("Tirant d'eau maximal", b.tirant_eau_max_cm, "cm", "Hypothèse"),
        ("Tirant d'eau à vide", b.tirant_eau_lege_cm, "cm", "Hypothèse"),
        ("Pied de pilote (marge sous la quille)", b.pied_de_pilote_cm, "cm", "Contargo, brochure basses eaux (2017)"),
        ("Marché du fret", None, None, None),
        ("Élasticité du fret au taux de chargement", m.elasticite, "", "Calée : fret × 3,5 vers 25 cm (VerkehrsRundschau, 4/08/2026)"),
        ("Multiplicateur maximal", m.multiplicateur_max, "×", "Hypothèse"),
        ("Taux de chargement minimal pour naviguer", m.taux_chargement_min_navigation, "", "Hypothèse"),
        ("Prix (9 novembre 2026)", None, None, None),
        ("Blé de meunerie Euronext", prix["ble_euronext"].valeur, "€/t", prix["ble_euronext"].source),
        ("Gaz TTF (marché de référence européen)", prix["gaz_ttf"].valeur, "€/MWh", prix["gaz_ttf"].source),
        ("Quota carbone EUA (marché carbone européen)", prix["carbone_eua"].valeur, "€/t CO2", prix["carbone_eua"].source),
        ("Usine A (fictive)", None, None, None),
        ("Consommation de blé", u.consommation_t_jour, "t/jour", "Hypothèse"),
        ("Part péniche", u.approvisionnement.peniche.part, "", "Hypothèse"),
        ("Part rail", u.approvisionnement.rail.part, "", "Hypothèse"),
        ("Part camion", u.approvisionnement.camion.part, "", "Hypothèse"),
        ("Fret péniche en eaux normales", u.approvisionnement.peniche.fret_base_eur_t, "€/t", "Hypothèse"),
        ("Fret rail", u.approvisionnement.rail.fret_eur_t, "€/t", "Hypothèse"),
        ("Fret camion par km", c.camion_eur_t_km, "€/t/km", "Hypothèse"),
        ("Distance camion", u.approvisionnement.camion.distance_km, "km", "Hypothèse"),
        ("Manutention", c.manutention_eur_t, "€/t", "Hypothèse"),
        ("Base régionale du blé", cfg.produits.base_regionale_ble_eur_t, "€/t", "Hypothèse neutre"),
        ("Énergie, carbone, produits", None, None, None),
        ("Gaz consommé par tonne de blé", e.gaz_mwh_par_t_ble, "MWh/t", "Hypothèse"),
        ("Facteur d'émission du gaz", e.facteur_emission_t_co2_par_mwh, "t CO2/MWh", "GIEC 2006 : 56,1 t CO2/TJ"),
        ("Part couverte par des quotas gratuits", e.part_quotas_gratuits, "", "Hypothèse"),
        ("Valeur des produits par tonne de blé", cfg.produits.valeur_eur_par_t_ble, "€/t", "Hypothèse NON sourcée, ordre de grandeur"),
    ]
    h.append([])
    for i, (lib, val, unite, src) in enumerate(lignes, start=4):
        h.cell(i, 1, lib)
        if val is None:
            h.cell(i, 1).font = GRAS
            h.cell(i, 1).fill = ENTETE
            for col in range(2, 5):
                h.cell(i, col).fill = ENTETE
            continue
        h.cell(i, 1).font = NOIR
        cel = h.cell(i, 2, val)
        cel.font = BLEU
        cel.number_format = "0.00%" if unite == "" and val <= 1 and lib.startswith(("Part", "Taux")) else "#,##0.00"
        h.cell(i, 3, unite).font = NOIR
        h.cell(i, 4, src).font = Font(name=POLICE, color="52514E", size=9)
    noms = {lib: f"Hypothèses!$B${i}" for i, (lib, val, *_ ) in enumerate(lignes, start=4) if val is not None}
    h[noms["Niveau de Kaub (cm)"].split("!")[1].replace("$", "")].fill = JAUNE
    h.column_dimensions["A"].width = 46
    h.column_dimensions["B"].width = 14
    h.column_dimensions["C"].width = 11
    h.column_dimensions["D"].width = 90
    R = {cle: noms[cle] for cle in noms}

    def ref(lib):
        return R[lib]

    # ------------------------------------------------------------ Calcul pas à pas
    s = wb.create_sheet("Calcul")
    s["A1"] = "Du niveau du Rhin à la marge de l'usine A, étape par étape"
    s["A1"].font = TITRE
    s.append([])
    s.append(["Étape", "Valeur", "Unité", "Formule en clair"])
    for col in range(1, 5):
        s.cell(3, col).font = GRAS
        s.cell(3, col).fill = ENTETE
    N = ref("Niveau de Kaub (cm)")
    etapes = [
        ("Niveau de Kaub", f"={N}", "cm", "lien vers le levier de scénario"),
        ("Profondeur du chenal", f"={ref('TuGlW (profondeur garantie au GlW)')}-{ref('GlW (niveau d’étiage de référence)'.replace('’', chr(39)))}+B4", "cm", "TuGlW − GlW + niveau"),
        ("Tirant d'eau possible", f"=B5-{ref('Pied de pilote (marge sous la quille)')}", "cm", "profondeur − pied de pilote"),
        ("Tonnes par cm d'enfoncement", f"={ref('Port en lourd')}/({ref('Tirant d’eau maximal'.replace('’', chr(39)))}-{ref('Tirant d’eau à vide'.replace('’', chr(39)))})", "t/cm", "port en lourd / (tirant max − tirant à vide)"),
        ("Charge utile", f"=MAX(0,MIN({ref('Port en lourd')},(B6-{ref('Tirant d’eau à vide'.replace('’', chr(39)))})*B7))", "t", "(tirant possible − tirant à vide) × t/cm, borné"),
        ("Taux de chargement", f"=B8/{ref('Port en lourd')}", "", "charge utile / port en lourd"),
        ("Bateaux pour en remplacer un", '=IF(B9>0,1/B9,"infini")', "", "1 / taux de chargement"),
        ("Voie d'eau ouverte ?", f'=IF(B9>={ref("Taux de chargement minimal pour naviguer")},"oui","non")', "", "taux ≥ minimum"),
        ("Multiplicateur du fret", f"=MIN(MAX(B9,{ref('Taux de chargement minimal pour naviguer')})^(-{ref('Élasticité du fret au taux de chargement')}),{ref('Multiplicateur maximal')})", "×", "taux ^ (−élasticité), plafonné"),
        ("Fret péniche", f"={ref('Fret péniche en eaux normales')}*B12", "€/t", "fret normal × multiplicateur"),
        ("Coût rendu péniche", f"={ref('Blé de meunerie Euronext')}+{ref('Base régionale du blé')}+B13+{ref('Manutention')}", "€/t", "blé + base + fret + manutention"),
        ("Coût rendu rail", f"={ref('Blé de meunerie Euronext')}+{ref('Base régionale du blé')}+{ref('Fret rail')}+{ref('Manutention')}", "€/t", "blé + base + fret rail + manutention"),
        ("Coût rendu camion", f"={ref('Blé de meunerie Euronext')}+{ref('Base régionale du blé')}+{ref('Fret camion par km')}*{ref('Distance camion')}+{ref('Manutention')}", "€/t", "blé + base + €/t/km × km + manutention"),
        ("Fret moyen du plan", f"=({ref('Part péniche')}*IF(B11=\"oui\",B13,{ref('Fret péniche en eaux normales')}*{ref('Multiplicateur maximal')})+{ref('Part rail')}*{ref('Fret rail')}+{ref('Part camion')}*{ref('Fret camion par km')}*{ref('Distance camion')})/({ref('Part péniche')}+{ref('Part rail')}+{ref('Part camion')})", "€/t", "moyenne pondérée par les parts du plan ; voie fermée : fret maximal"),
        ("Blé rendu usine (moyenne)", f"={ref('Blé de meunerie Euronext')}+{ref('Base régionale du blé')}+B17+{ref('Manutention')}", "€/t", "blé + base + fret moyen + manutention"),
        ("Coût du gaz", f"={ref('Gaz consommé par tonne de blé')}*{ref('Gaz TTF (marché de référence européen)')}", "€/t", "MWh/t × prix TTF"),
        ("Coût du carbone", f"={ref('Gaz consommé par tonne de blé')}*{ref('Facteur d’émission du gaz'.replace('’', chr(39)))}*(1-{ref('Part couverte par des quotas gratuits')})*{ref('Quota carbone EUA (marché carbone européen)')}", "€/t", "MWh × facteur × part non gratuite × prix EUA"),
        ("Marge variable par tonne", f"={ref('Valeur des produits par tonne de blé')}-B18-B19-B20", "€/t", "produits − blé rendu − gaz − carbone"),
        ("Marge variable par jour", f"=B21*{ref('Consommation de blé')}", "€/jour", "marge par tonne × consommation"),
    ]
    for i, (lib, formule, unite, clair) in enumerate(etapes, start=4):
        s.cell(i, 1, lib).font = NOIR
        cel = s.cell(i, 2, formule)
        cel.font = VERT if formule.startswith("=Hyp") else NOIR
        cel.number_format = "0.0%" if lib == "Taux de chargement" else "#,##0.00"
        s.cell(i, 3, unite).font = NOIR
        s.cell(i, 4, clair).font = Font(name=POLICE, color="52514E", size=9)
        for col in range(1, 5):
            s.cell(i, col).border = FILET
    for lib in ("Marge variable par tonne", "Marge variable par jour"):
        r = 4 + [x[0] for x in etapes].index(lib)
        s.cell(r, 1).font = GRAS
        s.cell(r, 2).font = Font(name=POLICE, bold=True)
    s.column_dimensions["A"].width = 32
    s.column_dimensions["B"].width = 14
    s.column_dimensions["C"].width = 9
    s.column_dimensions["D"].width = 62

    # ------------------------------------------------------------ Table par niveau
    t = wb.create_sheet("Table par niveau")
    t["A1"] = "Capacité des péniches et coût rendu selon le niveau de Kaub"
    t["A1"].font = TITRE
    entetes = ["Niveau (cm)", "Profondeur (cm)", "Charge utile (t)", "Taux de chargement", "Bateaux pour un", "Multiplicateur", "Fret péniche (€/t)", "Coût rendu péniche (€/t)"]
    for j, x in enumerate(entetes, start=1):
        cel = t.cell(3, j, x)
        cel.font = GRAS
        cel.fill = ENTETE
        cel.alignment = Alignment(wrap_text=True)
    niveaux = list(range(-20, 310, 10))
    for i, w in enumerate(niveaux, start=4):
        t.cell(i, 1, w).font = BLEU
        t.cell(i, 2, f"={ref('TuGlW (profondeur garantie au GlW)')}-{ref('GlW (niveau d’étiage de référence)'.replace('’', chr(39)))}+A{i}")
        t.cell(i, 3, f"=MAX(0,MIN({ref('Port en lourd')},(B{i}-{ref('Pied de pilote (marge sous la quille)')}-{ref('Tirant d’eau à vide'.replace('’', chr(39)))})*{ref('Port en lourd')}/({ref('Tirant d’eau maximal'.replace('’', chr(39)))}-{ref('Tirant d’eau à vide'.replace('’', chr(39)))})))")
        t.cell(i, 4, f"=C{i}/{ref('Port en lourd')}")
        t.cell(i, 5, f'=IF(D{i}>0,1/D{i},"")')
        t.cell(i, 6, f"=MIN(MAX(D{i},{ref('Taux de chargement minimal pour naviguer')})^(-{ref('Élasticité du fret au taux de chargement')}),{ref('Multiplicateur maximal')})")
        t.cell(i, 7, f"={ref('Fret péniche en eaux normales')}*F{i}")
        t.cell(i, 8, f"={ref('Blé de meunerie Euronext')}+{ref('Base régionale du blé')}+G{i}+{ref('Manutention')}")
        for j in range(1, 9):
            cel = t.cell(i, j)
            if j > 1:
                cel.font = NOIR
            cel.number_format = "0%" if j == 4 else "#,##0.0" if j in (5, 6, 7, 8) else "#,##0"
    for j in range(1, 9):
        t.column_dimensions[get_column_letter(j)].width = 15
    dernier = 3 + len(niveaux)
    for col, titre, y_titre, ancre in ((4, "Taux de chargement du bateau type selon le niveau de Kaub", "part du port en lourd", "J3"), (8, "Coût rendu usine du blé par péniche selon le niveau de Kaub", "€/t", "J22")):
        g = ScatterChart()
        g.title = titre
        g.style = 13
        g.x_axis.title = "niveau de Kaub (cm)"
        g.y_axis.title = y_titre
        g.legend = None
        serie = Series(Reference(t, min_col=col, min_row=4, max_row=dernier), Reference(t, min_col=1, min_row=4, max_row=dernier), title=titre)
        serie.graphicalProperties.line.solidFill = "2A78D6"
        serie.graphicalProperties.line.width = 22000
        serie.marker.symbol = "none"
        g.series.append(serie)
        g.height, g.width = 8, 16
        t.add_chart(g, ancre)

    # ------------------------------------------------------------ Contrôle Excel = Python
    v = wb.create_sheet("Contrôle")
    v["A1"] = "Contrôle : le classeur reproduit-il le code Python ?"
    v["A1"].font = TITRE
    v["A2"] = "Les valeurs Python sont calculées par kaub/modele au moment de la construction du classeur (niveau 11 cm, prix du 9/11/2026)."
    v["A2"].font = Font(name=POLICE, italic=True, color="52514E")
    for j, x in enumerate(["Grandeur", "Excel", "Python", "Écart"], start=1):
        v.cell(4, j, x).font = GRAS
        v.cell(4, j).fill = ENTETE
    rendu = cout_rendu_usine(cfg, "A", 11, prix["ble_euronext"].valeur)["modes"]
    marge = marge_usine(cfg, "A", 11, prix["ble_euronext"].valeur, prix["gaz_ttf"].valeur, prix["carbone_eua"].valeur)
    controles = [
        ("Profondeur du chenal (cm)", "Calcul!B5", float(nav.profondeur_chenal_cm(k, 11))),
        ("Taux de chargement", "Calcul!B9", float(nav.taux_chargement(k, b, 11))),
        ("Multiplicateur du fret", "Calcul!B12", float(nav.multiplicateur_fret(k, b, m, 11))),
        ("Coût rendu péniche (€/t)", "Calcul!B14", rendu["peniche"]["cout_rendu_eur_t"]),
        ("Coût rendu rail (€/t)", "Calcul!B15", rendu["rail"]["cout_rendu_eur_t"]),
        ("Marge variable (€/t)", "Calcul!B21", marge["marge_eur_t"]),
    ]
    for i, (lib, cible, valeur) in enumerate(controles, start=5):
        v.cell(i, 1, lib).font = NOIR
        v.cell(i, 2, f"={cible}").font = VERT
        cel = v.cell(i, 3, round(valeur, 4))
        cel.font = BLUE_PY
        cel.comment = Comment("Valeur calculée par le code Python (kaub/modele) pour le même niveau et les mêmes prix.", "KAUB")
        v.cell(i, 4, f"=B{i}-C{i}").font = NOIR
        for j in (2, 3, 4):
            v.cell(i, j).number_format = "#,##0.000"
    v.column_dimensions["A"].width = 30
    for col in "BCD":
        v.column_dimensions[col].width = 14

    chemin.parent.mkdir(parents=True, exist_ok=True)
    wb.save(chemin)


BLUE_PY = Font(name=POLICE, color="0000FF")

if __name__ == "__main__":
    sortie = RACINE / "excel" / "modele_cout_kaub.xlsx"
    construire(sortie)
    print(f"Classeur écrit : {sortie}")
