"""L'agent : outils, vérificateur de chiffres, et boucle complète contre une API simulée.

Le dernier test fait tourner le vrai « tool runner » du SDK Anthropic, mais l'API est remplacée par un
faux serveur local : on vérifie que Claude peut appeler nos outils et que le vérificateur contrôle la
réponse, sans clé d'API ni connexion.
"""

import json

try:  # le SDK Anthropic récent utilise « httpx2 », les versions plus anciennes « httpx »
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx
import pytest

from kaub.agent.agent import lancer
from kaub.agent.outils import Contexte, fabriquer_outils
from kaub.agent.verificateur import verifier


@pytest.fixture
def ctx(cfg, situation, analyse, tmp_path):
    return Contexte(cfg, situation, analyse, dossier_sorties=tmp_path)


def test_schemas_des_outils(ctx):
    outils = fabriquer_outils(ctx)
    noms = {t.name for t in outils}
    assert {"lire_niveaux_rhin", "lire_prevision", "comparer_options", "projeter_couverture", "deposer_alerte"} <= noms
    for t in outils:
        d = t.to_dict()
        assert d["description"] and d["input_schema"]["type"] == "object"


def test_outils_calculent_et_enregistrent(ctx):
    o = {t.name: t for t in fabriquer_outils(ctx)}
    r = json.loads(o["projeter_couverture"].call({"usine": "A", "fermeture_jours": 10}))
    assert r["premier_jour_rupture"] is not None
    r = json.loads(o["chiffrer_marge"].call({"usine": "A", "hausse_gaz_pct": 20}))
    assert r["ecart_eur_t"] < 0
    assert [a["outil"] for a in ctx.registre.appels] == ["projeter_couverture", "chiffrer_marge"]


def test_usine_inconnue(ctx):
    o = {t.name: t for t in fabriquer_outils(ctx)}
    with pytest.raises(ValueError):
        o["chiffrer_cout_rendu"].call({"usine": "Z"})


def test_ecritures_jamais_envoyees(ctx, tmp_path):
    o = {t.name: t for t in fabriquer_outils(ctx)}
    r = json.loads(o["preparer_brouillon_logistique"].call({"objet": "Test", "corps": "Bonjour"}))
    assert r["envoye"] is False
    assert (tmp_path / "brouillons").exists()


def test_verificateur_repere_un_chiffre_invente():
    outils = [{"autonomie_jours": 14.2, "taux_chargement": 0.141, "cout_moyen_eur": 917666.0}]
    ok = verifier("Autonomie de 14,2 jours ; péniches chargées à 14 % ; coût 918 k€, le 9 novembre 2026.", outils)
    assert ok.ok, ok.resume()
    ko = verifier("Autonomie de 15,8 jours.", outils)
    assert not ko.ok and ko.non_verifies == ["15,8"]


def _reponse(contenu, stop):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": contenu,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_boucle_agent_complete_avec_api_simulee(ctx):
    import anthropic

    requetes = []
    niveau = ctx.analyse["stations"]["KAUB"]["niveau_cm"]

    def serveur(request: httpx.Request) -> httpx.Response:
        corps = json.loads(request.content)
        requetes.append(corps)
        if len(requetes) == 1:
            assert {t["name"] for t in corps["tools"]} >= {"lire_niveaux_rhin", "comparer_options"}
            return httpx.Response(200, json=_reponse([
                {"type": "tool_use", "id": "toolu_1", "name": "lire_niveaux_rhin", "input": {}},
                {"type": "tool_use", "id": "toolu_2", "name": "comparer_options", "input": {"usine": "A"}},
            ], "tool_use"))
        # deuxième tour : les résultats des outils doivent avoir été renvoyés
        resultats = [b for m in corps["messages"] if m["role"] == "user" and isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result"]
        assert len(resultats) == 2
        texte = f"# KAUB — Note du 9 novembre 2026\nKaub est à {niveau:.0f} cm. Recommandation à valider."
        return httpx.Response(200, json=_reponse([{"type": "text", "text": texte}], "end_turn"))

    client = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(serveur)))
    res = lancer(ctx, client=client, modele="claude-sonnet-5-5")
    assert "Kaub est à 11 cm" in res.texte
    assert [a["outil"] for a in res.appels] == ["lire_niveaux_rhin", "comparer_options"]
    assert res.verification.ok, res.verification.resume()
    assert len(requetes) == 2
