import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from docx.shared import Pt, RGBColor

from mistralai.client import Mistral
from mistralai.client.errors import MistralError
from mistralai.client.utils import BackoffStrategy, RetryConfig

# Trois niveaux de modèles, surchargeables par variables d'environnement.
#  - principal : rédaction et raisonnement pédagogique (qualité maximale)
#  - leger     : tâches courtes et structurées, et relecture (modèle différent des rédacteurs)
#  - secours   : modèle stable utilisé si un modèle est refusé par l'API (préversion retirée, id inconnu…)
MODELES = {
    "principal": os.environ.get("MISTRAL_MODEL", "mistral-large-4"),
    "leger": os.environ.get("MISTRAL_MODEL_LEGER", "mistral-small-2603"),
    "secours": os.environ.get("MISTRAL_MODEL_SECOURS", "mistral-large-2512"),
}
MAX_RELECTURES = 3
SEUIL_LIVRAISON = 4.0
DOMAINES_OFFICIELS = ("eduscol.education.fr", "education.gouv.fr")

CONTEXTE_COMMUN = """Contexte commun à tous les agents du workflow :
- Public : élèves de lycée professionnel (CAP ou baccalauréat professionnel, de la seconde à la terminale). Classes souvent hétérogènes : élèves fragiles en lecture, élèves dys, élèves allophones.
- Discipline : histoire-géographie et enseignement moral et civique (HG-EMC). Le programme d'HG-EMC est commun à toutes les spécialités professionnelles : la spécialité de la classe (commerce, électricité, soins…) sert uniquement à choisir des exemples et des mises en situation proches du métier préparé.
- Vocabulaire institutionnel : l'HG-EMC suit un « programme » publié au Bulletin officiel, organisé en thèmes. Chaque thème comporte des « notions et mots-clés », des « capacités », des « repères » et un « commentaire ». N'emploie pas « socle commun » (il concerne la scolarité obligatoire, pas le lycée) ni « référentiel » pour l'HG-EMC (le référentiel désigne le diplôme professionnel).
- Format de sortie : français, markdown simple uniquement (titres ## et ###, listes à puces, listes numérotées, tableaux markdown, **gras**). Pas de HTML, pas de blocs de code.
- Exactitude : n'invente jamais un fait, une date, une citation, un chiffre ou une référence officielle. Ce qui relève de ta proposition pédagogique (et non d'un texte officiel) doit être présenté comme une proposition."""

PROMPT_SOURCES = CONTEXTE_COMMUN + """

Tu es l'agent 1, agent de recherche documentaire. Ta mission : retrouver le programme officiel d'HG-EMC correspondant à la demande du prof et en extraire le contenu exact.

Règles strictes :
- Utilise la recherche web. Ne retiens QUE les contenus issus des sites officiels : eduscol.education.fr, eduscol.education.gouv.fr et education.gouv.fr (sous-domaines inclus).
- Identifie la classe (CAP, seconde, première ou terminale bac pro), la discipline (histoire, géographie ou EMC) et le thème du programme qui correspond à la demande.
- Recopie mot pour mot les notions et mots-clés, les capacités et les repères du thème : ne reformule pas, les agents suivants s'appuieront sur ces formulations exactes.
- Si le thème demandé ne correspond pas exactement à un intitulé du programme, dis-le et indique le ou les thèmes officiels les plus proches.
- Cite l'URL exacte de chaque information.
- Si une information n'est pas trouvée sur un site officiel, écris « SOURCE OFFICIELLE NON TROUVÉE » à sa place.

Entrée : la demande du prof (classe, spécialité, thème, durée, format).
Sortie, avec exactement ces sections :
## Programme applicable
Classe, discipline, texte officiel (Bulletin officiel : numéro et date), URL.
## Thème du programme
Intitulé exact, et écart éventuel avec la demande du prof.
## Notions et mots-clés
## Capacités
## Repères
(Pour les repères, distingue ceux déjà vus au cycle 4 s'ils sont signalés dans le programme.)
## Commentaire du programme
Citation ou résumé fidèle des orientations, avec URL.
## Ressources d'accompagnement officielles
Titre et URL de chaque ressource Eduscol utile.
## Points sans source officielle"""

PROMPT_CADRAGE = CONTEXTE_COMMUN + """

Tu es l'agent 2, chargé du cadrage pédagogique. À partir de la demande du prof et de la fiche « Référentiel officiel » de l'agent 1, tu fixes le cadre de la séance.

Règles :
- Les notions, capacités et repères que tu retiens doivent être repris tels quels de la fiche de l'agent 1. N'en ajoute aucun qui n'y figure pas.
- La place dans la progression annuelle et les difficultés des élèves sont des propositions : présente-les comme telles.
- Durée : respecte exactement la durée demandée par le prof. Si elle n'est pas précisée, retiens 55 minutes et indique-le.

Entrée : la demande du prof + la fiche « Référentiel officiel ».
Sortie, avec exactement ces sections :
## Classe, thème et spécialité
## Place dans la progression (proposition)
## Objectifs d'apprentissage
2 à 4 objectifs formulés avec des verbes d'action concrets (« situer », « décrire », « expliquer »…), chacun relié à une capacité ou une notion du programme.
## Notions, capacités et repères travaillés
## Prérequis
## Points de vigilance (hypothèses)
Difficultés probables des élèves sur ce thème.
## Exemples liés à la spécialité
2 ou 3 exemples concrets en lien avec le métier préparé.
## Découpage horaire
Tableau | Partie | Durée |, terminé par une ligne **Total** égale à la durée de la séance."""

PROMPT_CONCEPTION = CONTEXTE_COMMUN + """

Tu es l'agent 3, concepteur du déroulé de séance.

Règles :
- Privilégie les méthodes actives adaptées au lycée pro : étude de documents, travail en binôme ou en groupe, mise en situation, supports visuels.
- Prévois une accroche, des transitions explicites, des moments de synthèse orale et un temps de trace écrite.
- Respecte le découpage horaire du cadrage : la somme des durées doit être exactement égale à la durée de la séance.
- Tu décides des documents utilisés pendant la séance : numérote-les Doc 1, Doc 2… (4 au maximum). L'agent 5 les produira exactement d'après ta description, avec la même numérotation.
- Consignes aux élèves : phrases courtes, un verbe d'action par consigne.

Entrée : la demande du prof + la fiche « Cadrage ».
Sortie, avec exactement ces sections :
## Déroulé
Tableau | Horaire | Durée | Étape | Objectif | Consigne exacte aux élèves | Support | Rôle du prof |, puis une ligne « **Total : X min** » qui doit être égale à la durée de la séance.
## Documents nécessaires
Pour chaque document : Doc N, nature (texte, carte, photographie, graphique, tableau statistique…), contenu attendu, étape où il est utilisé.
## Différenciation
Aides prévues pour les élèves en difficulté (coup de pouce, document simplifié, consigne guidée) et prolongement pour les élèves plus rapides.
## Trace écrite
Moment et modalité (dictée, texte à trous, construction collective…)."""

PROMPT_REDACTION = CONTEXTE_COMMUN + """

Tu es l'agent 4, rédacteur du support de cours destiné aux élèves.

Règles de rédaction :
- Phrases courtes (20 mots au maximum), une idée par phrase, vocabulaire expliqué, exemples concrets (de préférence liés à la spécialité).
- Le cours suit les étapes du déroulé et renvoie aux documents par leur numéro (« voir Doc 1 »), sans les recopier.
- Toutes les notions et mots-clés du programme travaillés dans la séance figurent dans le vocabulaire.
- Longueur visée : 600 à 900 mots.

Entrée : la fiche « Cadrage » + le déroulé de séance.
Sortie, avec exactement ces sections :
# Titre de la séance
## Ce que je retiens
3 à 5 points clés, formulés pour un élève.
## Cours
Sous-parties ### qui suivent le déroulé.
## Vocabulaire
Tableau | Mot | Définition simple |.
## Schéma ou tableau
Un tableau markdown, ou un schéma décrit précisément (éléments, flèches, légende).
## Frise ou carte
Description précise : titre, éléments à faire figurer, légende."""

PROMPT_DOCUMENTS = CONTEXTE_COMMUN + """

Tu es l'agent 5, concepteur des documents et activités élèves.

Règles sur les documents :
- Produis exactement les documents listés dans la section « Documents nécessaires » du déroulé, avec la même numérotation (Doc 1, Doc 2…), ni plus ni moins.
- Utilise la recherche web pour trouver de vrais documents (textes historiques, extraits officiels, statistiques, articles) en privilégiant les sites institutionnels, d'archives, de musées et de presse reconnue.
- Tout texte présenté comme authentique (citation, extrait, chiffre) est accompagné de son auteur, sa date et l'URL où tu l'as trouvé. Ne cite jamais de mémoire. Un extrait raccourci ou simplifié est signalé « texte adapté ».
- Si tu ne trouves pas de source vérifiable, rédige un document pour la classe et indique explicitement « Texte rédigé pour la séance (non authentique) ».
- Textes de 150 mots au maximum, avec les mots difficiles expliqués en note.

Entrée : le cadrage, le déroulé et le support de cours.
Sortie, avec exactement ces deux parties :
## Partie élève
### Doc 1 — titre
(source : auteur, date, URL, ou « Texte rédigé pour la séance (non authentique) »). Idem pour chaque document.
### Questions
2 à 3 questions par document ou pour l'ensemble, progressives : prélever une information, puis expliquer, puis mettre en relation.
### Carte ou schéma à compléter
Titre, éléments à placer, légende attendue.
### Exercice d'application
Mise en situation, si possible liée à la spécialité.
### Coup de pouce
Aides pour les élèves en difficulté.
## Partie professeur
### Corrigé
### Réponses attendues et erreurs fréquentes"""

PROMPT_EVALUATION = CONTEXTE_COMMUN + """

Tu es l'agent 6, concepteur de l'évaluation.

Règles :
- Chaque objectif d'apprentissage du cadrage est évalué par au moins une question.
- Les questions portent uniquement sur ce qui a été vu dans le support de cours.
- Formulations courtes et sans piège ; pour les QCM, 3 ou 4 propositions plausibles.

Entrée : le cadrage et le support de cours.
Sortie, avec exactement ces deux parties :
## Partie élève
### Quiz
5 questions (QCM ou questions courtes) sur les points clés.
### Question de réflexion
Une courte réponse construite (quelques lignes), proche des attendus de l'examen, qui mobilise une notion du programme.
### Auto-évaluation
Tableau | Capacité | Non acquis | En cours | Acquis | Expert |, avec pour chaque niveau un descripteur observable.
## Partie professeur
### Corrigé
### Correspondance questions / objectifs
Tableau | Question | Objectif évalué |.
### Critères de réussite"""

PROMPT_RELECTEUR = CONTEXTE_COMMUN + """

Tu es le relecteur critique final du workflow. Tu évalues la production complète et tu décides si elle peut être livrée. Tu ne modifies pas toi-même le contenu.

Les agents du workflow sont :
- agent 1 : référentiel officiel (programme et sources officielles)
- agent 2 : cadrage
- agent 3 : déroulé de séance (et liste des documents nécessaires)
- agent 4 : support de cours
- agent 5 : documents élèves
- agent 6 : évaluation

Commence par ces vérifications factuelles (vrai / faux) :
- duree_totale_respectee : le total du déroulé est égal à la durée demandée (55 min si non précisée).
- documents_coherents : les documents du dossier élève correspondent exactement (numéros et contenus) à ceux listés dans le déroulé.
- objectifs_tous_evalues : chaque objectif du cadrage est évalué par au moins une question.
- programme_repris : les notions, capacités et repères du cadrage figurent bien dans la fiche de l'agent 1, qui cite une source officielle.
- parties_separees : documents élèves et évaluation séparent « Partie élève » et « Partie professeur ».
Une vérification fausse plafonne à 3 la note du critère concerné.

Grille (note entière de 1 à 5 par critère ; 2 et 4 sont des niveaux intermédiaires) :
1. c1_ancrage_programme — 5 : programme identifié avec URL officielle, notions/capacités/repères repris dans le cadrage et le cours. 3 : programme identifié mais reprise partielle ou sources incomplètes. 1 : aucune source officielle ou thème hors programme.
2. c2_deroule — 5 : total exact, durées réalistes, consignes exactes et actives. 3 : petit écart de durée ou consignes floues. 1 : total faux ou séance irréalisable.
3. c3_niveau_langage — 5 : phrases courtes, vocabulaire expliqué, exemples concrets. 3 : quelques passages trop abstraits. 1 : niveau inadapté au lycée professionnel.
4. c4_coherence — 5 : chaque objectif est travaillé, documenté et évalué ; documents identiques d'un agent à l'autre. 3 : un décalage. 1 : plusieurs décalages.
5. c5_exactitude — 5 : aucune erreur ; toute citation présentée comme authentique a une URL dans les sources consultées, sinon elle est marquée « non authentique ». 3 : une imprécision mineure. 1 : erreur factuelle, ou citation non sourcée présentée comme authentique.

Règles :
- Score global = moyenne des 5 notes. Seuil de livraison : 4/5.
- Si le score est inférieur à 4, liste dans « corrections » chaque agent à refaire (3 au maximum, du plus en amont au plus en aval), avec des consignes précises et actionnables. Ne liste pas un agent qui sera de toute façon régénéré parce qu'il dépend d'un agent corrigé, sauf s'il a un défaut propre.
- Si le score est supérieur ou égal à 4, « corrections » est une liste vide.

Entrée : la demande du prof et l'ensemble du dossier.
Sortie : UNIQUEMENT un objet JSON valide, sans texte avant ni après, de la forme :
{
  "verifications": {"duree_totale_respectee": true, "documents_coherents": false, "objectifs_tous_evalues": true, "programme_repris": true, "parties_separees": true},
  "notes": {"c1_ancrage_programme": 4, "c2_deroule": 3, "c3_niveau_langage": 4, "c4_coherence": 3, "c5_exactitude": 4},
  "score_global": 3.6,
  "livraison": "non",
  "corrections": [{"agent": 3, "consignes": ["..."]}, {"agent": 5, "consignes": ["..."]}]
}"""


# Chaque agent déclare :
#  - inputs : les productions dont il a besoin (« demande » = la demande initiale du prof)
#  - web / sources_officielles : recherche web, et filtrage strict aux domaines officiels ou non
#  - tier, temperature, reasoning_effort : le modèle et ses réglages
#  - key : suffixe de la variable d'environnement de surcharge (MISTRAL_MODEL_<KEY>)
AGENTS = [
    {"name": "1_referentiel_officiel", "title": "Référentiel officiel", "prompt": PROMPT_SOURCES,
     "inputs": ["demande"], "web": True, "sources_officielles": True,
     "key": "REFERENTIEL", "tier": "principal", "temperature": 0.1},
    {"name": "2_cadrage", "title": "Cadrage", "prompt": PROMPT_CADRAGE,
     "inputs": ["demande", "1_referentiel_officiel"], "web": False,
     "key": "CADRAGE", "tier": "principal", "temperature": 0.2},
    {"name": "3_deroule", "title": "Déroulé de séance", "prompt": PROMPT_CONCEPTION,
     "inputs": ["demande", "2_cadrage"], "web": False,
     "key": "DEROULE", "tier": "principal", "temperature": 0.5},
    {"name": "4_support_cours", "title": "Support de cours", "prompt": PROMPT_REDACTION,
     "inputs": ["2_cadrage", "3_deroule"], "web": False,
     "key": "SUPPORT", "tier": "principal", "temperature": 0.4},
    {"name": "5_documents_eleves", "title": "Documents élèves", "prompt": PROMPT_DOCUMENTS,
     "inputs": ["2_cadrage", "3_deroule", "4_support_cours"], "web": True, "sources_officielles": False,
     "key": "DOCUMENTS", "tier": "principal", "temperature": 0.5},
    {"name": "6_evaluation", "title": "Évaluation", "prompt": PROMPT_EVALUATION,
     "inputs": ["2_cadrage", "4_support_cours"], "web": False,
     "key": "EVALUATION", "tier": "leger", "temperature": 0.3},
]
# Le relecteur tourne sur un modèle différent des rédacteurs (limite l'auto-complaisance), en mode raisonnement.
RELECTEUR = {"name": "relecteur", "title": "Relecteur", "prompt": PROMPT_RELECTEUR,
             "key": "RELECTEUR", "tier": "leger", "temperature": 0, "reasoning_effort": "high"}
AGENTS_BY_NAME = {a["name"]: a for a in AGENTS}
VERIFICATIONS = {
    "duree_totale_respectee": "Durée totale respectée",
    "documents_coherents": "Documents cohérents entre déroulé et dossier élève",
    "objectifs_tous_evalues": "Tous les objectifs sont évalués",
    "programme_repris": "Programme officiel repris",
    "parties_separees": "Parties élève / professeur séparées",
}
TITRES = {"demande": "Demande du prof", **{a["name"]: a["title"] for a in AGENTS}}
CRITERES = {
    "c1_ancrage_programme": "Ancrage au programme officiel",
    "c2_deroule": "Clarté et réalisme du déroulé",
    "c3_niveau_langage": "Niveau de langage",
    "c4_coherence": "Cohérence d'ensemble",
    "c5_exactitude": "Exactitude factuelle",
}


# --------------------------------------------------------------------------- utilitaires SDK

def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def chunk_text(chunk):
    """Texte d'un chunk de contenu (str, dict ou modèle pydantic). Ignore thinking, références, etc."""
    if isinstance(chunk, str):
        return chunk
    if _get(chunk, "type") == "text":
        texte = _get(chunk, "text")
        return texte if isinstance(texte, str) else None
    return None


def content_to_text(content):
    """Normalise un `message.content` (str, liste de chunks ou None) en texte brut."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(t for t in (chunk_text(c) for c in content) if t)
    return chunk_text(content) or str(content)


def is_official_url(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in DOMAINES_OFFICIELS)


URL_RE = re.compile(r"https?://[^\s)\]>\"'«»]+")


def find_urls(text):
    return [u.rstrip(".,;:") for u in URL_RE.findall(text or "")]


# --------------------------------------------------------------------------- appels agents

def build_input(outputs, agent, corrections=None):
    parts = []
    for key in agent["inputs"]:
        parts.append(f"## {TITRES[key]}\n\n{outputs.get(key, '').strip()}")
    if corrections:
        consignes = "\n".join(f"- {c}" for c in corrections)
        parts.append(
            "## CORRECTIONS DEMANDÉES PAR LE RELECTEUR\n\n"
            "Ta production précédente a été jugée insuffisante. Produis une nouvelle version "
            f"complète qui applique ces consignes :\n{consignes}"
        )
        if agent["name"] in outputs:
            parts.append(f"## Ta production précédente\n\n{outputs[agent['name']].strip()}")
    return "\n\n---\n\n".join(parts)


# --------------------------------------------------------------------------- choix des modèles

class Routeur:
    """Mémorise les modèles remplacés par le modèle de secours et le modèle réellement utilisé par agent."""

    def __init__(self):
        self.substitutions = {}
        self.utilises = {}

    def reset(self):
        self.substitutions.clear()
        self.utilises.clear()


ROUTEUR = Routeur()


def model_for(cfg):
    """Modèle configuré : MISTRAL_MODEL_<KEY> si défini, sinon le modèle du niveau (principal / leger)."""
    return os.environ.get(f"MISTRAL_MODEL_{cfg['key']}") or MODELES[cfg["tier"]]


def _error_body(exc):
    return str(getattr(exc, "body", "") or exc).lower()


def _is_model_error(exc):
    status = getattr(exc, "status_code", None)
    return status == 404 or (status in (400, 422) and "model" in _error_body(exc))


def _is_reasoning_error(exc):
    return getattr(exc, "status_code", None) in (400, 422) and "reasoning" in _error_body(exc)


def call_with_fallback(cfg, request):
    """Exécute `request(model, reasoning_effort)` en gérant :
    - un modèle refusé par l'API → bascule sur le modèle de secours (mémorisé pour la suite) ;
    - un `reasoning_effort` non supporté par le modèle → nouvel essai sans raisonnement.
    """
    model = model_for(cfg)
    model = ROUTEUR.substitutions.get(model, model)
    reasoning = cfg.get("reasoning_effort")
    while True:
        try:
            result = request(model, reasoning)
        except MistralError as exc:
            if reasoning and _is_reasoning_error(exc):
                print(f"  ({model} n'accepte pas reasoning_effort={reasoning} : nouvel essai sans raisonnement)")
                reasoning = None
                continue
            secours = MODELES["secours"]
            if _is_model_error(exc) and model != secours:
                print(f"  (modèle {model} refusé par l'API [{exc.status_code}] : bascule sur {secours})")
                ROUTEUR.substitutions[model] = secours
                model = secours
                continue
            raise
        ROUTEUR.utilises[cfg["name"]] = model + (f" (raisonnement : {reasoning})" if reasoning else "")
        return result


def call_agent(client, cfg, user_content, response_format=None):
    if not isinstance(user_content, str):
        user_content = content_to_text(user_content)
    messages = [
        {"role": "system", "content": cfg["prompt"]},
        {"role": "user", "content": user_content},
    ]

    def request(model, reasoning):
        kwargs = {"model": model, "messages": messages, "temperature": cfg["temperature"]}
        if response_format:
            kwargs["response_format"] = response_format
        if reasoning:
            kwargs["reasoning_effort"] = reasoning
        return client.chat.complete(**kwargs)

    response = call_with_fallback(cfg, request)
    return content_to_text(response.choices[0].message.content)


def collect_conversation_output(response):
    """Retourne (texte, références) d'une réponse conversations.start."""
    textes, refs = [], []
    for entry in _get(response, "outputs", []) or []:
        if _get(entry, "type") != "message.output":
            continue
        content = _get(entry, "content", [])
        if isinstance(content, str):
            textes.append(content)
            continue
        for chunk in content or []:
            if _get(chunk, "type") == "tool_reference":
                url = _get(chunk, "url")
                if isinstance(url, str) and url:
                    refs.append({"title": _get(chunk, "title") or url, "url": url})
                continue
            texte = chunk_text(chunk)
            if texte:
                textes.append(texte)
    return "".join(textes), refs


def format_sources(texte, refs, officielles_seulement=True):
    """Ajoute à la production la liste des sources consultées.

    officielles_seulement=True : seules les sources eduscol / education.gouv sont retenues, les autres sont
    signalées comme écartées. Sinon : toutes les sources consultées sont listées, et les URL citées dans le
    texte qui ne proviennent pas de la recherche sont signalées comme non vérifiées.
    """
    if not officielles_seulement:
        uniques = list({r["url"]: r for r in refs}.values())
        consultees = {r["url"] for r in uniques}
        lignes = ["## Sources consultées (recherche web)"]
        lignes += [f"- {r['title']} : {r['url']}" for r in uniques] or ["- Aucune source trouvée par la recherche web."]
        blocs = [texte.strip(), "\n".join(lignes)]
        non_verifiees = sorted({u for u in find_urls(texte) if u not in consultees})
        if non_verifiees:
            blocs.append("\n".join(["## URL citées non issues de la recherche (à vérifier)"]
                                   + [f"- {u}" for u in non_verifiees]))
        return "\n\n".join(blocs)

    officielles, ecartees, vues = [], [], set()
    for ref in refs:
        if ref["url"] in vues:
            continue
        vues.add(ref["url"])
        (officielles if is_official_url(ref["url"]) else ecartees).append(ref)
    citees_hors = sorted({u for u in find_urls(texte) if not is_official_url(u)})

    blocs = [texte.strip()]
    lignes = ["## Sources officielles consultées"]
    if officielles:
        lignes += [f"- {r['title']} : {r['url']}" for r in officielles]
    else:
        lignes.append("- SOURCE OFFICIELLE NON TROUVÉE par la recherche web : vérifier manuellement le programme.")
    blocs.append("\n".join(lignes))
    if ecartees or citees_hors:
        lignes = ["## Sources non officielles (écartées, à ne pas utiliser comme référence)"]
        lignes += [f"- {r['title']} : {r['url']}" for r in ecartees]
        lignes += [f"- URL citée dans la fiche : {u}" for u in citees_hors if u not in vues]
        blocs.append("\n".join(lignes))
    return "\n\n".join(blocs)


def call_web_agent(client, cfg, user_content):
    def request(model, reasoning):
        completion_args = {"temperature": cfg["temperature"]}
        if reasoning:
            completion_args["reasoning_effort"] = reasoning
        agent = client.beta.agents.create(
            model=model,
            name=f"vibeprof-{cfg['name']}",
            instructions=cfg["prompt"],
            tools=[{"type": "web_search"}],
            completion_args=completion_args,
        )
        try:
            return client.beta.conversations.start(agent_id=agent.id, inputs=user_content)
        finally:
            try:
                client.beta.agents.delete(agent_id=agent.id)
            except Exception as exc:  # le nettoyage ne doit pas faire échouer le cours
                print(f"  (avertissement : suppression de l'agent {agent.id} impossible : {exc})")

    response = call_with_fallback(cfg, request)
    texte, refs = collect_conversation_output(response)
    return format_sources(texte, refs, officielles_seulement=cfg.get("sources_officielles", True))


def run_agent(client, agent, outputs, corrections=None):
    user_content = build_input(outputs, agent, corrections)
    if agent["web"]:
        return call_web_agent(client, agent, user_content)
    return call_agent(client, agent, user_content)


def dependents(name):
    """Agents à régénérer (dans l'ordre) quand `name` change : dépendances directes et transitives."""
    touches, result = {name}, []
    for agent in AGENTS:
        if agent["name"] != name and touches.intersection(agent["inputs"]):
            touches.add(agent["name"])
            result.append(agent)
    return result


# --------------------------------------------------------------------------- pipeline

def run_pipeline(client, demande, checkpoint=None):
    outputs = {"demande": demande}
    total = len(AGENTS)
    for i, agent in enumerate(AGENTS, 1):
        print(f"[{i}/{total}] {agent['title']}...")
        outputs[agent["name"]] = run_agent(client, agent, outputs)
        if checkpoint:
            checkpoint(outputs)
    return outputs


def to_float(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def extract_json(text):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Aucun JSON trouvé dans la réponse du relecteur")
    return json.loads(match.group(0))


def _agent_index(ref):
    """Index (0-based) d'un agent désigné par 3, "3", "agent 3"… ; None si invalide."""
    match = re.search(r"(\d+)", str(ref if ref is not None else ""))
    if not match:
        return None
    index = int(match.group(1)) - 1
    return index if 0 <= index < len(AGENTS) else None


def _as_list(value):
    if not value:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def normalize_rapport(rapport):
    if not isinstance(rapport, dict):
        raise ValueError("La réponse du relecteur n'est pas un objet JSON")
    notes = rapport.get("notes") if isinstance(rapport.get("notes"), dict) else {}
    valeurs = [v for v in (to_float(n) for n in notes.values()) if v is not None]
    score = to_float(rapport.get("score_global"))
    if valeurs:  # on recalcule la moyenne plutôt que de faire confiance au calcul du modèle
        score = round(sum(valeurs) / len(valeurs), 2)

    # Corrections : format actuel {"corrections": [{"agent": N, "consignes": [...]}]},
    # ou ancien format {"retour_vers": "agent N", "consignes_correction": [...]}.
    brutes = rapport.get("corrections")
    if not isinstance(brutes, list):
        retour = rapport.get("retour_vers")
        brutes = [{"agent": retour, "consignes": rapport.get("consignes_correction")}] if retour else []
    par_agent = {}
    for item in brutes:
        if not isinstance(item, dict):
            continue
        index = _agent_index(item.get("agent"))
        if index is not None:
            par_agent.setdefault(index, []).extend(_as_list(item.get("consignes")))
    corrections = [{"agent": i + 1, "consignes": par_agent[i]} for i in sorted(par_agent)]

    verifs = rapport.get("verifications") if isinstance(rapport.get("verifications"), dict) else {}
    return {
        "score_global": score,
        "notes": notes,
        "verifications": verifs,
        "livraison": "oui" if score is not None and score >= SEUIL_LIVRAISON else "non",
        "livraison_relecteur": rapport.get("livraison"),
        "corrections": corrections,
    }


def run_relecture(client, outputs, tentatives=2):
    dossier = "\n\n---\n\n".join(f"## {TITRES[k]}\n\n{outputs[k]}" for k in ["demande"] + [a["name"] for a in AGENTS])
    derniere_erreur, raw = None, ""
    for _ in range(tentatives):
        raw = call_agent(client, RELECTEUR, dossier,
                         response_format={"type": "json_object"})
        try:
            return normalize_rapport(extract_json(raw)), raw
        except (ValueError, json.JSONDecodeError) as exc:
            derniere_erreur = exc
    raise ValueError(f"Rapport du relecteur illisible ({derniere_erreur}). Réponse brute : {raw[:500]}")


def apply_correction(client, outputs, rapport, checkpoint=None):
    """Refait les agents désignés par le relecteur (avec leurs consignes) puis tous ceux qui en dépendent,
    dans l'ordre du pipeline, chacun une seule fois."""
    consignes = {AGENTS[c["agent"] - 1]["name"]: c["consignes"] for c in rapport.get("corrections") or []}
    if not consignes:
        return outputs, False
    a_refaire = set(consignes)
    for name in consignes:
        a_refaire.update(a["name"] for a in dependents(name))
    for agent in AGENTS:
        if agent["name"] not in a_refaire:
            continue
        corrections = consignes.get(agent["name"])
        print(f"  {'correction' if corrections else 'mise à jour'} : {agent['title']}...")
        outputs[agent["name"]] = run_agent(client, agent, outputs, corrections)
        if checkpoint:
            checkpoint(outputs)
    return outputs, True


# --------------------------------------------------------------------------- export .docx

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|`[^`]+`)")


def add_inline(paragraph, text):
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**")) or (part.startswith("__") and part.endswith("__")):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            paragraph.add_run(part[1:-1]).font.name = "Courier New"
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)
    return paragraph


def _table_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def add_table(doc, lines):
    rows = [_table_cells(l) for l in lines if not re.fullmatch(r"\|?[\s:\-|]+\|?", l.strip())]
    if not rows:
        return
    width = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=width)
    table.style = "Table Grid"
    for i, row in enumerate(rows):
        for j in range(width):
            cell = table.cell(i, j)
            cell.text = ""
            run_par = cell.paragraphs[0]
            add_inline(run_par, row[j] if j < len(row) else "")
            if i == 0:
                for run in run_par.runs:
                    run.bold = True


def add_markdown(doc, text, base_level=1):
    lines = (text or "").replace("\r\n", "\n").split("\n")
    i, paragraph_buf = 0, []

    def flush():
        if paragraph_buf:
            add_inline(doc.add_paragraph(), " ".join(s.strip() for s in paragraph_buf))
            paragraph_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            p = doc.add_paragraph()
            run = p.add_run("\n".join(code))
            run.font.name = "Courier New"
            run.font.size = Pt(9)
        elif not stripped or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush()
        elif m := re.match(r"^(#{1,6})\s+(.*)$", stripped):
            flush()
            level = max(1, min(base_level + len(m.group(1)), 9))
            doc.add_heading(m.group(2).strip("# ").replace("**", ""), level=level)
        elif stripped.startswith("|"):
            flush()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            add_table(doc, table_lines)
            continue
        elif m := re.match(r"^(\s*)[-*+•]\s+(.*)$", line):
            flush()
            style = "List Bullet 2" if len(m.group(1).replace("\t", "  ")) >= 2 else "List Bullet"
            add_inline(doc.add_paragraph(style=style), m.group(2))
        elif m := re.match(r"^(\s*)\d+[.)]\s+(.*)$", line):
            flush()
            style = "List Number 2" if len(m.group(1).replace("\t", "  ")) >= 2 else "List Number"
            add_inline(doc.add_paragraph(style=style), m.group(2))
        elif stripped.startswith(">"):
            flush()
            p = add_inline(doc.add_paragraph(), stripped.lstrip("> "))
            for run in p.runs:
                run.italic = True
        else:
            paragraph_buf.append(stripped)
        i += 1
    flush()


PARTIE_RE = re.compile(r"^#{1,3}\s*\**\s*partie\s+(él[eè]ve|eleve|professeur|prof|enseignant)\b.*$",
                       re.IGNORECASE | re.MULTILINE)


def split_parties(text):
    """Sépare une production en (partie élève, partie professeur) d'après les titres « ## Partie élève » /
    « ## Partie professeur ». Retourne (None, texte) si la production n'est pas séparée : par prudence, tout va
    alors au professeur (pour ne jamais distribuer un corrigé aux élèves)."""
    text = text or ""
    marques = list(PARTIE_RE.finditer(text))
    if not marques:
        return None, text
    eleve, prof = [], [text[:marques[0].start()].strip()]
    for i, m in enumerate(marques):
        fin = marques[i + 1].start() if i + 1 < len(marques) else len(text)
        bloc = text[m.end():fin].strip()
        (eleve if m.group(1).lower().startswith(("é", "e")) else prof).append(bloc)
    eleve_txt = "\n\n".join(b for b in eleve if b)
    return (eleve_txt or None), "\n\n".join(b for b in prof if b)


def session_title(outputs, demande):
    """Titre de la séance : premier titre « # … » du support de cours, sinon la demande."""
    m = re.search(r"^#\s+(.+)$", outputs.get("4_support_cours", ""), re.MULTILINE)
    titre = m.group(1).strip().replace("**", "") if m else ""
    if not titre or titre.lower().startswith("titre de la séance"):
        titre = demande
    return titre


def _warning(doc, livre, rapports):
    if livre:
        return
    run = doc.add_paragraph().add_run(
        f"⚠ ATTENTION : le seuil de livraison ({SEUIL_LIVRAISON}/5) n'a pas été atteint après "
        f"{len(rapports)} relecture(s). Relisez attentivement ce cours avant de l'utiliser."
    )
    run.bold = True
    run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)


def _teacher_header(doc, titre, demande, livre, rapports):
    doc.add_heading(titre, level=0)
    p = doc.add_paragraph()
    p.add_run("Demande : ").bold = True
    p.add_run(demande)
    _warning(doc, livre, rapports)


def _student_header(doc, titre, sous_titre):
    doc.add_heading(titre, level=0)
    doc.add_paragraph(sous_titre).runs[0].italic = True
    doc.add_paragraph("Nom : ______________________    Prénom : ______________________\n"
                      "Classe : ____________    Date : ____________")


def _add_rapports_et_modeles(doc, rapports):
    doc.add_heading("Rapports de relecture", level=1)
    for i, r in enumerate(rapports, 1):
        doc.add_heading(f"Itération {i} — score {r.get('score_global')}/5, livraison : {r.get('livraison')}", level=2)
        notes = r.get("notes") or {}
        if notes:
            table = doc.add_table(rows=1, cols=2)
            table.style = "Table Grid"
            table.cell(0, 0).text, table.cell(0, 1).text = "Critère", "Note /5"
            for key, val in notes.items():
                cells = table.add_row().cells
                cells[0].text, cells[1].text = CRITERES.get(key, key), str(val)
        verifs = r.get("verifications") or {}
        if verifs:
            doc.add_paragraph("Vérifications :")
            for key, ok in verifs.items():
                doc.add_paragraph(f"{'✔' if ok is True else '✘'} {VERIFICATIONS.get(key, key)}", style="List Bullet")
        for corr in r.get("corrections") or []:
            doc.add_paragraph(f"Renvoi vers l'agent {corr['agent']} ({AGENTS[corr['agent'] - 1]['title']}) :")
            for c in corr["consignes"]:
                add_inline(doc.add_paragraph(style="List Bullet 2"), c)

    if ROUTEUR.utilises:
        doc.add_heading("Modèles utilisés", level=1)
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        table.cell(0, 0).text, table.cell(0, 1).text = "Agent", "Modèle"
        for cfg in AGENTS + [RELECTEUR]:
            if cfg["name"] in ROUTEUR.utilises:
                cells = table.add_row().cells
                cells[0].text, cells[1].text = cfg["title"], ROUTEUR.utilises[cfg["name"]]


def add_section(doc, text, parent_level):
    """Ajoute du markdown en calant son titre de plus haut niveau juste sous `parent_level`."""
    niveaux = [len(m.group(1)) for m in re.finditer(r"^\s*(#{1,6})\s", text or "", re.MULTILINE)]
    add_markdown(doc, text, base_level=parent_level + 1 - min(niveaux) if niveaux else parent_level)


def build_docx(path, demande, outputs, rapports, livre):
    """Dossier complet : toutes les productions, rapports et modèles (archive / consultation)."""
    doc = Document()
    _teacher_header(doc, "Cours généré — dossier complet", demande, livre, rapports)
    for agent in AGENTS:
        doc.add_heading(agent["title"], level=1)
        add_section(doc, outputs.get(agent["name"], ""), parent_level=1)
    _add_rapports_et_modeles(doc, rapports)
    doc.save(path)


def build_fiche_professeur(path, demande, outputs, rapports, livre):
    """Fiche de préparation : programme, cadrage, déroulé, corrigés, contrôle qualité."""
    doc = Document()
    _teacher_header(doc, f"Fiche professeur — {session_title(outputs, demande)}", demande, livre, rapports)
    for name in ("1_referentiel_officiel", "2_cadrage", "3_deroule"):
        doc.add_heading(TITRES[name], level=1)
        add_section(doc, outputs.get(name, ""), parent_level=1)
    for name, titre in (("5_documents_eleves", "Documents élèves — partie professeur"),
                        ("6_evaluation", "Évaluation — partie professeur")):
        eleve, prof = split_parties(outputs.get(name, ""))
        doc.add_heading(titre, level=1)
        if eleve is None:
            doc.add_paragraph("La production n'a pas séparé partie élève et partie professeur : "
                              "elle figure en entier ici et n'a pas été mise dans le document élève.").runs[0].italic = True
        add_section(doc, prof, parent_level=1)
    _add_rapports_et_modeles(doc, rapports)
    doc.save(path)


def build_document_eleve(path, titre, sous_titre, contenu):
    doc = Document()
    _student_header(doc, titre, sous_titre)
    if contenu:
        add_section(doc, contenu, parent_level=0)
    else:
        doc.add_paragraph("Contenu indisponible : voir la fiche professeur.").runs[0].italic = True
    doc.save(path)


def build_deliverables(outdir, demande, outputs, rapports, livre):
    """Écrit les documents livrés et retourne leur liste (chemins)."""
    outdir = Path(outdir)
    titre = session_title(outputs, demande)
    support = re.sub(r"^#\s+.+\n?", "", outputs.get("4_support_cours", "").strip(), count=1)
    docs_eleve, _ = split_parties(outputs.get("5_documents_eleves", ""))
    eval_eleve, _ = split_parties(outputs.get("6_evaluation", ""))
    fichiers = {
        "1_fiche_professeur.docx": lambda p: build_fiche_professeur(p, demande, outputs, rapports, livre),
        "2_cours_eleve.docx": lambda p: build_document_eleve(p, titre, "Cours", support),
        "3_documents_eleves.docx": lambda p: build_document_eleve(p, titre, "Documents et activités", docs_eleve),
        "4_evaluation_eleve.docx": lambda p: build_document_eleve(p, titre, "Évaluation", eval_eleve),
        "cours_complet.docx": lambda p: build_docx(p, demande, outputs, rapports, livre),
    }
    chemins = []
    for nom, build in fichiers.items():
        build(outdir / nom)
        chemins.append(outdir / nom)
    return chemins


# --------------------------------------------------------------------------- main

def make_client(api_key):
    retry = RetryConfig(
        "backoff",
        BackoffStrategy(initial_interval=2000, max_interval=60000, exponent=2, max_elapsed_time=300000),
        retry_connection_errors=True,
    )
    return Mistral(api_key=api_key, retry_config=retry, timeout_ms=300000)


def main():
    parser = argparse.ArgumentParser(description="Workflow agentique de création de cours (Mistral)")
    parser.add_argument("demande", help="Demande du prof, ex: 'Terminale bac pro Commerce, thème: la mondialisation, 2h, TD'")
    parser.add_argument("--outdir", default="output")
    parser.add_argument("--model", default=MODELES["principal"],
                        help=f"Modèle principal (défaut : {MODELES['principal']}, ou $MISTRAL_MODEL)")
    parser.add_argument("--model-leger", default=MODELES["leger"],
                        help=f"Modèle léger : évaluation et relecture (défaut : {MODELES['leger']}, ou $MISTRAL_MODEL_LEGER)")
    parser.add_argument("--model-secours", default=MODELES["secours"],
                        help=f"Modèle de secours si un modèle est refusé (défaut : {MODELES['secours']}, ou $MISTRAL_MODEL_SECOURS)")
    parser.add_argument("--max-relectures", type=int, default=MAX_RELECTURES)
    args = parser.parse_args()
    MODELES.update(principal=args.model, leger=args.model_leger, secours=args.model_secours)
    ROUTEUR.reset()

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("Erreur : variable d'environnement MISTRAL_API_KEY manquante.")

    client = make_client(api_key)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    rapports = []

    def save(outputs, statut="en_cours", livre=False):
        final = {
            "demande": args.demande,
            "modeles_configures": dict(MODELES),
            "modeles_utilises": dict(ROUTEUR.utilises),
            "substitutions": dict(ROUTEUR.substitutions),
            "statut": statut,
            "livre": livre,
            "dossier": outputs,
            "rapports_relecture": rapports,
            "iterations": len(rapports),
        }
        (outdir / "cours_final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Lancement de la chaîne d'agents...")
    try:
        outputs = run_pipeline(client, args.demande, checkpoint=save)
    except Exception as exc:
        sys.exit(f"Erreur pendant la génération : {exc}\nProductions partielles : {outdir}/cours_final.json")

    livre = False
    statut = "termine"
    for iteration in range(1, args.max_relectures + 1):
        print(f"[relecture {iteration}/{args.max_relectures}] Évaluation par le relecteur...")
        try:
            rapport, _ = run_relecture(client, outputs)
        except Exception as exc:
            print(f"  relecture impossible : {exc}")
            statut = "relecture_en_erreur"
            break
        rapports.append(rapport)
        save(outputs)
        print(f"  score = {rapport['score_global']}/5, livraison = {rapport['livraison']}")
        if rapport["livraison"] == "oui":
            livre = True
            break
        if iteration < args.max_relectures:
            cibles = ", ".join(f"agent {c['agent']}" for c in rapport["corrections"]) or "aucun agent"
            print(f"  renvoi vers : {cibles}")
            try:
                outputs, corrected = apply_correction(client, outputs, rapport, checkpoint=save)
            except Exception as exc:
                print(f"  correction impossible : {exc}")
                statut = "correction_en_erreur"
                break
            if not corrected:
                print("  aucun agent valide désigné pour la correction, arrêt des relectures.")
                break

    save(outputs, statut=statut, livre=livre)
    fichiers = build_deliverables(outdir, args.demande, outputs, rapports, livre)

    if not livre:
        print(f"⚠ Seuil de {SEUIL_LIVRAISON}/5 non atteint : cours à relire attentivement.")
    print(f"Terminé en {len(rapports)} relecture(s). Documents dans {outdir}/ :")
    for f in fichiers:
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
