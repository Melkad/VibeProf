"""Schémas des productions des agents (sorties JSON strictes) et leur mise en forme markdown.

Chaque agent rend un objet JSON validé par un de ces modèles. Le programme :
- contrôle ce qui est vérifiable (voir controles.py) ;
- produit le markdown lu par les agents suivants et converti en documents Word (fonction `vers_markdown`).

Les valeurs calculables (durée totale, correspondances) ne sont jamais demandées au modèle : le code les calcule.
"""
from typing import Literal

from pydantic import BaseModel

# --------------------------------------------------------------------------- modèles


class Lien(BaseModel):
    texte: str
    url: str


class Definition(BaseModel):
    mot: str
    definition: str


class Repere(BaseModel):
    texte: str
    vu_au_cycle_4: bool


class Programme(BaseModel):
    intitule: str
    reference_bo: str
    date: str
    url: str
    verification_en_vigueur: str


class Theme(BaseModel):
    programme_annuel: str
    intitule: str
    ecart_avec_demande: str


class PartieEMC(BaseModel):
    attendus_objectifs: str
    notions_abordees: list[str]
    contenus: list[str]
    demarches_possibles: list[str]
    horaire_voie_pro: str


class Referentiel(BaseModel):
    classe: str
    discipline: str
    programme: Programme
    theme: Theme
    notions_mots_cles: list[str]
    capacites: list[str]
    reperes: list[Repere]
    emc: PartieEMC | None
    commentaire: Lien
    recommandations: list[Lien]
    attendus_examen: list[Lien]
    ressources: list[Lien]
    points_sans_source: list[str]


class Objectif(BaseModel):
    texte: str
    capacite: str


class PartieHoraire(BaseModel):
    partie: str
    duree_min: int


class Cadrage(BaseModel):
    classe_theme_specialite: str
    problematique: str
    place_progression: str
    objectifs: list[Objectif]
    notions: list[str]
    capacites: list[str]
    reperes: list[str]
    prerequis: list[str]
    points_vigilance: list[str]
    exemples_specialite: list[str]
    decoupage: list[PartieHoraire]


class Etape(BaseModel):
    duree_min: int
    titre: str
    objectif: str
    consigne: str
    support: str
    role_prof: str


class DocumentPrevu(BaseModel):
    numero: int
    nature: str
    contenu_attendu: str
    etape: str


class Conformite(BaseModel):
    recommandation: str
    source: str
    application: str


class Deroule(BaseModel):
    etapes: list[Etape]
    documents_necessaires: list[DocumentPrevu]
    aide_eleves_en_difficulte: str
    prolongement: str
    besoins_particuliers: str
    trace_ecrite: str
    conformite: list[Conformite]


class PartieCours(BaseModel):
    titre: str
    texte: str


class Tableau(BaseModel):
    titre: str
    colonnes: list[str]
    lignes: list[list[str]]


class Support(BaseModel):
    titre: str
    ce_que_je_retiens: list[str]
    parties: list[PartieCours]
    vocabulaire: list[Definition]
    tableau: Tableau | None
    schema_description: str
    frise_ou_carte: str


class DocumentEleve(BaseModel):
    numero: int
    titre: str
    nature: str
    authentique: bool
    auteur: str
    date: str
    url: str
    adapte: bool
    contenu: str
    notes: list[Definition]


class QuestionDocument(BaseModel):
    texte: str
    documents: list[int]


class Croquis(BaseModel):
    titre: str
    consigne: str
    elements_a_placer: list[str]
    legende: list[str]


class Documents(BaseModel):
    documents: list[DocumentEleve]
    questions: list[QuestionDocument]
    croquis: Croquis | None
    exercice: str
    coup_de_pouce: list[str]
    corrige: list[str]
    erreurs_frequentes: list[str]


class QuestionQuiz(BaseModel):
    type: Literal["qcm", "courte"]
    enonce: str
    propositions: list[str]
    reponse: str
    objectif: int
    capacite: str


class Reflexion(BaseModel):
    enonce: str
    type_exercice_examen: str
    objectif: int
    capacite: str
    elements_attendus: list[str]


class AutoEvaluation(BaseModel):
    capacite: str
    non_acquis: str
    en_cours: str
    acquis: str
    expert: str


class Evaluation(BaseModel):
    quiz: list[QuestionQuiz]
    reflexion: Reflexion
    auto_evaluation: list[AutoEvaluation]
    criteres_reussite: list[str]


SCHEMAS = {
    "1_referentiel_officiel": Referentiel,
    "2_cadrage": Cadrage,
    "3_deroule": Deroule,
    "4_support_cours": Support,
    "5_documents_eleves": Documents,
    "6_evaluation": Evaluation,
}

# --------------------------------------------------------------------------- mise en forme markdown


def _cellule(texte):
    return str(texte).replace("|", "/").replace("\n", " ").strip()


def _tableau(colonnes, lignes):
    out = ["| " + " | ".join(_cellule(c) for c in colonnes) + " |", "|" + "---|" * len(colonnes)]
    out += ["| " + " | ".join(_cellule(c) for c in ligne) + " |" for ligne in lignes]
    return "\n".join(out)


def _puces(items, vide="Aucun."):
    items = [i for i in items if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else f"- {vide}"


def _liens(liens, vide="SOURCE OFFICIELLE NON TROUVÉE"):
    return _puces([f"{l.texte} — {l.url}" if l.url else l.texte for l in liens], vide)


def duree_totale(etapes_ou_parties):
    return sum(max(int(e.duree_min), 0) for e in etapes_ou_parties)


def md_referentiel(r: Referentiel):
    p = r.programme
    blocs = [
        "## Programme applicable",
        f"{r.classe}, {r.discipline}. {p.intitule} — {p.reference_bo} ({p.date}). URL : {p.url}",
        f"Vérification : {p.verification_en_vigueur}",
        "## Thème du programme",
        f"**{r.theme.programme_annuel} — {r.theme.intitule}**"
        + (f"\n\nÉcart avec la demande : {r.theme.ecart_avec_demande}" if r.theme.ecart_avec_demande.strip() else ""),
    ]
    if r.emc:
        blocs += [
            "## Attendus et objectifs", r.emc.attendus_objectifs,
            "## Notions abordées", _puces(r.emc.notions_abordees),
            "## Contenus d'enseignement", _puces(r.emc.contenus),
            "## Démarches et situations d'apprentissage possibles", _puces(r.emc.demarches_possibles),
            f"Horaire indicatif en voie professionnelle : {r.emc.horaire_voie_pro}",
        ]
    else:
        reperes = [f"*{x.texte}* (vu au cycle 4)" if x.vu_au_cycle_4 else x.texte for x in r.reperes]
        blocs += ["## Notions et mots-clés", _puces(r.notions_mots_cles),
                  "## Capacités", _puces(r.capacites),
                  "## Repères", _puces(reperes)]
    blocs += [
        "## Commentaire du programme",
        f"{r.commentaire.texte} URL : {r.commentaire.url}" if r.commentaire.url else r.commentaire.texte,
        "## Recommandations officielles de mise en œuvre", _liens(r.recommandations),
        "## Attendus de l'examen", _liens(r.attendus_examen),
        "## Ressources d'accompagnement officielles", _liens(r.ressources, "Aucune."),
        "## Points sans source officielle", _puces(r.points_sans_source),
    ]
    return "\n\n".join(blocs)


def md_cadrage(c: Cadrage):
    objectifs = "\n".join(f"{i}. {o.texte} *(capacité : {o.capacite})*" for i, o in enumerate(c.objectifs, 1))
    lignes = [[p.partie, f"{p.duree_min} min"] for p in c.decoupage]
    lignes.append(["**Total**", f"**{duree_totale(c.decoupage)} min**"])
    return "\n\n".join([
        "## Classe, thème et spécialité", c.classe_theme_specialite,
        "## Problématique", c.problematique,
        "## Place dans la progression (proposition)", c.place_progression,
        "## Objectifs d'apprentissage", objectifs or "- Aucun.",
        "## Notions, capacités et repères travaillés",
        _puces([f"Notions : {', '.join(c.notions)}", f"Capacités : {' ; '.join(c.capacites)}",
                f"Repères : {' ; '.join(c.reperes)}"]),
        "## Prérequis", _puces(c.prerequis),
        "## Points de vigilance (hypothèses)", _puces(c.points_vigilance),
        "## Exemples liés à la spécialité", _puces(c.exemples_specialite),
        "## Découpage horaire", _tableau(["Partie", "Durée"], lignes),
    ])


def md_deroule(d: Deroule):
    lignes = [[f"{e.duree_min} min", f"**{e.titre}** — {e.objectif}", e.consigne, e.support, e.role_prof]
              for e in d.etapes]
    docs = [f"**Doc {x.numero}** — {x.nature} : {x.contenu_attendu.rstrip('. ')}. Étape : {x.etape.rstrip('. ')}."
            for x in sorted(d.documents_necessaires, key=lambda x: x.numero)]
    conformite = [[x.recommandation, x.source, x.application] for x in d.conformite]
    return "\n\n".join([
        "## Déroulé",
        _tableau(["Durée", "Étape et objectif", "Consigne aux élèves", "Support", "Rôle du prof"], lignes),
        f"**Total : {duree_totale(d.etapes)} min**",
        "## Documents nécessaires", _puces(docs),
        "## Différenciation",
        _puces([f"Élèves en difficulté : {d.aide_eleves_en_difficulte}",
                f"Élèves plus rapides : {d.prolongement}",
                f"Élèves à besoins éducatifs particuliers : {d.besoins_particuliers}"]),
        "## Trace écrite", d.trace_ecrite,
        "## Conformité aux recommandations officielles",
        _tableau(["Recommandation officielle", "Source", "Application dans la séance"], conformite)
        if conformite else "- Aucune recommandation officielle relevée.",
    ])


def md_support(s: Support):
    blocs = [f"# {s.titre}", "## Ce que je retiens", _puces(s.ce_que_je_retiens), "## Cours"]
    for i, p in enumerate(s.parties, 1):
        blocs += [f"### {i}. {p.titre}", p.texte]
    blocs += ["## Vocabulaire", _tableau(["Mot", "Définition simple"], [[v.mot, v.definition] for v in s.vocabulaire])]
    blocs.append("## Schéma ou tableau")
    if s.tableau and s.tableau.lignes:
        if s.tableau.titre.strip():
            blocs.append(f"**{s.tableau.titre}**")
        blocs.append(_tableau(s.tableau.colonnes, s.tableau.lignes))
    if s.schema_description.strip():
        blocs.append(s.schema_description)
    blocs += ["## Frise ou carte", s.frise_ou_carte]
    return "\n\n".join(blocs)


def _source(doc: DocumentEleve):
    if not doc.authentique:
        return "*Texte rédigé pour la séance (non authentique)*"
    elements = [x for x in (doc.auteur, doc.date) if x.strip()]
    texte = "Source : " + ", ".join(elements) if elements else "Source"
    if doc.adapte:
        texte += " (texte adapté)"
    return f"*{texte}.* {doc.url}".strip()


def md_documents(d: Documents):
    blocs = ["## Partie élève"]
    for doc in sorted(d.documents, key=lambda x: x.numero):
        blocs += [f"### Doc {doc.numero} — {doc.titre}", _source(doc), doc.contenu]
        if doc.notes:
            blocs.append("\n".join(f"*{n.mot}* : {n.definition}" for n in doc.notes))
    questions = []
    for i, q in enumerate(d.questions, 1):
        renvoi = f" (Doc {', '.join(str(n) for n in q.documents)})" if q.documents else ""
        questions.append(f"{i}. {q.texte}{renvoi}")
    blocs += ["### Questions", "\n".join(questions) or "- Aucune."]
    if d.croquis:
        c = d.croquis
        blocs += ["### Carte ou schéma à compléter", f"**{c.titre}** — {c.consigne}",
                  "Éléments à placer : " + ", ".join(c.elements_a_placer) + ".",
                  "Légende : " + " ; ".join(c.legende) + "."]
    blocs += ["### Exercice d'application", d.exercice, "### Coup de pouce", _puces(d.coup_de_pouce),
              "## Partie professeur", "### Corrigé",
              "\n".join(f"{i}. {r}" for i, r in enumerate(d.corrige, 1)) or "- Aucun.",
              "### Erreurs fréquentes", _puces(d.erreurs_frequentes)]
    return "\n\n".join(blocs)


def md_evaluation(e: Evaluation, cadrage: Cadrage | None = None):
    quiz = []
    for i, q in enumerate(e.quiz, 1):
        quiz.append(f"{i}. {q.enonce}")
        if q.type == "qcm":
            quiz += [f"   - {p}" for p in q.propositions]
    auto = [[a.capacite, a.non_acquis, a.en_cours, a.acquis, a.expert] for a in e.auto_evaluation]

    def objectif(n):
        if cadrage and 1 <= n <= len(cadrage.objectifs):
            return f"{n}. {cadrage.objectifs[n - 1].texte}"
        return f"Objectif {n}"

    correspondance = [[str(i), objectif(q.objectif), q.capacite] for i, q in enumerate(e.quiz, 1)]
    correspondance.append(["Réflexion", objectif(e.reflexion.objectif), e.reflexion.capacite])
    corrige = [f"{i}. {q.reponse}" for i, q in enumerate(e.quiz, 1)]
    return "\n\n".join([
        "## Partie élève",
        "### Quiz", "\n".join(quiz),
        "### Question de réflexion", e.reflexion.enonce,
        "### Auto-évaluation",
        _tableau(["Capacité", "Non acquis", "En cours", "Acquis", "Expert"], auto) if auto else "- Aucune.",
        "## Partie professeur",
        "### Corrigé", "\n".join(corrige),
        f"Question de réflexion ({e.reflexion.type_exercice_examen}) — éléments attendus :",
        _puces(e.reflexion.elements_attendus),
        "### Correspondance questions / objectifs",
        _tableau(["Question", "Objectif évalué", "Capacité du programme"], correspondance),
        "### Critères de réussite", _puces(e.criteres_reussite),
    ])


def vers_markdown(nom, modele, structures=None):
    """Markdown d'une production, à partir de son modèle validé."""
    structures = structures or {}
    if nom == "6_evaluation":
        cadrage = structures.get("2_cadrage")
        return md_evaluation(modele, Cadrage.model_validate(cadrage) if cadrage else None)
    return {
        "1_referentiel_officiel": md_referentiel,
        "2_cadrage": md_cadrage,
        "3_deroule": md_deroule,
        "4_support_cours": md_support,
        "5_documents_eleves": md_documents,
    }[nom](modele)
