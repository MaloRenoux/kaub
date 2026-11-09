"""Analyse du 9 novembre 2026 (données réelles) et note du matin rédigée par le gabarit."""

import json

from kaub import journal
from kaub.agent.verificateur import verifier
from kaub.note import rediger


def test_analyse_complete_et_serialisable(analyse):
    json.dumps(analyse, default=float)
    assert analyse["date"] == "2026-11-09"
    assert set(analyse["usines"]) == {"A", "B", "C"}
    assert analyse["stations"]["KAUB"]["niveau_cm"] == 11.0
    assert analyse["alerte_globale"] in {"VERT", "ORANGE", "ROUGE"}


def test_usine_rail_route_insensible_au_rhin(analyse):
    c = analyse["usines"]["C"]
    assert c["station_reference"] is None
    assert c["niveau_alerte"] == "VERT"


def test_usine_A_en_alerte_le_9_novembre(analyse):
    # Kaub à 11 cm : l'usine A (70 % par péniche) doit être en alerte, avec une option qui ramène le risque sous 10 %
    a = analyse["usines"]["A"]
    assert a["niveau_alerte"] in {"ORANGE", "ROUGE"}
    reco = next(o for o in a["options"] if o["option"] == a["recommandation"]["option"])
    assert reco["proba_rupture"] <= 0.10


def test_note_gabarit(analyse):
    note = rediger(analyse)
    for section in ("# KAUB — Note du 9 novembre 2026", "## Situation", "## Impact et options par usine", "Recommandation", "fictif"):
        assert section in note
    # tous les chiffres du gabarit viennent de l'analyse
    rapport = verifier(note, [analyse])
    assert rapport.ok, rapport.resume()


def test_journal(tmp_path, analyse):
    f = tmp_path / "decisions.jsonl"
    journal.enregistrer_recommandation(analyse, f)
    journal.enregistrer_decision("2026-11-09", "A", "Basculer 30 % des volumes sur le rail", "Malo", retenue=False, commentaire="pas de sillons disponibles", fichier=f)
    assert len(journal.lire(fichier=f)) == 4
    assert "pas de sillons" in journal.options_ecartees("A", f)["Basculer 30 % des volumes sur le rail"]
