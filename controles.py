"""Contrôles automatiques des productions structurées : ce que le code peut vérifier n'est pas laissé au relecteur.

Gravité :
- « bloquant » : la séance ne peut pas être livrée en l'état ; l'agent concerné est relancé avec le message ;
- « alerte » : signalé au relecteur et dans la fiche professeur, sans bloquer.
"""
import re
import unicodedata
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

import schemas
from contexte import niveau

# Intitulés des capacités du tableau officiel « Compétences disciplinaires en baccalauréat professionnel »
# (voir cadre_officiel/03_capacites.md).
CAPACITES_OFFICIELLES = (
    "Mémoriser et s'approprier les notions",
    "Se repérer",
    "Contextualiser",
    "Exploiter les outils spécifiques aux disciplines",
    "Mener et construire une démarche historique ou géographique et la justifier",
    "Collaborer et échanger en histoire-géographie",
)
DOMAINES_OFFICIELS = ("eduscol.education.fr", "eduscol.education.gouv.fr", "education.gouv.fr", "legifrance.gouv.fr")
TOLERANCE_DUREE_MIN = 5


@dataclass
class Controle:
    code: str
    agent: int
    gravite: str
    message: str

    def to_dict(self):
        return asdict(self)


def normaliser(texte):
    texte = unicodedata.normalize("NFD", str(texte).lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


_CAPACITES_NORM = [normaliser(c) for c in CAPACITES_OFFICIELLES]


def capacite_officielle(texte):
    """Vrai si le texte cite (au moins le début de) l'intitulé d'une capacité officielle."""
    t = normaliser(texte)
    return any(c in t or (len(c) > 25 and c[:25] in t) for c in _CAPACITES_NORM)


def nb_mots(texte):
    return len(re.findall(r"\w+", str(texte)))


def est_officiel(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in DOMAINES_OFFICIELS)


def _modele(structures, nom):
    data = (structures or {}).get(nom)
    return schemas.SCHEMAS[nom].model_validate(data) if data else None


def verifier(structures, contexte=None, references_web=None):
    """Retourne la liste des Controle pour les productions disponibles."""
    ctl = []
    ajouter = lambda code, agent, gravite, message: ctl.append(Controle(code, agent, gravite, message))
    ref = _modele(structures, "1_referentiel_officiel")
    cad = _modele(structures, "2_cadrage")
    der = _modele(structures, "3_deroule")
    sup = _modele(structures, "4_support_cours")
    docs = _modele(structures, "5_documents_eleves")
    ev = _modele(structures, "6_evaluation")
    n = niveau(contexte)
    discipline = getattr(contexte, "discipline", None) or (ref.discipline if ref else None)
    hg = discipline is None or normaliser(discipline) in ("histoire", "geographie")
    cible = getattr(contexte, "duree_min", None)

    # --- référentiel
    if ref:
        if not est_officiel(ref.programme.url):
            ajouter("programme_source", 1, "alerte",
                    f"L'URL du programme ({ref.programme.url or 'absente'}) n'est pas sur un site officiel.")
        if normaliser(discipline or "") == "emc" and ref.emc is None:
            ajouter("emc_structure", 1, "alerte", "Séance d'EMC : les rubriques du programme d'EMC 2024 manquent.")

    # --- durées
    if cad:
        total_cadrage = schemas.duree_totale(cad.decoupage)
        if cible and abs(total_cadrage - cible) > TOLERANCE_DUREE_MIN:
            ajouter("duree", 2, "bloquant",
                    f"Le découpage horaire totalise {total_cadrage} min au lieu de {cible} min. "
                    f"Ajuste les durées pour totaliser exactement {cible} min.")
        cible = cible or total_cadrage
    if der:
        total = schemas.duree_totale(der.etapes)
        if cible and total != cible:
            ajouter("duree", 3, "bloquant",
                    f"Les étapes du déroulé totalisent {total} min au lieu de {cible} min. "
                    f"Ajuste les durées pour totaliser exactement {cible} min.")
        if len(der.etapes) > 7:
            ajouter("longueur", 3, "alerte", f"{len(der.etapes)} étapes (7 au maximum).")
        longues = [i for i, e in enumerate(der.etapes, 1) if nb_mots(e.consigne) > 30]
        if longues:
            ajouter("longueur", 3, "alerte", f"Consignes trop longues (étapes {', '.join(map(str, longues))}) : "
                                             "25 mots au maximum.")
        if len(der.documents_necessaires) > n["docs_max"]:
            ajouter("longueur", 3, "alerte",
                    f"{len(der.documents_necessaires)} documents prévus ({n['docs_max']} au maximum pour cette classe).")

    # --- capacités officielles (histoire-géographie)
    if hg and cad:
        hors = [o.capacite for o in cad.objectifs if not capacite_officielle(o.capacite)]
        if hors:
            ajouter("capacites", 2, "bloquant",
                    "Capacités non conformes au tableau officiel : " + " ; ".join(hors) +
                    ". Cite l'intitulé exact d'une capacité : " + " ; ".join(CAPACITES_OFFICIELLES) + ".")
    if hg and ev:
        hors = [q.capacite for q in ev.quiz if not capacite_officielle(q.capacite)]
        if not capacite_officielle(ev.reflexion.capacite):
            hors.append(ev.reflexion.capacite)
        if hors:
            ajouter("capacites", 6, "bloquant",
                    "Capacités non conformes au tableau officiel : " + " ; ".join(dict.fromkeys(hors)) +
                    ". Cite l'intitulé exact d'une capacité : " + " ; ".join(CAPACITES_OFFICIELLES) + ".")

    # --- documents : cohérence entre déroulé et dossier élève, sources
    if der and docs:
        prevus = {d.numero for d in der.documents_necessaires}
        produits = {d.numero for d in docs.documents}
        if prevus != produits:
            manquants = sorted(prevus - produits)
            en_trop = sorted(produits - prevus)
            details = []
            if manquants:
                details.append("manquants : " + ", ".join(f"Doc {x}" for x in manquants))
            if en_trop:
                details.append("non prévus par le déroulé : " + ", ".join(f"Doc {x}" for x in en_trop))
            ajouter("documents", 5, "bloquant",
                    "Les documents ne correspondent pas à ceux du déroulé (" + " ; ".join(details) + "). "
                    "Produis exactement les documents listés dans « Documents nécessaires ».")
    if docs:
        produits = {d.numero for d in docs.documents}
        for d in docs.documents:
            if d.authentique and not d.url.strip():
                ajouter("sources", 5, "bloquant",
                        f"Doc {d.numero} présenté comme authentique sans URL : donne l'URL où il a été trouvé, "
                        "ou marque-le « non authentique ».")
            elif d.authentique and references_web is not None and not est_officiel(d.url) \
                    and d.url not in references_web:
                ajouter("sources", 5, "alerte",
                        f"Doc {d.numero} : l'URL {d.url} ne figure pas parmi les pages consultées par la recherche.")
            if nb_mots(d.contenu) > n["texte_doc_max"] * 1.3:
                ajouter("longueur", 5, "bloquant" if nb_mots(d.contenu) > n["texte_doc_max"] * 1.8 else "alerte",
                        f"Doc {d.numero} : {nb_mots(d.contenu)} mots ({n['texte_doc_max']} au maximum).")
        for i, q in enumerate(docs.questions, 1):
            inconnus = [x for x in q.documents if x not in produits]
            if inconnus:
                ajouter("documents", 5, "alerte", f"La question {i} renvoie à un document inexistant "
                                                  f"(Doc {', '.join(map(str, inconnus))}).")
        if len(docs.corrige) != len(docs.questions):
            ajouter("corrige", 5, "alerte",
                    f"{len(docs.corrige)} réponses au corrigé pour {len(docs.questions)} questions.")

    # --- évaluation : chaque objectif évalué, forme du quiz
    if cad and ev:
        nb = len(cad.objectifs)
        references = [q.objectif for q in ev.quiz] + [ev.reflexion.objectif]
        hors = sorted({r for r in references if not 1 <= r <= nb})
        if hors:
            ajouter("objectifs", 6, "bloquant",
                    f"Numéros d'objectif inexistants : {', '.join(map(str, hors))} (le cadrage en compte {nb}).")
        non_evalues = [i for i in range(1, nb + 1) if i not in references]
        if non_evalues:
            ajouter("objectifs", 6, "bloquant",
                    "Objectifs non évalués : " + ", ".join(str(i) for i in non_evalues) +
                    ". Chaque objectif du cadrage doit être évalué par au moins une question.")
    if ev:
        if len(ev.quiz) != 5:
            ajouter("quiz", 6, "alerte", f"Le quiz compte {len(ev.quiz)} questions au lieu de 5.")
        for i, q in enumerate(ev.quiz, 1):
            if q.type == "qcm" and len(q.propositions) != 3:
                ajouter("quiz", 6, "alerte", f"QCM {i} : {len(q.propositions)} propositions au lieu de 3.")
            if q.type == "qcm" and q.propositions and \
                    normaliser(q.reponse) not in [normaliser(p) for p in q.propositions] and \
                    not any(normaliser(p) in normaliser(q.reponse) for p in q.propositions):
                ajouter("quiz", 6, "alerte", f"QCM {i} : la réponse ne figure pas parmi les propositions.")

    # --- support de cours
    if sup:
        mots = nb_mots(" ".join([sup.titre, *sup.ce_que_je_retiens, *(p.texte for p in sup.parties),
                                 *(v.definition for v in sup.vocabulaire)]))
        mini, maxi = n["support_mots"]
        if mots > maxi * 1.6:
            ajouter("longueur", 4, "bloquant", f"Support de cours de {mots} mots ({mini} à {maxi} attendus) : "
                                               "raccourcis-le.")
        elif mots > maxi * 1.2 or mots < mini * 0.6:
            ajouter("longueur", 4, "alerte", f"Support de cours de {mots} mots ({mini} à {maxi} attendus).")
        if not 3 <= len(sup.ce_que_je_retiens) <= 5:
            ajouter("longueur", 4, "alerte", f"« Ce que je retiens » compte {len(sup.ce_que_je_retiens)} points "
                                             "(3 à 5 attendus).")
    return ctl


def bloquants(controles):
    return [c for c in controles if c.gravite == "bloquant"]


def verifications(controles, structures):
    """Vérifications calculées par le code (elles remplacent celles du relecteur pour ces points)."""
    codes_bloquants = {c.code for c in bloquants(controles)}
    resultat = {}
    if "2_cadrage" in structures or "3_deroule" in structures:
        resultat["duree_totale_respectee"] = "duree" not in codes_bloquants
    if "5_documents_eleves" in structures:
        resultat["documents_coherents"] = not ({"documents", "sources"} & codes_bloquants)
        resultat["parties_separees"] = True  # garanti par la structure des productions
    if "6_evaluation" in structures:
        resultat["objectifs_tous_evalues"] = "objectifs" not in codes_bloquants
    if "2_cadrage" in structures:
        resultat["programme_repris"] = "capacites" not in codes_bloquants
    return resultat


def corrections(controles):
    """Corrections à demander : {numéro d'agent: [consignes]} pour les contrôles bloquants."""
    par_agent = {}
    for c in bloquants(controles):
        par_agent.setdefault(c.agent, []).append(c.message)
    return par_agent
