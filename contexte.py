"""Contexte d'une demande : classe, discipline, durée effective, et consignes VibeProf propres à chaque classe.

L'interface web fournit ces informations directement (champs du formulaire) ; en ligne de commande, elles sont
déduites du texte de la demande.
"""
import re
from dataclasses import asdict, dataclass

CLASSES = ("CAP", "seconde", "première", "terminale")
DISCIPLINES = ("histoire", "géographie", "EMC")
MINUTES_PAR_HEURE_DE_COURS = 55  # usage courant en lycée : une « heure » de cours dure 55 minutes


@dataclass
class Contexte:
    classe: str | None = None          # CAP, seconde, première, terminale
    discipline: str | None = None      # histoire, géographie, EMC
    duree_min: int | None = None       # durée effective de la séance, en minutes

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(data.get("classe"), data.get("discipline"), data.get("duree_min"))


def duree_effective(texte):
    """« 2 h » -> 110 ; « 1 h 30 » -> 85 ; « 55 min » -> 55 ; None si aucune durée.

    Une heure de cours compte 55 minutes ; les minutes indiquées en plus s'ajoutent telles quelles."""
    texte = (texte or "").lower()
    m = re.search(r"(\d+)\s*h(?:eures?)?\s*(\d{1,2})?(?!\w)", texte)
    if m:
        return int(m.group(1)) * MINUTES_PAR_HEURE_DE_COURS + int(m.group(2) or 0)
    m = re.search(r"(\d+)\s*min", texte)
    return int(m.group(1)) if m else None


def analyser_demande(texte):
    """Déduit classe, discipline et durée d'une demande en texte libre (ligne de commande)."""
    t = texte or ""
    tl = t.lower()
    classe = None
    if re.search(r"\bCAP\b", t):
        classe = "CAP"
    elif re.search(r"\b(seconde|2nde|2de)\b", tl):
        classe = "seconde"
    elif re.search(r"\b(premi[eè]re|1re|1ère)\b", tl):
        classe = "première"
    elif re.search(r"\b(terminale|tle)\b", tl):
        classe = "terminale"
    discipline = None
    if re.search(r"\bemc\b|enseignement moral", tl):
        discipline = "EMC"
    else:
        geo = "géograph" in tl or "geograph" in tl
        hist = re.search(r"\bhistoire\b", tl) is not None
        if geo and not hist:
            discipline = "géographie"
        elif hist and not geo:
            discipline = "histoire"
    return Contexte(classe, discipline, duree_effective(t))


# Consignes VibeProf par classe (choix pédagogiques de l'outil, distincts des textes officiels du dossier
# cadre_officiel/). Elles servent aussi de seuils aux contrôles automatiques.
NIVEAUX = {
    "CAP": {"phrase_max": 15, "texte_doc_max": 80, "docs_max": 3, "support_mots": (250, 450),
            "consigne": "Public souvent fragile à l'écrit : consignes très guidées, une seule tâche par consigne, "
                        "documents courts, questions surtout de prélèvement et de description."},
    "seconde": {"phrase_max": 20, "texte_doc_max": 120, "docs_max": 3, "support_mots": (350, 550),
                "consigne": "Classe de consolidation du cycle 4 : remettre les élèves en confiance avec les outils "
                            "de la discipline, étayer fortement les productions."},
    "première": {"phrase_max": 20, "texte_doc_max": 150, "docs_max": 4, "support_mots": (350, 550),
                 "consigne": "Plus de place à la production écrite, avec étayage pour les élèves fragiles."},
    "terminale": {"phrase_max": 25, "texte_doc_max": 150, "docs_max": 4, "support_mots": (350, 600),
                  "consigne": "Viser l'autonomie et préparer progressivement aux consignes de l'épreuve écrite "
                              "E5/U52 (dater, définir, présenter un document, justifier, compléter un croquis, "
                              "rédiger une dizaine de lignes)."},
}
NIVEAU_PAR_DEFAUT = {"phrase_max": 20, "texte_doc_max": 120, "docs_max": 4, "support_mots": (350, 550),
                     "consigne": ""}


def niveau(contexte):
    return NIVEAUX.get(getattr(contexte, "classe", None), NIVEAU_PAR_DEFAUT)


def consignes_contexte(contexte):
    """Bloc de consignes VibeProf pour la classe, la discipline et la durée de la demande."""
    if contexte is None:
        return ""
    n = niveau(contexte)
    lignes = []
    if contexte.classe:
        lignes.append(f"- Classe : {contexte.classe}. {n['consigne']}".rstrip())
    if contexte.discipline:
        lignes.append(f"- Discipline : {contexte.discipline}.")
    if contexte.duree_min:
        lignes.append(f"- Durée effective de la séance : {contexte.duree_min} minutes (une heure de cours compte "
                      f"{MINUTES_PAR_HEURE_DE_COURS} minutes). Le découpage horaire et le déroulé totalisent "
                      "exactement cette durée.")
    lignes.append(f"- Phrases destinées aux élèves : {n['phrase_max']} mots au maximum. Textes des documents : "
                  f"{n['texte_doc_max']} mots au maximum. {n['docs_max']} documents au maximum. Support de cours : "
                  f"{n['support_mots'][0]} à {n['support_mots'][1]} mots.")
    return "\n".join(lignes)


# Thèmes des programmes en vigueur (voir cadre_officiel/02_structure_programmes.md et 06_emc.md, vérifiés le
# 04/11/2026), proposés dans l'interface. Clé : (classe, discipline).
THEMES_OFFICIELS = {
    ("CAP", "histoire"): [
        "La France de la Révolution française à la Ve République : l'affirmation démocratique",
        "La France et la construction européenne depuis 1950"],
    ("CAP", "géographie"): ["Espaces, transports et mobilités", "Espaces urbains : acteurs et enjeux"],
    ("seconde", "histoire"): [
        "L'expansion du monde connu (XVe-XVIIIe siècle)",
        "L'Amérique et l'Europe en révolution (des années 1760 à 1804)",
        "Métiers, compagnons, compagnonnage et chef-d'œuvre au XIXe siècle"],
    ("seconde", "géographie"): [
        "Des réseaux de production et d'échanges mondialisés",
        "Une circulation croissante mais diverse des personnes à l'échelle mondiale"],
    ("première", "histoire"): [
        "Hommes et femmes au travail, en métropole et dans les colonies françaises (XIXe siècle-1ère moitié du "
        "XXe siècle)",
        "Guerres européennes, guerres mondiales, guerres totales (1914-1945)"],
    ("première", "géographie"): [
        "La recomposition du territoire urbain en France : métropolisation et périurbanisation",
        "L'Afrique, un continent en recomposition"],
    ("terminale", "histoire"): [
        "Le jeu des puissances dans les relations internationales depuis 1945",
        "Vivre en France en démocratie depuis 1945"],
    ("terminale", "géographie"): [
        "L'accès aux ressources pour produire, consommer, se loger et se déplacer",
        "Les sociétés et les risques : anticiper, réagir, se coordonner et s'adapter"],
    ("CAP", "EMC"): [
        "L'État de droit est garant des libertés et des droits fondamentaux",
        "Liberté et responsabilité : l'exemple de l'information (vecteurs, nécessité et enjeux)",
        "Droits et responsabilité : l'exemple de la protection de l'environnement et sauvegarde de la biodiversité",
        "La délibération dans les institutions (nationales, européennes, internationales) : l'exemple des "
        "questions environnementales",
        "Les valeurs et les principes de la République à l'épreuve de la cohésion sociale",
        "La République et la Nation",
        "L'engagement politique des citoyennes et citoyens au service de la société"],
    ("seconde", "EMC"): [
        "L'État de droit garantit les droits et libertés et un pluralisme démocratique",
        "Liberté et responsabilité : l'exemple de l'information (vecteurs, nécessité et enjeux)",
        "Droits et responsabilité : l'exemple de la protection de l'environnement et de la sauvegarde de la "
        "biodiversité"],
    ("première", "EMC"): [
        "Les valeurs et les principes de la République à l'épreuve de la cohésion sociale",
        "La République et la Nation"],
    ("terminale", "EMC"): [
        "Les principes et les espaces du débat démocratique",
        "La délibération dans les institutions"],
}
