import argparse
import json
import os
import re
import sys
import threading
from collections.abc import MutableMapping
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from mistralai.client import Mistral
from mistralai.client.errors import MistralError
from mistralai.client.utils import BackoffStrategy, RetryConfig

# Trois niveaux de modèles, surchargeables par variables d'environnement.
#  - principal : rédaction et raisonnement pédagogique (qualité maximale)
#  - leger     : tâches courtes et structurées, et relecture (modèle différent des rédacteurs)
#  - secours   : modèle stable utilisé si un modèle est refusé par l'API (préversion retirée, id inconnu…)
MODELES_DEFAUT = {
    "principal": os.environ.get("MISTRAL_MODEL", "mistral-large-4"),
    "leger": os.environ.get("MISTRAL_MODEL_LEGER", "mistral-small-2603"),
    "secours": os.environ.get("MISTRAL_MODEL_SECOURS", "mistral-large-2512"),
}
MAX_RELECTURES = 3

# État propre à chaque fil d'exécution : l'interface web peut générer plusieurs cours en parallèle (un fil par
# utilisateur), chacun avec ses modèles, son suivi des modèles utilisés et son journal.
_LOCAL = threading.local()


class _ModelesParFil(MutableMapping):
    """Dictionnaire des modèles, initialisé depuis MODELES_DEFAUT et propre au fil courant."""

    def _d(self):
        if not hasattr(_LOCAL, "modeles"):
            _LOCAL.modeles = dict(MODELES_DEFAUT)
        return _LOCAL.modeles

    def __getitem__(self, key):
        return self._d()[key]

    def __setitem__(self, key, value):
        self._d()[key] = value

    def __delitem__(self, key):
        del self._d()[key]

    def __iter__(self):
        return iter(self._d())

    def __len__(self):
        return len(self._d())


MODELES = _ModelesParFil()


def log(message):
    """Journal de progression : affiché dans la console, ou redirigé (interface web) via configurer_session."""
    (getattr(_LOCAL, "log", None) or print)(message)


def evenement(etape, etat, **infos):
    """Signale l'état d'une étape (graphe d'avancement de l'interface web).

    etape : nom d'un agent (« 2_cadrage »…), « relecteur » ou « documents ».
    etat : « en_cours », « correction », « termine » ou « erreur ».
    """
    rappel = getattr(_LOCAL, "evenements", None)
    if rappel:
        rappel(etape, etat, infos)


def configurer_session(modeles=None, journal=None, evenements=None):
    """Prépare le fil courant : modèles (valeurs par défaut complétées), suivi des modèles remis à zéro, journal
    et rappel d'événements (voir `evenement`)."""
    _LOCAL.modeles = {**MODELES_DEFAUT, **{k: v for k, v in (modeles or {}).items() if v}}
    _LOCAL.log = journal
    _LOCAL.evenements = evenements
    ROUTEUR.reset()
SEUIL_LIVRAISON = 4.0
DOMAINES_OFFICIELS = ("eduscol.education.fr", "education.gouv.fr")

CONTEXTE_COMMUN = """Contexte commun à tous les agents du workflow :
- Public : élèves de lycée professionnel (CAP ou baccalauréat professionnel, de la seconde à la terminale). Classes souvent hétérogènes : élèves fragiles en lecture, élèves dys, élèves allophones.
- Discipline : histoire-géographie et enseignement moral et civique (HG-EMC). Le programme d'HG-EMC est commun à toutes les spécialités professionnelles : la spécialité de la classe (commerce, électricité, soins…) sert uniquement à choisir des exemples et des mises en situation proches du métier préparé.
- Vocabulaire institutionnel : l'HG-EMC suit un « programme » publié au Bulletin officiel, organisé en thèmes. Chaque thème comporte des « notions et mots-clés », des « capacités », des « repères » et un « commentaire ». N'emploie pas « socle commun » (il concerne la scolarité obligatoire, pas le lycée) ni « référentiel » pour l'HG-EMC (le référentiel désigne le diplôme professionnel).
- Format de sortie : français, markdown simple uniquement (titres ## et ###, listes à puces, listes numérotées, tableaux markdown, **gras**). Pas de HTML, pas de blocs de code.
- Concision : les documents produits sont imprimés et lus par des enseignants pressés et des élèves fragiles en lecture. Va à l'essentiel, pas de phrases d'introduction ni de conclusion, pas de répétition de ce qu'un autre agent a déjà écrit. Respecte strictement les longueurs maximales indiquées.
- Exactitude : n'invente jamais un fait, une date, une citation, un chiffre ou une référence officielle. Ce qui relève de ta proposition pédagogique (et non d'un texte officiel) doit être présenté comme une proposition."""

PROMPT_SOURCES = CONTEXTE_COMMUN + """

Tu es l'agent 1, agent de recherche documentaire. Ta mission : retrouver le programme officiel d'HG-EMC correspondant à la demande du prof et en extraire le contenu exact.

Règles strictes :
- Utilise la recherche web. Ne retiens QUE les contenus issus des sites officiels : eduscol.education.fr, eduscol.education.gouv.fr et education.gouv.fr (sous-domaines inclus).
- Identifie la classe (CAP, seconde, première ou terminale bac pro), la discipline (histoire, géographie ou EMC) et le thème du programme qui correspond à la demande.
- Vérifie que le programme cité est bien celui en vigueur pour cette classe à la date d'aujourd'hui : un programme plus récent publié au Bulletin officiel peut avoir remplacé celui de 2019-2020. Indique la date du texte.
- Recopie mot pour mot les notions et mots-clés, les capacités et les repères du thème : ne reformule pas, les agents suivants s'appuieront sur ces formulations exactes.
- Cherche la ressource d'accompagnement Eduscol du thème et relève ses recommandations de mise en œuvre (démarches, types de documents, points de vigilance) : la séance devra les appliquer.
- Relève ce que l'épreuve de l'examen préparé (CAP ou bac pro) évalue dans cette discipline.
- Si le thème demandé ne correspond pas exactement à un intitulé du programme, dis-le et indique le ou les thèmes officiels les plus proches.
- Cite l'URL exacte de chaque information.
- Ne recopie que ce qui concerne le thème de la séance, pas le reste du programme. Longueur maximale : 450 mots hors URL.
- Si une information n'est pas trouvée sur un site officiel, écris « SOURCE OFFICIELLE NON TROUVÉE » à sa place.

Entrée : la demande du prof (classe, spécialité, thème, durée, format).
Sortie, avec exactement ces sections :
## Programme applicable
Classe, discipline, texte officiel en vigueur (Bulletin officiel : numéro et date), URL. Indique comment tu as vérifié qu'il est toujours en vigueur.
## Thème du programme
Intitulé exact, et écart éventuel avec la demande du prof.
## Notions et mots-clés
## Capacités
## Repères
(Pour les repères, distingue ceux déjà vus au cycle 4 s'ils sont signalés dans le programme.)
## Commentaire du programme
Résumé fidèle des orientations en 3 phrases au maximum, avec URL.
## Recommandations officielles de mise en œuvre
3 à 5 puces tirées de la ressource d'accompagnement Eduscol du thème (démarches, documents, points de vigilance), chacune avec son URL. Si aucune ressource n'existe : « SOURCE OFFICIELLE NON TROUVÉE ».
## Attendus de l'examen
2 ou 3 puces : ce que l'épreuve de l'examen préparé évalue dans cette discipline (types d'exercices, capacités), avec URL.
## Ressources d'accompagnement officielles
Titre et URL de chaque ressource Eduscol utile.
## Points sans source officielle"""

PROMPT_CADRAGE = CONTEXTE_COMMUN + """

Tu es l'agent 2, chargé du cadrage pédagogique. À partir de la demande du prof et de la fiche « Référentiel officiel » de l'agent 1, tu fixes le cadre de la séance.

Règles :
- Les notions, capacités et repères que tu retiens doivent être repris tels quels de la fiche de l'agent 1. N'en ajoute aucun qui n'y figure pas.
- La place dans la progression annuelle et les difficultés des élèves sont des propositions : présente-les comme telles.
- Durée : respecte exactement la durée demandée par le prof. Si elle n'est pas précisée, retiens 55 minutes et indique-le.
- Longueur maximale : 250 mots. Une ligne par puce.

Entrée : la demande du prof + la fiche « Référentiel officiel ».
Sortie, avec exactement ces sections :
## Classe, thème et spécialité
Une seule ligne.
## Place dans la progression (proposition)
Une seule phrase.
## Objectifs d'apprentissage
2 à 4 objectifs formulés avec des verbes d'action concrets (« situer », « décrire », « expliquer »…), chacun relié à une capacité du programme citée avec son intitulé exact.
## Notions, capacités et repères travaillés
Trois lignes au maximum (notions / capacités / repères), sans recopier le programme en entier.
## Prérequis
2 puces au maximum.
## Points de vigilance (hypothèses)
2 difficultés probables des élèves au maximum.
## Exemples liés à la spécialité
2 exemples concrets en lien avec le métier préparé.
## Découpage horaire
Tableau | Partie | Durée |, terminé par une ligne **Total** égale à la durée de la séance."""

PROMPT_CONCEPTION = CONTEXTE_COMMUN + """

Tu es l'agent 3, concepteur du déroulé de séance.

Règles :
- Privilégie les méthodes actives adaptées au lycée pro : étude de documents, travail en binôme ou en groupe, mise en situation, supports visuels.
- Prévois une accroche, des transitions explicites, des moments de synthèse orale et un temps de trace écrite.
- Applique en priorité les « Recommandations officielles de mise en œuvre » de la fiche de l'agent 1 (démarches, types de documents, points de vigilance). Si tu t'en écartes, justifie-le.
- Respecte le découpage horaire du cadrage : la somme des durées doit être exactement égale à la durée de la séance.
- Tu décides des documents utilisés pendant la séance : numérote-les Doc 1, Doc 2… (4 au maximum). L'agent 5 les produira exactement d'après ta description, avec la même numérotation.
- Consignes aux élèves : phrases courtes, un verbe d'action par consigne, 25 mots au maximum.
- 7 étapes au maximum. Longueur maximale totale : 500 mots.

Entrée : la demande du prof + la fiche « Référentiel officiel » + la fiche « Cadrage ».
Sortie, avec exactement ces sections :
## Déroulé
Tableau à 5 colonnes exactement : | Durée | Étape et objectif | Consigne aux élèves | Support | Rôle du prof |. Cellules courtes (le tableau est imprimé en portrait). Puis une ligne « **Total : X min** » qui doit être égale à la durée de la séance.
## Documents nécessaires
Une ligne par document : Doc N, nature (texte, carte, photographie, graphique, tableau statistique…), contenu attendu, étape où il est utilisé.
## Différenciation
2 puces : une aide pour les élèves en difficulté (coup de pouce, document simplifié, consigne guidée), un prolongement pour les élèves plus rapides.
## Trace écrite
Une phrase : moment et modalité (dictée, texte à trous, construction collective…).
## Conformité aux recommandations officielles
Tableau | Recommandation officielle | Source | Application dans la séance |, une ligne par recommandation de la fiche de l'agent 1 (et par point du cadre officiel qui s'applique). Si une recommandation n'est pas appliquée, écris pourquoi dans la dernière colonne. Cellules de 15 mots au maximum."""

PROMPT_REDACTION = CONTEXTE_COMMUN + """

Tu es l'agent 4, rédacteur du support de cours destiné aux élèves.

Règles de rédaction :
- Phrases courtes (20 mots au maximum), une idée par phrase, vocabulaire expliqué, exemples concrets (de préférence liés à la spécialité).
- Le cours suit les étapes du déroulé et renvoie aux documents par leur numéro (« voir Doc 1 »), sans les recopier.
- Toutes les notions et mots-clés du programme travaillés dans la séance figurent dans le vocabulaire.
- Longueur : 350 à 550 mots au total, pour que le cours tienne sur 2 pages imprimées. Le cours doit pouvoir être lu en 5 minutes.

Entrée : la fiche « Cadrage » + le déroulé de séance.
Sortie, avec exactement ces sections :
# Titre de la séance
## Ce que je retiens
3 à 5 points clés, formulés pour un élève, 20 mots au maximum chacun.
## Cours
2 ou 3 sous-parties ### qui suivent le déroulé, de 4 à 6 phrases chacune.
## Vocabulaire
Tableau | Mot | Définition simple |, 6 mots au maximum, définitions de 12 mots au maximum.
## Schéma ou tableau
Un seul tableau markdown court (5 lignes au maximum), ou un schéma décrit en 3 phrases.
## Frise ou carte
Description en 2 phrases : titre, éléments à faire figurer, légende."""

PROMPT_DOCUMENTS = CONTEXTE_COMMUN + """

Tu es l'agent 5, concepteur des documents et activités élèves.

Règles sur les documents :
- Produis exactement les documents listés dans la section « Documents nécessaires » du déroulé, avec la même numérotation (Doc 1, Doc 2…), ni plus ni moins.
- Utilise la recherche web pour trouver de vrais documents (textes historiques, extraits officiels, statistiques, articles) en privilégiant les sites institutionnels, d'archives, de musées et de presse reconnue.
- Tout texte présenté comme authentique (citation, extrait, chiffre) est accompagné de son auteur, sa date et l'URL où tu l'as trouvé. Ne cite jamais de mémoire. Un extrait raccourci ou simplifié est signalé « texte adapté ».
- Si tu ne trouves pas de source vérifiable, rédige un document pour la classe et indique explicitement « Texte rédigé pour la séance (non authentique) ».
- Textes de 120 mots au maximum, avec les mots difficiles expliqués en note.
- Longueur : la partie élève doit tenir sur 2 pages imprimées (500 mots au maximum, documents compris) ; la partie professeur sur une demi-page (150 mots au maximum).

Entrée : le cadrage, le déroulé et le support de cours.
Sortie, avec exactement ces deux parties :
## Partie élève
### Doc 1 — titre
(source : auteur, date, URL, ou « Texte rédigé pour la séance (non authentique) »). Idem pour chaque document.
### Questions
3 à 5 questions au total, en liste numérotée, progressives : prélever une information, puis expliquer, puis mettre en relation. Une ligne par question.
### Carte ou schéma à compléter
Consigne en 2 phrases : titre, éléments à placer, légende attendue (un cadre vide sera ajouté pour dessiner).
### Exercice d'application
Mise en situation en 2 ou 3 phrases, si possible liée à la spécialité.
### Coup de pouce
2 ou 3 aides courtes.
## Partie professeur
### Corrigé
Réponses brèves, numérotées comme les questions.
### Erreurs fréquentes
2 puces au maximum."""

PROMPT_EVALUATION = CONTEXTE_COMMUN + """

Tu es l'agent 6, concepteur de l'évaluation.

Règles :
- Chaque objectif d'apprentissage du cadrage est évalué par au moins une question.
- Chaque question est rattachée à une capacité du programme, citée avec son intitulé exact.
- La question de réflexion reprend un type d'exercice décrit dans les « Attendus de l'examen » de la fiche de l'agent 1, adapté au niveau de la séance.
- Les questions portent uniquement sur ce qui a été vu dans le support de cours.
- Formulations courtes et sans piège ; pour les QCM, 3 propositions plausibles, en sous-liste sous la question.
- Longueur : la partie élève doit tenir sur une page imprimée, lignes de réponse comprises ; la partie professeur sur une demi-page.

Entrée : la fiche « Référentiel officiel », le cadrage et le support de cours.
Sortie, avec exactement ces deux parties :
## Partie élève
### Quiz
5 questions (QCM ou questions courtes) sur les points clés.
### Question de réflexion
Une seule question, pour une courte réponse construite (5 lignes), proche des attendus de l'examen, qui mobilise une notion du programme.
### Auto-évaluation
Tableau | Capacité | Non acquis | En cours | Acquis | Expert |, 2 capacités au maximum, descripteurs de 8 mots au maximum.
## Partie professeur
### Corrigé
### Correspondance questions / objectifs
Tableau | Question | Objectif évalué | Capacité du programme |.
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
- programme_en_vigueur : la fiche de l'agent 1 identifie le programme en vigueur (texte, date, URL officielle) et explique comment elle l'a vérifié.
- recommandations_appliquees : le déroulé contient le tableau « Conformité aux recommandations officielles », cohérent avec la fiche de l'agent 1 et avec ce que la séance fait réellement.
Une vérification fausse plafonne à 3 la note du critère concerné.

Grille (note entière de 1 à 5 par critère ; 2 et 4 sont des niveaux intermédiaires) :
1. c1_ancrage_programme — 5 : programme en vigueur identifié avec URL officielle, notions/capacités/repères repris avec leurs intitulés exacts, recommandations officielles de mise en œuvre appliquées, évaluation alignée sur les capacités et les attendus de l'examen. 3 : programme identifié mais reprise partielle, recommandations peu appliquées ou sources incomplètes. 1 : aucune source officielle, programme périmé ou thème hors programme.
2. c2_deroule — 5 : total exact, durées réalistes, consignes exactes et actives. 3 : petit écart de durée ou consignes floues. 1 : total faux ou séance irréalisable.
3. c3_niveau_langage — 5 : phrases courtes, vocabulaire expliqué, exemples concrets, longueurs maximales respectées. 3 : quelques passages trop abstraits ou trop longs. 1 : niveau inadapté au lycée professionnel ou documents beaucoup trop longs.
4. c4_coherence — 5 : chaque objectif est travaillé, documenté et évalué ; documents identiques d'un agent à l'autre. 3 : un décalage. 1 : plusieurs décalages.
5. c5_exactitude — 5 : aucune erreur ; toute citation présentée comme authentique a une URL dans les sources consultées, sinon elle est marquée « non authentique ». 3 : une imprécision mineure. 1 : erreur factuelle, ou citation non sourcée présentée comme authentique.

Règles :
- Score global = moyenne des 5 notes. Seuil de livraison : 4/5.
- Si le score est inférieur à 4, liste dans « corrections » chaque agent à refaire (3 au maximum, du plus en amont au plus en aval), avec des consignes précises et actionnables. Ne liste pas un agent qui sera de toute façon régénéré parce qu'il dépend d'un agent corrigé, sauf s'il a un défaut propre.
- Si le score est supérieur ou égal à 4, « corrections » est une liste vide.

Entrée : la demande du prof et l'ensemble du dossier.
Sortie : UNIQUEMENT un objet JSON valide, sans texte avant ni après, de la forme :
{
  "verifications": {"duree_totale_respectee": true, "documents_coherents": false, "objectifs_tous_evalues": true, "programme_repris": true, "parties_separees": true, "programme_en_vigueur": true, "recommandations_appliquees": true},
  "notes": {"c1_ancrage_programme": 4, "c2_deroule": 3, "c3_niveau_langage": 4, "c4_coherence": 3, "c5_exactitude": 4},
  "score_global": 3.6,
  "livraison": "non",
  "corrections": [{"agent": 3, "consignes": ["..."]}, {"agent": 5, "consignes": ["..."]}]
}"""


# --------------------------------------------------------------------------- cadre officiel

CADRE_OFFICIEL_DIR = Path(__file__).resolve().parent / "cadre_officiel"


def lire_cadre_officiel(dossier=CADRE_OFFICIEL_DIR):
    """Fiches du dossier cadre_officiel/ : [{fichier, agents, statut, sources, corps}].

    Format : en-tête « --- » (agents, statut, sources) puis texte markdown ; les commentaires <!-- … --> ne sont
    pas transmis aux agents."""
    fiches = []
    for chemin in sorted(Path(dossier).glob("[0-9]*.md")) if Path(dossier).is_dir() else []:
        texte = chemin.read_text(encoding="utf-8")
        entete, corps = {}, texte
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", texte, re.DOTALL)
        if m:
            for ligne in m.group(1).splitlines():
                if ":" in ligne:
                    cle, valeur = ligne.split(":", 1)
                    entete[cle.strip().lower()] = valeur.strip()
            corps = m.group(2)
        corps = re.sub(r"<!--.*?-->", "", corps, flags=re.DOTALL).strip()
        fiches.append({
            "fichier": chemin.name,
            "agents": {a.strip().upper() for a in entete.get("agents", "").split(",") if a.strip()},
            "statut": entete.get("statut", "à compléter"),
            "sources": entete.get("sources", ""),
            "corps": corps,
        })
    return fiches


CADRE_OFFICIEL = lire_cadre_officiel()


def cadre_officiel(cle, fiches=None):
    """Bloc de consignes « cadre officiel » destiné à l'agent `cle` (vide si aucune fiche ne le concerne)."""
    blocs = []
    for f in CADRE_OFFICIEL if fiches is None else fiches:
        if cle.upper() in f["agents"] and f["corps"]:
            blocs.append(f"[Fiche {f['fichier']} — statut : {f['statut']} — sources : {f['sources']}]\n{f['corps']}")
    if not blocs:
        return ""
    return ("\n\nCADRE OFFICIEL DE RÉFÉRENCE — extraits de textes officiels rassemblés pour VibeProf (statut et sources "
            "indiqués pour chaque fiche). Ils priment sur tes connaissances générales. Une fiche « partiel » ou « à compléter » est incomplète : complète-la par "
            "ta recherche ou tes entrées, sans jamais la contredire.\n\n" + "\n\n".join(blocs))


PROMPT_SOURCES += cadre_officiel("REFERENTIEL")
PROMPT_CADRAGE += cadre_officiel("CADRAGE")
PROMPT_CONCEPTION += cadre_officiel("DEROULE")
PROMPT_REDACTION += cadre_officiel("SUPPORT")
PROMPT_DOCUMENTS += cadre_officiel("DOCUMENTS")
PROMPT_EVALUATION += cadre_officiel("EVALUATION")
PROMPT_RELECTEUR += cadre_officiel("RELECTEUR")


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
     "inputs": ["demande", "1_referentiel_officiel", "2_cadrage"], "web": False,
     "key": "DEROULE", "tier": "principal", "temperature": 0.5},
    {"name": "4_support_cours", "title": "Support de cours", "prompt": PROMPT_REDACTION,
     "inputs": ["2_cadrage", "3_deroule"], "web": False,
     "key": "SUPPORT", "tier": "principal", "temperature": 0.4},
    {"name": "5_documents_eleves", "title": "Documents élèves", "prompt": PROMPT_DOCUMENTS,
     "inputs": ["2_cadrage", "3_deroule", "4_support_cours"], "web": True, "sources_officielles": False,
     "key": "DOCUMENTS", "tier": "principal", "temperature": 0.5},
    {"name": "6_evaluation", "title": "Évaluation", "prompt": PROMPT_EVALUATION,
     "inputs": ["1_referentiel_officiel", "2_cadrage", "4_support_cours"], "web": False,
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
    "programme_en_vigueur": "Programme en vigueur vérifié",
    "recommandations_appliquees": "Recommandations officielles appliquées",
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


class _RouteurParFil:
    """Accès au Routeur du fil courant."""

    def __getattr__(self, name):
        if not hasattr(_LOCAL, "routeur"):
            _LOCAL.routeur = Routeur()
        return getattr(_LOCAL.routeur, name)


ROUTEUR = _RouteurParFil()


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
                log(f"  ({model} n'accepte pas reasoning_effort={reasoning} : nouvel essai sans raisonnement)")
                reasoning = None
                continue
            secours = MODELES["secours"]
            if _is_model_error(exc) and model != secours:
                log(f"  (modèle {model} refusé par l'API [{exc.status_code}] : bascule sur {secours})")
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
                log(f"  (avertissement : suppression de l'agent {agent.id} impossible : {exc})")

    response = call_with_fallback(cfg, request)
    texte, refs = collect_conversation_output(response)
    return format_sources(texte, refs, officielles_seulement=cfg.get("sources_officielles", True))


def run_agent(client, agent, outputs, corrections=None):
    evenement(agent["name"], "correction" if corrections else "en_cours")
    user_content = build_input(outputs, agent, corrections)
    try:
        if agent["web"]:
            texte = call_web_agent(client, agent, user_content)
        else:
            texte = call_agent(client, agent, user_content)
    except Exception as exc:
        evenement(agent["name"], "erreur", message=str(exc))
        raise
    evenement(agent["name"], "termine", modele=ROUTEUR.utilises.get(agent["name"]))
    return texte


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
        log(f"[{i}/{total}] {agent['title']}...")
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
        log(f"  {'correction' if corrections else 'mise à jour'} : {agent['title']}...")
        outputs[agent["name"]] = run_agent(client, agent, outputs, corrections)
        if checkpoint:
            checkpoint(outputs)
    return outputs, True


# --------------------------------------------------------------------------- export .docx

# Charte graphique
POLICE = "Arial"
ACCENT = RGBColor(0x1F, 0x4E, 0x79)
GRIS = RGBColor(0x59, 0x59, 0x59)
FOND_ENTETE = "DCE6F2"      # en-têtes de tableaux
FOND_DOC = "F3F6FA"         # encadrés « Doc N »
FOND_RETIENS = "FFF4D6"     # encadré « Ce que je retiens »
BORDURE = "BFBFBF"
LARGEUR_TEXTE_CM = 17.0     # A4 avec marges de 2 cm

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|`[^`]+`)")
PARTIE_RE = re.compile(r"^#{1,3}\s*\**\s*partie\s+(él[eè]ve|eleve|professeur|prof|enseignant)\b.*$",
                       re.IGNORECASE | re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def add_inline(paragraph, text, size=None):
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**")) or (part.startswith("__") and part.endswith("__")):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Courier New"
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        if size:
            run.font.size = Pt(size)
    return paragraph


# ---- utilitaires XML (python-docx n'expose pas ces réglages)

def _set_cell_fill(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _set_table_borders(table, color=BORDURE, size=4, inside=True):
    tbl_pr = table._tbl.tblPr
    for old in tbl_pr.findall(qn("w:tblBorders")):
        tbl_pr.remove(old)
    borders = OxmlElement("w:tblBorders")
    edges = ["top", "left", "bottom", "right"] + (["insideH", "insideV"] if inside else [])
    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        el = OxmlElement(f"w:{edge}")
        visible = edge in edges
        el.set(qn("w:val"), "single" if visible else "nil")
        if visible:
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:color"), color)
        borders.append(el)
    tbl_pr.append(borders)


def _set_cell_margins(table, top=60, bottom=60, left=100, right=100):
    tbl_pr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tbl_pr.append(mar)


def _row_flag(row, tag):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement(tag)
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def _spacer(container, points=4):
    """Petit espace vertical (paragraphe vide à hauteur fixe)."""
    p = container.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(points)
    return p


def _add_field(paragraph, instr):
    run = paragraph.add_run()
    for tag, attr in (("w:fldChar", "begin"), ("w:instrText", instr), ("w:fldChar", "end")):
        el = OxmlElement(tag)
        if tag == "w:instrText":
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        else:
            el.set(qn("w:fldCharType"), attr)
        run._r.append(el)
    return run


def _strip_theme_fonts(style):
    r_pr = style.element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is not None:
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            r_fonts.attrib.pop(qn(attr), None)


def _remove_paragraph(paragraph):
    paragraph._element.getparent().remove(paragraph._element)


# ---- document et styles

def new_document(eleve, pied_de_page):
    """Document A4 stylé. Côté élève : police plus grande et plus aérée."""
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin, section.bottom_margin = Cm(1.4), Cm(1.4)

    taille = 12 if eleve else 10.5
    normal = doc.styles["Normal"]
    normal.font.name = POLICE
    normal.font.size = Pt(taille)
    _strip_theme_fonts(normal)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15 if eleve else 1.1

    for niveau, (size, color, before) in {1: (taille + 3, ACCENT, 12 if eleve else 14),
                                          2: (taille + 1.5, ACCENT, 8), 3: (taille + 0.5, GRIS, 6)}.items():
        style = doc.styles[f"Heading {niveau}"]
        style.font.name = POLICE
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.italic = False
        style.font.color.rgb = color
        _strip_theme_fonts(style)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True
    for name in ("List Bullet", "List Bullet 2"):
        doc.styles[name].paragraph_format.space_after = Pt(2)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run(f"{pied_de_page}  —  page ")
    run.font.size, run.font.color.rgb = Pt(8), GRIS
    for instr, sep in (("PAGE", " / "), ("NUMPAGES", "")):
        field = _add_field(footer, instr)
        field.font.size, field.font.color.rgb = Pt(8), GRIS
        if sep:
            sep_run = footer.add_run(sep)
            sep_run.font.size, sep_run.font.color.rgb = Pt(8), GRIS
    return doc


def add_title(doc, titre, sous_titre=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(titre)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(18), ACCENT
    if sous_titre:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        run = p.add_run(sous_titre.upper())
        run.font.size, run.font.color.rgb, run.bold = Pt(9), GRIS, True


def add_box(doc, fill, border=BORDURE, hauteur_cm=None):
    """Encadré : tableau 1×1 coloré. Retourne la cellule, dans laquelle on peut écrire du markdown.
    `hauteur_cm` : hauteur minimale (cadre vide pour dessiner une carte, un croquis…)."""
    table = doc.add_table(rows=1, cols=1)
    _set_table_borders(table, color=border, size=6, inside=False)
    _set_cell_margins(table, top=100, bottom=60, left=160, right=160)
    cell = table.cell(0, 0)
    cell.width = Cm(LARGEUR_TEXTE_CM)
    if fill:
        _set_cell_fill(cell, fill)
    if hauteur_cm:
        table.rows[0].height = Cm(hauteur_cm)
        table.rows[0].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    else:
        _row_flag(table.rows[0], "w:cantSplit")
    _spacer(doc, 8)  # respiration après l'encadré
    return cell


def _clean_box(cell):
    if len(cell.paragraphs) > 1 and not cell.paragraphs[0].text.strip():
        _remove_paragraph(cell.paragraphs[0])
    # pas d'espace vide en bas de l'encadré
    while len(cell._tc.xpath("./w:p")) > 1 and not cell.paragraphs[-1].text.strip() \
            and cell._tc[-1].tag == qn("w:p"):
        _remove_paragraph(cell.paragraphs[-1])


def _table_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def add_table(container, lines, size):
    rows = [_table_cells(l) for l in lines if not re.fullmatch(r"\|?[\s:\-|]+\|?", l.strip())]
    if not rows:
        return
    width = max(len(r) for r in rows)
    table = container.add_table(rows=len(rows), cols=width)
    table.autofit = False
    _set_table_borders(table)
    _set_cell_margins(table)
    # largeur des colonnes proportionnelle à leur contenu, bornée
    poids = []
    for j in range(width):
        longueurs = [len(re.sub(r"[*`_]", "", r[j])) for r in rows if j < len(r)]
        poids.append(min(max(sum(longueurs) / max(len(longueurs), 1), 6), 45))
    total_cm = LARGEUR_TEXTE_CM - (0 if hasattr(container, "sections") else 1.2)  # moins large dans un encadré
    largeurs = [Cm(total_cm * p / sum(poids)) for p in poids]
    for i, row in enumerate(rows):
        _row_flag(table.rows[i], "w:cantSplit")
        for j in range(width):
            cell = table.cell(i, j)
            cell.width = largeurs[j]
            par = cell.paragraphs[0]
            par.paragraph_format.space_after = Pt(0)
            add_inline(par, row[j] if j < len(row) else "", size=size)
            if i == 0:
                _set_cell_fill(cell, FOND_ENTETE)
                for run in par.runs:
                    run.bold = True
    _row_flag(table.rows[0], "w:tblHeader")
    _spacer(container, 6)


class Rendu:
    """Convertit le markdown des agents en contenu Word.

    eleve=True active les aides de mise en page pour les fiches élèves : lignes de réponse après les questions,
    cases à cocher pour les QCM, lignes de rédaction pour la question de réflexion et l'exercice.
    """

    LIGNES_PAR_QUESTION = 2
    LIGNES_SECTION = {"reflexion": 5, "exercice": 4}

    def __init__(self, eleve=False):
        self.eleve = eleve
        self.table_size = 11 if eleve else 9.5

    @staticmethod
    def section_kind(titre):
        t = (titre or "").lower()
        if "réflexion" in t or "reflexion" in t:
            return "reflexion"
        if t.startswith("exercice"):
            return "exercice"
        if t.startswith(("question", "quiz")):
            return "questions"
        return None

    def answer_lines(self, container, n):
        for _ in range(n):
            p = container.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.4
            p.paragraph_format.tab_stops.add_tab_stop(Cm(LARGEUR_TEXTE_CM - 0.2), WD_TAB_ALIGNMENT.RIGHT,
                                                      WD_TAB_LEADER.DOTS)
            run = p.add_run("\t")
            run.font.color.rgb = RGBColor(0xA6, 0xA6, 0xA6)

    def markdown(self, container, text, parent_level=0, kind=None):
        """Écrit `text` dans `container` (document ou cellule) ; le titre le plus haut du texte est calé au
        niveau parent_level + 1. `kind` : type de section élève de départ (questions, réflexion…)."""
        lines = (text or "").replace("\r\n", "\n").split("\n")
        niveaux = [len(m.group(1)) for l in lines if (m := HEADING_RE.match(l.strip()))]
        decalage = parent_level + 1 - min(niveaux) if niveaux else 0
        state = {"kind": kind, "pending": False, "options": False}
        buf = []

        def flush_par():
            if buf:
                add_inline(container.add_paragraph(), " ".join(s.strip() for s in buf))
                buf.clear()

        def flush_question():
            if self.eleve and state["pending"] and not state["options"]:
                self.answer_lines(container, self.LIGNES_PAR_QUESTION)
            state["pending"], state["options"] = False, False

        def end_section():
            flush_par()
            flush_question()
            if self.eleve and state["kind"] in self.LIGNES_SECTION:
                self.answer_lines(container, self.LIGNES_SECTION[state["kind"]])

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("```"):
                flush_par()
                i += 1
                code = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code.append(lines[i])
                    i += 1
                run = container.add_paragraph().add_run("\n".join(code))
                run.font.name, run.font.size = "Courier New", Pt(9)
            elif not stripped or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
                flush_par()
            elif m := HEADING_RE.match(stripped):
                end_section()
                titre = m.group(2).strip("# ").replace("**", "")
                level = max(1, min(len(m.group(1)) + decalage, 9))
                container.add_paragraph(titre, style=f"Heading {min(level, 3)}")
                state["kind"] = self.section_kind(titre)
            elif stripped.startswith("|"):
                flush_par()
                flush_question()
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                add_table(container, table_lines, self.table_size)
                continue
            elif m := re.match(r"^(\s*)[-*+•]\s+(.*)$", line):
                flush_par()
                nested = len(m.group(1).replace("\t", "  ")) >= 2
                if self.eleve and nested and state["pending"]:
                    state["options"] = True  # options de QCM sous une question
                    p = container.add_paragraph()
                    p.paragraph_format.left_indent = Cm(1.4)
                    p.paragraph_format.space_after = Pt(0)
                    add_inline(p, "☐  " + re.sub(r"^\(?[a-dA-D][).]\s*", "", m.group(2)))
                else:
                    flush_question()
                    add_inline(container.add_paragraph(style="List Bullet 2" if nested else "List Bullet"),
                               m.group(2))
            elif m := re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line):
                flush_par()
                flush_question()
                nested = len(m.group(1).replace("\t", "  ")) >= 2
                retrait = Cm(1.4 if nested else 0.7)
                p = container.add_paragraph()
                p.paragraph_format.left_indent = retrait
                p.paragraph_format.first_line_indent = -Cm(0.7)
                p.paragraph_format.tab_stops.add_tab_stop(retrait)
                p.paragraph_format.space_after = Pt(2)
                num = p.add_run(f"{m.group(2)}.\t")
                num.bold, num.font.color.rgb = True, ACCENT
                add_inline(p, m.group(3))
                state["pending"] = state["kind"] == "questions" and not nested
            elif stripped.startswith(">"):
                flush_par()
                p = add_inline(container.add_paragraph(), stripped.lstrip("> "))
                for run in p.runs:
                    run.italic = True
            else:
                flush_question()
                buf.append(stripped)
            i += 1
        end_section()


def add_markdown(doc, text, base_level=1):
    """Compatibilité : rendu markdown sans aides élèves, titres calés sous `base_level`."""
    Rendu().markdown(doc, text, parent_level=base_level)


def split_sections(text):
    """Découpe un texte markdown sur ses titres de plus haut niveau : [(titre ou None, corps)]."""
    text = text or ""
    lines = text.split("\n")
    niveaux = [len(m.group(1)) for l in lines if (m := HEADING_RE.match(l.strip()))]
    if not niveaux:
        return [(None, text)]
    top = min(niveaux)
    sections, titre, corps = [], None, []
    for line in lines:
        m = HEADING_RE.match(line.strip())
        if m and len(m.group(1)) == top:
            if titre is not None or "".join(corps).strip():
                sections.append((titre, "\n".join(corps).strip()))
            titre, corps = m.group(2).strip("# ").replace("**", ""), []
        else:
            corps.append(line)
    sections.append((titre, "\n".join(corps).strip()))
    return sections


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


# ---- documents professeur

def _warning(doc, livre, rapports):
    if livre:
        return
    cell = add_box(doc, "FDECEA", border="C00000")
    run = cell.paragraphs[0].add_run(
        f"⚠ Seuil de qualité ({SEUIL_LIVRAISON}/5) non atteint après {len(rapports)} relecture(s) : "
        "relisez attentivement ce cours avant de l'utiliser (voir « Contrôle qualité » en annexe)."
    )
    run.bold, run.font.color.rgb = True, RGBColor(0xC0, 0x00, 0x00)


def _teacher_header(doc, titre, sous_titre, demande, livre, rapports):
    add_title(doc, titre, sous_titre)
    p = doc.add_paragraph()
    label = p.add_run("Demande : ")
    label.bold, label.font.color.rgb = True, GRIS
    p.add_run(demande).font.color.rgb = GRIS
    _warning(doc, livre, rapports)


def _add_rapport(doc, rendu, r, titre, detail=True):
    doc.add_paragraph(titre, style="Heading 2")
    if not detail:
        return
    lignes = ["| Critère | Note /5 |", "|---|---|"]
    lignes += [f"| {CRITERES.get(k, k)} | {v} |" for k, v in (r.get("notes") or {}).items()]
    if len(lignes) > 2:
        add_table(doc, lignes, rendu.table_size)
    verifs = r.get("verifications") or {}
    for key, ok in verifs.items():
        doc.add_paragraph(f"{'✔' if ok is True else '✘'}  {VERIFICATIONS.get(key, key)}", style="List Bullet")
    for corr in r.get("corrections") or []:
        add_inline(doc.add_paragraph(),
                   f"**Renvoi vers l'agent {corr['agent']} ({AGENTS[corr['agent'] - 1]['title']})** :")
        for c in corr["consignes"]:
            add_inline(doc.add_paragraph(style="List Bullet 2"), c)


def _modeles_lignes():
    """Modèles utilisés, regroupés : {modèle: [agents]}."""
    groupes = {}
    for cfg in AGENTS + [RELECTEUR]:
        if cfg["name"] in ROUTEUR.utilises:
            groupes.setdefault(ROUTEUR.utilises[cfg["name"]], []).append(cfg["title"])
    return groupes


def _add_controle_qualite(doc, rendu, rapports, complet):
    """complet=True : chaque relecture en détail (dossier complet). Sinon : synthèse en quelques lignes."""
    if complet:
        for i, r in enumerate(rapports, 1):
            _add_rapport(doc, rendu, r, f"Relecture {i} — {r.get('score_global')}/5 — livraison : {r.get('livraison')}")
        if ROUTEUR.utilises:
            doc.add_paragraph("Modèles utilisés", style="Heading 2")
            lignes = ["| Agent | Modèle |", "|---|---|"]
            lignes += [f"| {cfg['title']} | {ROUTEUR.utilises[cfg['name']]} |"
                       for cfg in AGENTS + [RELECTEUR] if cfg["name"] in ROUTEUR.utilises]
            add_table(doc, lignes, rendu.table_size)
        return
    if rapports:
        historique = " → ".join(f"{r.get('score_global')}/5" for r in rapports)
        dernier = rapports[-1]
        add_inline(doc.add_paragraph(), f"**Score final : {dernier.get('score_global')}/5** "
                                        f"(livraison : {dernier.get('livraison')}) — relectures : {historique}")
        notes = dernier.get("notes") or {}
        if notes:
            courts = {"c1_ancrage_programme": "Programme", "c2_deroule": "Déroulé", "c3_niveau_langage": "Langage",
                      "c4_coherence": "Cohérence", "c5_exactitude": "Exactitude"}
            doc.add_paragraph("Notes : " + " · ".join(f"{courts.get(k, k)} {v}" for k, v in notes.items()))
        verifs = dernier.get("verifications") or {}
        if verifs:
            doc.add_paragraph("  ".join(f"{'✔' if ok is True else '✘'} {VERIFICATIONS.get(k, k)}"
                                        for k, ok in verifs.items()))
        for corr in dernier.get("corrections") or []:
            add_inline(doc.add_paragraph(style="List Bullet"),
                       f"**Reste à corriger ({AGENTS[corr['agent'] - 1]['title']})** : " + " ; ".join(corr["consignes"]))
    for modele, agents in _modeles_lignes().items():
        p = doc.add_paragraph(f"Modèle {modele} : {', '.join(agents)}.")
        p.runs[0].font.size, p.runs[0].font.color.rgb = Pt(9), GRIS
    if CADRE_OFFICIEL:
        statuts = ", ".join(f"{f['fichier'].split('_', 1)[0]} {f['statut']}" for f in CADRE_OFFICIEL)
        p = doc.add_paragraph(f"Cadre officiel fourni aux agents : {len(CADRE_OFFICIEL)} fiches ({statuts}).")
        p.runs[0].font.size, p.runs[0].font.color.rgb = Pt(9), GRIS


ANNEXE_PROGRAMME = ("programme applicable", "thème du programme", "recommandations officielles", "attendus de l",
                    "points sans source", "sources officielles")


def build_docx(path, demande, outputs, rapports, livre):
    """Dossier complet : toutes les productions, tous les rapports et les modèles (archive / consultation)."""
    rendu = Rendu()
    titre = session_title(outputs, demande)
    doc = new_document(eleve=False, pied_de_page=f"Dossier complet — {titre}")
    _teacher_header(doc, titre, "Dossier complet", demande, livre, rapports)
    for agent in AGENTS:
        doc.add_paragraph(agent["title"], style="Heading 1")
        rendu.markdown(doc, outputs.get(agent["name"], ""), parent_level=1)
    doc.add_paragraph("Contrôle qualité", style="Heading 1")
    _add_controle_qualite(doc, rendu, rapports, complet=True)
    doc.save(path)


def build_fiche_professeur(path, demande, outputs, rapports, livre):
    """Fiche de préparation, dans l'ordre d'usage : cadrage, déroulé, corrigés ; programme et contrôle qualité
    en annexe."""
    rendu = Rendu()
    titre = session_title(outputs, demande)
    doc = new_document(eleve=False, pied_de_page=f"Fiche professeur — {titre}")
    _teacher_header(doc, titre, "Fiche professeur", demande, livre, rapports)

    doc.add_paragraph("1. Objectifs et cadrage", style="Heading 1")
    rendu.markdown(doc, outputs.get("2_cadrage", ""), parent_level=1)
    doc.add_paragraph("2. Déroulé de la séance", style="Heading 1")
    rendu.markdown(doc, outputs.get("3_deroule", ""), parent_level=1)
    doc.add_paragraph("3. Corrigés", style="Heading 1")
    for name, sous_titre in (("5_documents_eleves", "Documents et activités"), ("6_evaluation", "Évaluation")):
        eleve, prof = split_parties(outputs.get(name, ""))
        doc.add_paragraph(sous_titre, style="Heading 2")
        if eleve is None:
            p = doc.add_paragraph("Production non séparée en partie élève / professeur : elle figure en entier "
                                  "ici et n'a pas été mise dans le document élève.")
            p.runs[0].italic = True
        rendu.markdown(doc, prof, parent_level=2)

    doc.add_paragraph("Annexe A — Programme officiel et sources", style="Heading 1")
    # Notions, capacités et repères sont déjà repris dans le cadrage : on ne garde ici que la référence du
    # programme et les sources (le texte complet est dans le dossier complet).
    for titre_section, corps in split_sections(outputs.get("1_referentiel_officiel", "")):
        if titre_section is None or titre_section.lower().startswith(ANNEXE_PROGRAMME):
            if titre_section:
                doc.add_paragraph(titre_section, style="Heading 2")
            rendu.markdown(doc, corps, parent_level=2)
    doc.add_paragraph("Annexe B — Contrôle qualité", style="Heading 1")
    _add_controle_qualite(doc, rendu, rapports, complet=False)
    doc.save(path)


# ---- documents élèves

def _student_header(doc, titre, sous_titre):
    add_title(doc, titre, sous_titre)
    table = doc.add_table(rows=1, cols=2)
    _set_table_borders(table, size=6, inside=False)
    _set_cell_margins(table, top=120, bottom=120, left=160, right=160)
    for cell, texte, largeur in ((table.cell(0, 0), "Nom, prénom :", 10.5), (table.cell(0, 1), "Classe :     Date :", 6.5)):
        cell.width = Cm(largeur)
        run = cell.paragraphs[0].add_run(texte)
        run.font.size, run.font.color.rgb = Pt(10), GRIS
        cell.paragraphs[0].paragraph_format.space_after = Pt(0)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def build_document_eleve(path, titre, sous_titre, contenu):
    """Fiche élève : sections au premier niveau ; « Ce que je retiens » et chaque « Doc N » dans un encadré."""
    rendu = Rendu(eleve=True)
    doc = new_document(eleve=True, pied_de_page=f"{titre} — {sous_titre}")
    _student_header(doc, titre, sous_titre)
    if not contenu:
        doc.add_paragraph("Contenu indisponible : voir la fiche professeur.").runs[0].italic = True
        doc.save(path)
        return
    for section_titre, corps in split_sections(contenu):
        t = (section_titre or "").lower()
        if "compléter" in t or "completer" in t or t.startswith("croquis"):
            # consigne puis cadre vide pour dessiner
            doc.add_paragraph(section_titre, style="Heading 1")
            rendu.markdown(doc, corps, parent_level=1)
            add_box(doc, None, hauteur_cm=7)
        elif t.startswith("ce que je retiens") or re.match(r"doc(ument)?\s*\d", t):
            cell = add_box(doc, FOND_RETIENS if t.startswith("ce que") else FOND_DOC)
            cell.add_paragraph(section_titre, style="Heading 2")
            rendu.markdown(cell, corps, parent_level=2)
            _clean_box(cell)
        else:
            if section_titre:
                doc.add_paragraph(section_titre, style="Heading 1")
            rendu.markdown(doc, corps, parent_level=1, kind=Rendu.section_kind(section_titre))
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


class GenerationError(Exception):
    """Échec de la génération ; `outdir` contient les productions partielles (cours_final.json)."""

    def __init__(self, message, outdir):
        super().__init__(message)
        self.outdir = outdir


def generer_cours(client, demande, outdir, max_relectures=MAX_RELECTURES, avancement=None):
    """Exécute tout le workflow et écrit les documents dans `outdir`.

    `avancement(fraction, libelle)` est appelé à chaque étape (barre de progression de l'interface).
    Retourne un dict : outdir, fichiers, livre, statut, rapports, dossier.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rapports = []
    nb_agents = len(AGENTS)
    fait = {"agents": 0}

    def avancer(fraction, libelle):
        if avancement:
            avancement(min(fraction, 1.0), libelle)

    def save(outputs, statut="en_cours", livre=False):
        final = {
            "demande": demande,
            "modeles_configures": dict(MODELES),
            "modeles_utilises": dict(ROUTEUR.utilises),
            "substitutions": dict(ROUTEUR.substitutions),
            "cadre_officiel": [{"fichier": f["fichier"], "statut": f["statut"]} for f in CADRE_OFFICIEL],
            "statut": statut,
            "livre": livre,
            "dossier": outputs,
            "rapports_relecture": rapports,
            "iterations": len(rapports),
        }
        (outdir / "cours_final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    def checkpoint_generation(outputs):
        save(outputs)
        fait["agents"] += 1
        if fait["agents"] < nb_agents:
            avancer(0.7 * fait["agents"] / nb_agents, f"Rédaction : {AGENTS[fait['agents']]['title']}")

    log("Lancement de la chaîne d'agents...")
    avancer(0.0, f"Rédaction : {AGENTS[0]['title']}")
    try:
        outputs = run_pipeline(client, demande, checkpoint=checkpoint_generation)
    except Exception as exc:
        raise GenerationError(f"Erreur pendant la génération : {exc}", outdir) from exc

    livre = False
    statut = "termine"
    for iteration in range(1, max_relectures + 1):
        avancer(0.7 + 0.3 * (iteration - 1) / max_relectures, f"Relecture {iteration}/{max_relectures}")
        log(f"[relecture {iteration}/{max_relectures}] Évaluation par le relecteur...")
        evenement("relecteur", "en_cours", iteration=iteration, max_relectures=max_relectures)
        try:
            rapport, _ = run_relecture(client, outputs)
        except Exception as exc:
            evenement("relecteur", "erreur", message=str(exc))
            log(f"  relecture impossible : {exc}")
            statut = "relecture_en_erreur"
            break
        rapports.append(rapport)
        save(outputs)
        evenement("relecteur", "termine", iteration=iteration, score=rapport["score_global"],
                  livre=rapport["livraison"] == "oui", corrections=[c["agent"] for c in rapport["corrections"]])
        log(f"  score = {rapport['score_global']}/5, livraison = {rapport['livraison']}")
        if rapport["livraison"] == "oui":
            livre = True
            break
        if iteration < max_relectures:
            cibles = ", ".join(f"agent {c['agent']}" for c in rapport["corrections"]) or "aucun agent"
            log(f"  renvoi vers : {cibles}")
            avancer(0.7 + 0.3 * (iteration - 0.5) / max_relectures, f"Corrections demandées par la relecture {iteration}")
            try:
                outputs, corrected = apply_correction(client, outputs, rapport, checkpoint=save)
            except Exception as exc:
                log(f"  correction impossible : {exc}")
                statut = "correction_en_erreur"
                break
            if not corrected:
                log("  aucun agent valide désigné pour la correction, arrêt des relectures.")
                break

    save(outputs, statut=statut, livre=livre)
    avancer(0.98, "Mise en page des documents")
    evenement("documents", "en_cours")
    fichiers = build_deliverables(outdir, demande, outputs, rapports, livre)
    evenement("documents", "termine", fichiers=[f.name for f in fichiers])
    if not livre:
        log(f"⚠ Seuil de {SEUIL_LIVRAISON}/5 non atteint : cours à relire attentivement.")
    avancer(1.0, "Terminé")
    return {"outdir": outdir, "fichiers": fichiers, "livre": livre, "statut": statut,
            "rapports": rapports, "dossier": outputs}


def rendre_depuis_json(source, outdir=None):
    """Régénère les documents à partir d'un cours_final.json (aucun appel à l'API). Retourne les chemins."""
    source = Path(source)
    data = json.loads(source.read_text(encoding="utf-8"))
    ROUTEUR.utilises.update(data.get("modeles_utilises") or {})
    return build_deliverables(Path(outdir or source.parent), data["demande"], data["dossier"],
                              data.get("rapports_relecture") or [], bool(data.get("livre")))


def main():
    parser = argparse.ArgumentParser(description="Workflow agentique de création de cours (Mistral)")
    parser.add_argument("demande", nargs="?",
                        help="Demande du prof, ex: 'Terminale bac pro Commerce, thème: la mondialisation, 2h, TD'")
    parser.add_argument("--rendu", metavar="COURS_FINAL_JSON",
                        help="Régénère uniquement les documents .docx à partir d'un cours_final.json existant "
                             "(aucun appel à l'API)")
    parser.add_argument("--outdir", default="output")
    parser.add_argument("--model", default=MODELES_DEFAUT["principal"],
                        help=f"Modèle principal (défaut : {MODELES_DEFAUT['principal']}, ou $MISTRAL_MODEL)")
    parser.add_argument("--model-leger", default=MODELES_DEFAUT["leger"],
                        help=f"Modèle léger : évaluation et relecture (défaut : {MODELES_DEFAUT['leger']}, ou $MISTRAL_MODEL_LEGER)")
    parser.add_argument("--model-secours", default=MODELES_DEFAUT["secours"],
                        help=f"Modèle de secours si un modèle est refusé (défaut : {MODELES_DEFAUT['secours']}, ou $MISTRAL_MODEL_SECOURS)")
    parser.add_argument("--max-relectures", type=int, default=MAX_RELECTURES)
    args = parser.parse_args()
    configurer_session({"principal": args.model, "leger": args.model_leger, "secours": args.model_secours})

    if args.rendu:
        fichiers = rendre_depuis_json(args.rendu)
        print(f"Documents régénérés dans {Path(args.rendu).parent}/ :")
        for f in fichiers:
            print(f"  - {f.name}")
        return
    if not args.demande:
        parser.error("la demande du prof est obligatoire (sauf avec --rendu)")

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("Erreur : variable d'environnement MISTRAL_API_KEY manquante.")

    outdir = Path(args.outdir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        resultat = generer_cours(make_client(api_key), args.demande, outdir, args.max_relectures)
    except GenerationError as exc:
        sys.exit(f"{exc}\nProductions partielles : {exc.outdir}/cours_final.json")
    print(f"Terminé en {len(resultat['rapports'])} relecture(s). Documents dans {outdir}/ :")
    for f in resultat["fichiers"]:
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
