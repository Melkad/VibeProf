import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from mistralai.client import Mistral

MODEL = os.environ.get("MISTRAL_MODEL", "mistral-large-latest")
MAX_RELECTURES = 3
SEUIL_LIVRAISON = 4.0

PROMPT_SOURCES = """Tu es un agent de recherche documentaire pour un enseignant d'histoire-géographie en lycée professionnel. Ta mission : récupérer les sources officielles du programme concerné.

Règles strictes :
- Utilise la recherche web. Ne retiens QUE les contenus issus des sites officiels : eduscol.education.fr et education.gouv.fr (leurs sous-domaines inclus).
- Pour chaque information retenue, cite l'URL exacte de la source.
- Extrais : le référentiel du niveau demandé, les compétences et savoirs associés au thème, et les documents d'accompagnement officiels si disponibles.
- Si aucune source officielle n'est trouvée pour un point, écris explicitement « SOURCE OFFICIELLE NON TROUVÉE » — n'invente jamais de contenu de programme.

Entrée attendue : la demande du prof (niveau, spécialité, thème, durée, format).
Sortie : une fiche structurée « Référentiel officiel » avec sections : programme applicable, objectifs officiels, compétences travaillées, documents officiels (avec URL), et liste des points sans source trouvée."""

PROMPT_CADRAGE = """Tu es un agent de cadrage pédagogique. À partir de la fiche « Référentiel officiel » produite par l'agent précédent, tu ancre le sujet dans le programme du bac professionnel.

Entrée attendue : la fiche « Référentiel officiel ».
Sortie : une fiche « Cadrage » contenant :
- le chapitre exact du référentiel et sa place dans la progression annuelle
- 2 à 4 objectifs d'apprentissage formulés pour des élèves de lycée pro (verbes d'action concrets)
- les compétences du socle et du référentiel mobilisées
- les prérequis nécessaires et les points de vigilance connus
- une durée réaliste allouée à chaque partie de la séance"""

PROMPT_CONCEPTION = """Tu es un concepteur de séances d'histoire-géographie pour le lycée professionnel. Tu conçois le déroulé pédagogique à partir du cadrage fourni.

Règles :
- Privilégie les méthodes actives adaptées au lycée pro : manipulation de documents, travail en groupe, mise en situation, supports visuels.
- Prévois des transitions explicites et des moments de synthèse orale.
- Adapte le niveau de langage : phrases courtes, vocabulaire explicité, exemples concrets tirés du vécu des élèves.

Entrée attendue : la fiche « Cadrage ».
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

Entrée attendue : le cadrage, le déroulé et le support de cours.
Sortie : un dossier « Documents élèves » contenant :
- 1 à 2 textes sources adaptés au niveau (avec indication de provenance ; si tu cites un texte historique, indique la source exacte)
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

Grille d'évaluation (note chaque critère sur 5) :
1. Ancrage au programme officiel (sources citées, objectifs conformes)
2. Clarté et réalisme du déroulé temporel
3. Niveau de langage adapté au lycée professionnel
4. Cohérence entre objectifs, support, documents et évaluation
5. Absence d'erreurs factuelles et de biais

Règles :
- Score global = moyenne des 5 critères. Seuil de livraison : 4/5.
- Si score < 4/5, liste précisément les défauts et indique À QUEL AGENT renvoyer la production (agent 2, 3, 4, 5 ou 6) avec les consignes de correction.
- Ne modifie pas toi-même le contenu.

Entrée attendue : l'ensemble du dossier (cadrage, déroulé, support, documents, évaluation).
Sortie : UNIQUEMENT un bloc JSON valide, sans texte avant ni après :
{
  "score_global": X.X,
  "notes": {"c1_ancrage_programme": X, "c2_deroule": X, "c3_niveau_langage": X, "c4_coherence": X, "c5_exactitude": X},
  "livraison": "oui" ou "non",
  "retour_vers": "agent X" ou "null",
  "consignes_correction": ["..."]
}"""

AGENTS = [
    ("1_referentiel_officiel", PROMPT_SOURCES, True),
    ("2_cadrage", PROMPT_CADRAGE, False),
    ("3_deroule", PROMPT_CONCEPTION, False),
    ("4_support_cours", PROMPT_REDACTION, False),
    ("5_documents_eleves", PROMPT_DOCUMENTS, False),
    ("6_evaluation", PROMPT_EVALUATION, False),
]


def call_agent(client, system_prompt, user_content):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    response = client.chat.complete(model=MODEL, messages=messages, temperature=0.4)
    return response.choices[0].message.content


def call_sources_agent(client, demande):
    agent = client.beta.agents.create(
        model=MODEL,
        name="vibeprof-sources-officielles",
        instructions=PROMPT_SOURCES,
        tools=[{"type": "web_search_premium"}],
    )
    try:
        response = client.agents.complete(
            agent_id=agent.id,
            messages=[{"role": "user", "content": demande}],
        )
        return response.choices[0].message.content
    finally:
        client.beta.agents.delete(agent_id=agent.id)


def extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Aucun JSON trouvé dans la réponse du relecteur")
    return json.loads(match.group(0))


def run_pipeline(client, demande):
    outputs = {}
    current = demande
    for name, prompt, use_web in AGENTS:
        if use_web:
            current = call_sources_agent(client, current)
        else:
            current = call_agent(client, prompt, current)
        outputs[name] = current
    return outputs


def run_relecture(client, outputs):
    dossier = "\n\n---\n\n".join(f"## {k}\n{v}" for k, v in outputs.items())
    rapport_raw = call_agent(client, PROMPT_RELECTEUR, dossier)
    return extract_json(rapport_raw), rapport_raw


def apply_correction(client, outputs, rapport):
    match = re.search(r"agent\s*(\d)", rapport.get("retour_vers") or "", re.IGNORECASE)
    if not match:
        return outputs, False
    index = int(match.group(1)) - 1
    if not (1 <= index < len(AGENTS)):
        return outputs, False
    name, prompt, use_web = AGENTS[index]
    consignes = "\n".join(f"- {c}" for c in rapport.get("consignes_correction", []))
    previous_input = ""
    if index == 0:
        previous_input = outputs.get("demande", "")
    else:
        previous_input = outputs[AGENTS[index - 1][0]]
    corrected = call_agent(client, prompt, f"{previous_input}\n\nCORRECTIONS DEMANDÉES PAR LE RELECTEUR :\n{consignes}")
    outputs[name] = corrected
    for j in range(index + 1, len(AGENTS)):
        n, p, w = AGENTS[j]
        if w:
            outputs[n] = call_sources_agent(client, outputs[AGENTS[j - 1][0]])
        else:
            outputs[n] = call_agent(client, p, outputs[AGENTS[j - 1][0]])
    return outputs, True


def build_docx(path, demande, outputs, rapports):
    doc = Document()
    doc.add_heading("Cours généré", level=0)
    doc.add_paragraph(f"Demande : {demande}")
    for name, content in outputs.items():
        if name == "demande":
            continue
        doc.add_heading(name, level=1)
        for block in re.split(r"\n\s*\n", content.strip()):
            block = block.strip()
            if not block:
                continue
            if block.startswith("### "):
                doc.add_heading(block[4:], level=3)
            elif block.startswith("## "):
                doc.add_heading(block[3:], level=2)
            elif block.startswith("# "):
                doc.add_heading(block[2:], level=1)
            elif block.startswith("- "):
                doc.add_paragraph(block[2:], style="List Bullet")
            else:
                doc.add_paragraph(block)
    doc.add_heading("Rapports de relecture", level=1)
    for i, r in enumerate(rapports, 1):
        doc.add_heading(f"Itération {i} — score {r.get('score_global')}/5, livraison : {r.get('livraison')}", level=2)
        doc.add_paragraph(json.dumps(r, ensure_ascii=False, indent=2))
    doc.save(path)


def main():
    parser = argparse.ArgumentParser(description="Workflow agentique de création de cours (Mistral)")
    parser.add_argument("demande", help="Demande du prof, ex: 'Terminale bac pro Commerce, thème: la mondialisation, 2h, TD'")
    parser.add_argument("--outdir", default="output")
    args = parser.parse_args()

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("Erreur : variable d'environnement MISTRAL_API_KEY manquante.")

    client = Mistral(api_key=api_key)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    print("[1/7] Lancement de la chaîne d'agents...")
    outputs = run_pipeline(client, args.demande)
    outputs["demande"] = args.demande

    rapports = []
    for iteration in range(1, MAX_RELECTURES + 1):
        print(f"[relecture {iteration}/{MAX_RELECTURES}] Évaluation par le relecteur...")
        rapport, raw = run_relecture(client, outputs)
        rapports.append(rapport)
        print(f"  score = {rapport.get('score_global')}/5, livraison = {rapport.get('livraison')}")
        if rapport.get("livraison") == "oui" or float(rapport.get("score_global", 0)) >= SEUIL_LIVRAISON:
            break
        if iteration < MAX_RELECTURES:
            print(f"  retour vers {rapport.get('retour_vers')} avec consignes de correction...")
            outputs, corrected = apply_correction(client, outputs, rapport)
            if not corrected:
                break

    final = {
        "demande": args.demande,
        "dossier": outputs,
        "rapports_relecture": rapports,
        "iterations": len(rapports),
    }
    (outdir / "cours_final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    build_docx(outdir / "cours_final.docx", args.demande, outputs, rapports)

    print(f"Terminé en {len(rapports)} itération(s). Résultat : {outdir}/cours_final.docx")


if __name__ == "__main__":
    main()
