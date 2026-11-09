"""Chargement du fichier d'hypothèses (config/hypotheses.yaml) dans des objets Python validés.

On utilise pydantic : si une valeur manque ou a le mauvais type, le programme s'arrête avec un message
clair au lieu de calculer des résultats faux en silence.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

from kaub.hydro.glofas import CorrectionGlofas
from kaub.hydro.tarage import CourbeTarage

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_CONFIG = RACINE / "config" / "hypotheses.yaml"


class Tarage(BaseModel):
    W0: float
    c: float
    n: float
    erreur_m3s: float
    source: str

    def courbe(self) -> CourbeTarage:
        return CourbeTarage(self.W0, self.c, self.n)


class ParamCorrection(BaseModel):
    decalage_jours: int
    fenetre_jours: int
    coef_base: float
    coef_rapide: float
    erreur_m3s: float

    def correction(self) -> CorrectionGlofas:
        return CorrectionGlofas(self.decalage_jours, self.fenetre_jours, self.coef_base, self.coef_rapide)


class PointGlofas(BaseModel):
    latitude: float
    longitude: float


class Station(BaseModel):
    nom: str
    pegelonline: str
    glw_cm: float
    tuglw_cm: float
    seuil_fin_obligation_transport_cm: float
    seuil_navigation_risquee_cm: float
    debit_plancher_m3s: float
    glofas: PointGlofas
    tarage: Tarage
    correction_glofas: ParamCorrection


class Bateau(BaseModel):
    nom: str
    port_en_lourd_t: float
    tirant_eau_max_cm: float
    tirant_eau_lege_cm: float
    pied_de_pilote_cm: float


class MarcheFret(BaseModel):
    elasticite: float
    multiplicateur_max: float
    taux_chargement_min_navigation: float
    flotte_flexible: float


class Couts(BaseModel):
    manutention_eur_t: float
    stockage_eur_t_semaine: float
    rail_surcout_crise: float
    camion_eur_t_km: float
    camion_max_t_jour: float
    camion_delai_jours: int
    rail_delai_jours: int
    rail_part_max_supplementaire: float
    penalite_rupture_eur_t: float


class Energie(BaseModel):
    gaz_mwh_par_t_ble: float
    facteur_emission_t_co2_par_mwh: float
    part_quotas_gratuits: float


class Produits(BaseModel):
    valeur_eur_par_t_ble: float
    base_regionale_ble_eur_t: float


class ApproPeniche(BaseModel):
    part: float
    station: Optional[str]
    distance_km: float
    fret_base_eur_t: float


class ApproRail(BaseModel):
    part: float
    distance_km: float
    fret_eur_t: float


class ApproCamion(BaseModel):
    part: float
    distance_km: float


class Approvisionnement(BaseModel):
    peniche: ApproPeniche
    rail: ApproRail
    camion: ApproCamion


class Usine(BaseModel):
    nom: str
    consommation_t_jour: float
    stock_initial_jours: float
    capacite_silo_t: float
    stock_securite_jours: float
    approvisionnement: Approvisionnement
    inspiration: str


class Alertes(BaseModel):
    horizon_jours: int
    rouge_proba_rupture: float
    orange_proba_rupture: float
    orange_taux_chargement: float
    orange_jours_consecutifs: int


class Config(BaseModel):
    stations: dict[str, Station]
    bateau: Bateau
    marche_fret: MarcheFret
    couts: Couts
    energie: Energie
    produits: Produits
    usines: dict[str, Usine]
    alertes: Alertes


@lru_cache(maxsize=4)
def charger_config(chemin: str | Path = CHEMIN_CONFIG) -> Config:
    """Lit le fichier YAML et renvoie la configuration validée (mise en cache)."""
    with open(chemin, encoding="utf-8") as f:
        return Config.model_validate(yaml.safe_load(f))
