"""L'agent : Claude lit les données du jour en appelant les outils, puis rédige la note ou répond à une question.

Boucle d'agent : le « tool runner » du SDK (kit de développement) Python d'Anthropic envoie la demande à
Claude, exécute les outils que Claude demande, lui renvoie les résultats, et recommence jusqu'à ce que
Claude ait fini. Documentation : https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from kaub.agent.outils import Contexte, fabriquer_outils
from kaub.agent.verificateur import Rapport, verifier
from kaub.format import date_fr

MODELE_PAR_DEFAUT = "claude-sonnet-5-5"

SYSTEME = """Tu es KAUB, un agent d'aide à la décision pour une équipe d'approvisionnement (achats de céréales \
et d'énergie, logistique, gestion des risques) d'un réseau FICTIF de trois usines d'amidon : A (bord du Rhin \
inférieur, approvisionnée par péniche via Kaub), B (Benelux, via Duisburg-Ruhrort) et C (rail et route).

Règles impératives :
1. Tu ne calcules RIEN toi-même : ni addition, ni différence, ni pourcentage, ni conversion. Chaque chiffre \
que tu écris doit apparaître tel quel (ou arrondi) dans le résultat d'un outil. S'il te manque un chiffre, \
appelle l'outil adapté ; s'il n'existe pas, dis que l'information n'est pas disponible.
2. Écris les probabilités en pourcentage (« 46 % »), les montants importants en k€.
3. Le réseau d'usines, les stocks et les coûts sont fictifs ; les niveaux, prévisions et prix sont réels. \
Dis-le dès la première ligne.
4. Tu proposes, un humain décide : formule la recommandation comme une proposition à valider.
5. Avant de recommander, consulte les décisions passées : si l'équipe a écarté une option, signale-le.
6. Si une usine est en alerte ORANGE ou ROUGE, dépose une alerte (deposer_alerte) et prépare un brouillon \
pour l'équipe logistique (preparer_brouillon_logistique). Ne prétends jamais avoir envoyé quoi que ce soit.
7. Définis brièvement chaque sigle à sa première apparition (par exemple TTF, marché de référence du gaz en Europe).
8. Style : français clair et sobre, phrases courtes, pas d'emphase. Cite les sources (PEGELONLINE, GloFAS via \
Open-Meteo, Euronext, Yahoo Finance)."""

CONSIGNE_NOTE = """Rédige la note du matin du {date} : une page au plus, en Markdown, avec ce plan :
# KAUB — Note du {date}
1. Situation (niveaux du Rhin, prévision à six semaines, pluie, prix) ;
2. Impact par usine (coût rendu, marge, jours d'autonomie), en commençant par la plus exposée ;
3. Deux ou trois options chiffrées pour chaque usine en alerte (coût, risque de rupture, hypothèses) ;
4. Recommandation, à valider par le responsable logistique ;
5. Sources et limites (une ou deux lignes).
Commence par appeler les outils dont tu as besoin."""


@dataclass
class ResultatAgent:
    texte: str
    appels: list[dict]
    verification: Rapport
    modele: str


def lancer(ctx: Contexte, demande: str | None = None, modele: str | None = None, client=None, max_iterations: int = 20) -> ResultatAgent:
    """Lance l'agent. Sans `demande`, il rédige la note du matin ; sinon il répond à la question posée."""
    import anthropic  # importé ici pour que le reste du projet fonctionne sans clé d'API

    modele = modele or os.environ.get("KAUB_MODELE", MODELE_PAR_DEFAUT)
    client = client or anthropic.Anthropic()
    consigne = demande or CONSIGNE_NOTE.format(date=date_fr(ctx.analyse["date"]))
    runner = client.beta.messages.tool_runner(
        model=modele,
        max_tokens=4096,
        system=SYSTEME,
        tools=fabriquer_outils(ctx),
        messages=[{"role": "user", "content": consigne}],
        max_iterations=max_iterations,
    )
    final = runner.until_done()
    texte = "".join(b.text for b in final.content if getattr(b, "type", "") == "text").strip()
    return ResultatAgent(texte, ctx.registre.appels, verifier(texte, ctx.registre.resultats), modele)
