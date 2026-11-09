"""Prix de marché : blé, maïs, gaz et carbone.

- Gaz : contrat à terme TTF (Title Transfer Facility, marché de référence du gaz en Europe), via le
  service de cotations public de Yahoo Finance (symbole TTF=F, cours différés).
- Carbone : titre CO2.L, adossé à des quotas EUA (European Union Allowance, quota d'émission du marché
  carbone européen) ; c'est une approximation du prix du quota, signalée comme telle.
- Blé et maïs Euronext : pas d'interface gratuite. On les saisit en 10 secondes par jour dans
  data/historique/prix_manuels.csv, à partir de la page publique d'Euronext (cours différés).
  À défaut, le blé de Chicago (ZW=F) sert d'indicateur de secours, clairement signalé.

Conditions d'usage : ces cours différés sont consultés pour un prototype personnel, sans redistribution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import requests

from kaub.config import RACINE

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
ENTETES = {"User-Agent": "Mozilla/5.0 (KAUB prototype)"}
FICHIER_MANUEL = RACINE / "data" / "historique" / "prix_manuels.csv"
TONNES_PAR_BOISSEAU_BLE = 0.0272155  # un boisseau de blé = 27,2155 kg


@dataclass
class Prix:
    produit: str
    valeur: float
    unite: str
    date: str
    source: str
    approximation: bool = False

    def en_dict(self) -> dict:
        return asdict(self)


def cours_yahoo(symbole: str, timeout: float = 20) -> tuple[float, str]:
    """Dernier cours et sa date (AAAA-MM-JJ) pour un symbole Yahoo Finance."""
    r = requests.get(YAHOO.format(symbole), params={"range": "5d", "interval": "1d"}, headers=ENTETES, timeout=timeout)
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    return float(meta["regularMarketPrice"]), pd.Timestamp(meta["regularMarketTime"], unit="s").strftime("%Y-%m-%d")


def prix_manuels(chemin: Path = FICHIER_MANUEL) -> pd.DataFrame:
    if not Path(chemin).exists():
        return pd.DataFrame(columns=["date", "produit", "valeur", "unite", "echeance", "source", "url"])
    return pd.read_csv(chemin, comment="#")


def dernier_manuel(produit: str, chemin: Path = FICHIER_MANUEL) -> Prix | None:
    df = prix_manuels(chemin)
    df = df[df["produit"] == produit]
    if df.empty:
        return None
    ligne = df.sort_values("date").iloc[-1]
    return Prix(produit, float(ligne["valeur"]), ligne["unite"], str(ligne["date"]), f"{ligne['source']} (saisie manuelle)")


def prix_du_jour() -> dict[str, Prix]:
    """Récupère tous les prix ; chaque prix porte sa source et sa date. Ne lève pas d'erreur : un prix
    indisponible est simplement absent, et l'agent le signale."""
    prix: dict[str, Prix] = {}
    try:
        v, d = cours_yahoo("TTF=F")
        prix["gaz_ttf"] = Prix("gaz_ttf", v, "EUR/MWh", d, "Yahoo Finance, TTF=F (contrat à terme TTF)")
    except Exception:  # noqa: BLE001 — une source en panne ne doit pas bloquer la note
        pass
    try:
        v, d = cours_yahoo("CO2.L")
        prix["carbone_eua"] = Prix("carbone_eua", v, "EUR/t CO2", d, "Yahoo Finance, CO2.L (titre adossé à des quotas EUA)", approximation=True)
    except Exception:  # noqa: BLE001
        pass
    for produit in ("ble_euronext", "mais_euronext"):
        p = dernier_manuel(produit)
        if p:
            prix[produit] = p
    if "ble_euronext" not in prix:
        try:
            usc, d = cours_yahoo("ZW=F")
            eurusd, _ = cours_yahoo("EURUSD=X")
            eur_t = usc / 100 / TONNES_PAR_BOISSEAU_BLE / eurusd
            prix["ble_euronext"] = Prix(
                "ble_euronext", round(eur_t, 2), "EUR/t", d, "Blé de Chicago ZW=F converti en €/t (indicateur de secours, PAS le prix Euronext)", approximation=True
            )
        except Exception:  # noqa: BLE001
            pass
    return prix


def prix_reference(chemin: Path) -> dict[str, Prix]:
    """Prix figés d'un fichier de référence (mode hors ligne)."""
    df = pd.read_csv(chemin, comment="#")
    out = {}
    for _, l in df.iterrows():
        out[l["produit"]] = Prix(l["produit"], float(l["valeur"]), l["unite"], str(l["date"]), l["source"], approximation=l["produit"] == "carbone_eua")
    return out
