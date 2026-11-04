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

PROMPT_SOURCES = """Tu es un agent de recherche documentaire pour un enseignant d'histoire-géographie en lycée professionnel. Ta mission : récupérer les sources officielles du programme concerné.

Règles strictes :
- Utilise la recherche web. Ne retiens QUE les contenus issus des sites officiels : eduscol.education.fr et education.gouv.fr (leurs sous-domaines inclus).
- Pour chaque information retenue, cite l'URL exacte de la source.
- Extrais : le référentiel du niveau demandé, les compétences et savoirs associés au thème, et les documents d'accompagnement officiels si disponibles.
- Si aucune source officielle n'est trouvée pour un point, écris explicitement « SOURCE OFFICIELLE NON TROUVÉE » — n'invente jamais de contenu de programme.

Entrée attendue : la demande du prof (niveau, spécialité, thème, durée, format).
Sortie : une fiche structurée « Référentiel officiel » avec sections : programme applicable, objectifs officiels, compétences travaillées, documents officiels (avec URL), et liste des points sans source trouvée."""

PROMPT_CADRAGE = """Tu es un agent de cadrage pédagogique. À partir de la demande du prof et de la fiche « Référentiel officiel » produite par l'agent précédent, tu ancres le sujet dans le programme du bac professionnel.

Entrée attendue : la demande du prof + la fiche « Référentiel officiel ».
Sortie : une fiche « Cadrage » contenant :
- le chapitre exact du référentiel et sa place dans la progression annuelle
- 2 à 4 objectifs d'apprentissage formulés pour des élèves de lycée pro (verbes d'action concrets)
- les compétences du socle et du référentiel mobilisées
- les prérequis nécessaires et les points de vigilance connus
- une durée réaliste allouée à chaque partie de la séance, cohérente avec la durée demandée par le prof"""

PROMPT_CONCEPTION = """Tu es un concepteur de séances d'histoire-géographie pour le lycée professionnel. Tu conçois le déroulé pédagogique à partir du cadrage fourni.

Règles :
- Privilégie les méthodes actives adaptées au lycée pro : manipulation de documents, travail en groupe, mise en situation, supports visuels.
- Prévois des transitions explicites et des moments de synthèse orale.
- Adapte le niveau de langage : phrases courtes, vocabulaire explicité, exemples concrets tirés du vécu des élèves.
- Respecte la durée totale et le format demandés par le prof.

Entrée attendue : la demande du prof + la fiche « Cadrage ».
Sortie : un déroulé de séance minute par minute (ex: 5 min accroche, 15 min doc 1...) avec pour chaque étape : objectif, consigne exacte donnée aux élèves, support utilisé, et ce que fait le prof."""

PROMPT_REDACTION = """Tu es un rédacteur de supports de cours d'histoire-géographie pour le lycée professionnel.

Entrée attendue : la fiche « Cadrage » + le déroulé de séance.
Sortie : le support de cours complet, rédigé, prêt à être projeté ou distribué :
- titre de la séance
- « Ce que je retiens » (3 à 5 points clés, formulation élève)
- le contenu structuré avec titres et sous-titres
- définitions des mots difficiles
- au moins un schéma ou tableau décrit textuellement (légende comprise)
- une frise ou une carte décrite précisément (éléments à faire figurer)"""

PROMPT_DOCUMENTS = """Tu es un concepteur de documents et d'activités pour des élèves de lycée professionnel.

Règles sur les sources :
- Utilise la recherche web pour trouver de vrais documents (textes historiques, extraits officiels, statistiques, articles) en privilégiant les sites institutionnels, d'archives, de musées et de presse reconnue.
- Tout texte présenté comme authentique (citation, extrait, chiffre) doit être accompagné de son auteur, sa date et l'URL où tu l'as trouvé. Ne cite jamais de mémoire.
- Si tu ne trouves pas de source vérifiable, rédige un texte adapté pour la classe et indique explicitement « Texte rédigé pour la séance (non authentique) ».

Entrée attendue : le cadrage, le déroulé et le support de cours.
Sortie : un dossier « Documents élèves » contenant :
- 1 à 2 textes sources adaptés au niveau (avec provenance et URL, ou mention « non authentique »)
- 1 carte ou schéma à compléter, décrit précisément (titre, éléments à placer, légende attendue)
- 2 à 3 questions de guidage progressives (du plus simple au plus complexe)
- 1 exercice d'application ou de mise en situation
- le corrigé type pour le prof"""

PROMPT_EVALUATION = """Tu es un concepteur d'évaluations pour le lycée professionnel.

Entrée attendue : le cadrage et le support de cours.
Sortie : une fiche « Évaluation » contenant :
- 5 questions QCM ou questions courtes portant sur les points clés de la séance (avec corrigé)
- OU une grille d'auto-évaluation à 4 niveaux (non acquis / en cours / acquis / expert) par compétence travaillée
- les critères de réussite explicites pour le prof"""

PROMPT_RELECTEUR = """Tu es le relecteur critique final d'un workflow de création de cours. Tu évalues la production complète et tu décides si elle peut être livrée.

Les agents du workflow sont :
- agent 1 : référentiel officiel (sources eduscol / education.gouv)
- agent 2 : cadrage
- agent 3 : déroulé de séance
- agent 4 : support de cours
- agent 5 : documents élèves
- agent 6 : évaluation

Grille d'évaluation (note chaque critère sur 5) :
1. Ancrage au programme officiel (sources citées, objectifs conformes)
2. Clarté et réalisme du déroulé temporel (y compris respect de la durée demandée)
3. Niveau de langage adapté au lycée professionnel
4. Cohérence entre objectifs, support, documents et évaluation
5. Absence d'erreurs factuelles et de biais

Pour les critères 1 et 5, appuie-toi sur les listes de sources jointes au référentiel et aux documents élèves : un point de programme sans source officielle, ou une citation présentée comme authentique sans URL dans la liste des sources consultées, doit faire baisser la note.

Règles :
- Score global = moyenne des 5 critères. Seuil de livraison : 4/5.
- Si score < 4/5, liste précisément les défauts et indique À QUEL AGENT renvoyer la production (agent 1 à 6 : choisis l'agent le plus en amont à l'origine du défaut principal) avec les consignes de correction.
- Ne modifie pas toi-même le contenu.

Entrée attendue : la demande du prof et l'ensemble du dossier (référentiel, cadrage, déroulé, support, documents, évaluation).
Sortie : UNIQUEMENT un objet JSON valide, sans texte avant ni après, de la forme :
{
  "score_global": 3.8,
  "notes": {"c1_ancrage_programme": 4, "c2_deroule": 3, "c3_niveau_langage": 4, "c4_coherence": 4, "c5_exactitude": 4},
  "livraison": "oui" ou "non",
  "retour_vers": "agent 3" ou null,
  "consignes_correction": ["..."]
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


def normalize_rapport(rapport):
    if not isinstance(rapport, dict):
        raise ValueError("La réponse du relecteur n'est pas un objet JSON")
    notes = rapport.get("notes") if isinstance(rapport.get("notes"), dict) else {}
    valeurs = [v for v in (to_float(n) for n in notes.values()) if v is not None]
    score = to_float(rapport.get("score_global"))
    if valeurs:  # on recalcule la moyenne plutôt que de faire confiance au calcul du modèle
        score = round(sum(valeurs) / len(valeurs), 2)
    consignes = rapport.get("consignes_correction") or []
    if isinstance(consignes, str):
        consignes = [consignes]
    retour = rapport.get("retour_vers")
    if isinstance(retour, str) and retour.strip().lower() in ("", "null", "none", "aucun"):
        retour = None
    return {
        "score_global": score,
        "notes": notes,
        "livraison": "oui" if score is not None and score >= SEUIL_LIVRAISON else "non",
        "livraison_relecteur": rapport.get("livraison"),
        "retour_vers": retour,
        "consignes_correction": [str(c) for c in consignes],
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


def target_agent(rapport):
    match = re.search(r"(\d+)", str(rapport.get("retour_vers") or ""))
    if not match:
        return None
    index = int(match.group(1)) - 1
    return AGENTS[index] if 0 <= index < len(AGENTS) else None


def apply_correction(client, outputs, rapport, checkpoint=None):
    agent = target_agent(rapport)
    if agent is None:
        return outputs, False
    print(f"  correction : {agent['title']}...")
    outputs[agent["name"]] = run_agent(client, agent, outputs, rapport.get("consignes_correction"))
    if checkpoint:
        checkpoint(outputs)
    for suivant in dependents(agent["name"]):
        print(f"  mise à jour : {suivant['title']}...")
        outputs[suivant["name"]] = run_agent(client, suivant, outputs)
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
            level = min(base_level + len(m.group(1)), 9)
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


def build_docx(path, demande, outputs, rapports, livre):
    doc = Document()
    doc.add_heading("Cours généré", level=0)
    p = doc.add_paragraph()
    p.add_run("Demande : ").bold = True
    p.add_run(demande)

    if not livre:
        avert = doc.add_paragraph()
        run = avert.add_run(
            f"⚠ ATTENTION : le seuil de livraison ({SEUIL_LIVRAISON}/5) n'a pas été atteint après "
            f"{len(rapports)} relecture(s). Relisez attentivement ce cours avant de l'utiliser."
        )
        run.bold = True
        run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)

    for agent in AGENTS:
        doc.add_heading(agent["title"], level=1)
        add_markdown(doc, outputs.get(agent["name"], ""), base_level=1)

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
        if r.get("retour_vers"):
            doc.add_paragraph(f"Renvoi vers : {r['retour_vers']}")
        for c in r.get("consignes_correction") or []:
            add_inline(doc.add_paragraph(style="List Bullet"), c)

    if ROUTEUR.utilises:
        doc.add_heading("Modèles utilisés", level=1)
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        table.cell(0, 0).text, table.cell(0, 1).text = "Agent", "Modèle"
        for cfg in AGENTS + [RELECTEUR]:
            if cfg["name"] in ROUTEUR.utilises:
                cells = table.add_row().cells
                cells[0].text, cells[1].text = cfg["title"], ROUTEUR.utilises[cfg["name"]]
    doc.save(path)


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
            print(f"  retour vers {rapport.get('retour_vers')} avec consignes de correction...")
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
    build_docx(outdir / "cours_final.docx", args.demande, outputs, rapports, livre)

    if not livre:
        print(f"⚠ Seuil de {SEUIL_LIVRAISON}/5 non atteint : cours à relire attentivement.")
    print(f"Terminé en {len(rapports)} relecture(s). Résultat : {outdir}/cours_final.docx")


if __name__ == "__main__":
    main()
