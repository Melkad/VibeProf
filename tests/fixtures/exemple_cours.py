"""Exemple réaliste de productions d'agents (format structuré), pour tester et prévisualiser le rendu.

Le thème et le programme cités sont réels ; le reste du contenu (documents, chiffres, recommandations) est un exemple
de test, non vérifié.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import schemas  # noqa: E402
from contexte import Contexte  # noqa: E402

DEMANDE = ("Seconde bac pro Métiers du commerce et de la vente, géographie, thème : des réseaux de production et "
           "d'échanges mondialisés, 2 h, Étude de documents (TD)")
CONTEXTE = Contexte("seconde", "géographie", 110)

URL_PROGRAMME = "https://eduscol.education.fr/document/25906/download"
URL_RESSOURCE = "https://eduscol.education.fr/document/25924/download"
URL_SUJET = ("https://www.education.gouv.fr/sites/default/files/document/"
             "baccalaureat-professionnel-2026-histoire-geographie-emc-516839.pdf")

STRUCTURES = {
    "1_referentiel_officiel": {
        "classe": "Seconde professionnelle", "discipline": "géographie",
        "programme": {"intitule": "Programme d'histoire-géographie de seconde professionnelle",
                      "reference_bo": "arrêté du 3 avril 2019, BO du 11 avril 2019", "date": "11 avril 2019",
                      "url": URL_PROGRAMME,
                      "verification_en_vigueur": "Aucun programme plus récent pour cette classe sur Eduscol."},
        "theme": {"programme_annuel": "Production mondiale et circulation des personnes, des biens et des informations",
                  "intitule": "Des réseaux de production et d'échanges mondialisés", "ecart_avec_demande": ""},
        "notions_mots_cles": ["Révolution des transports", "Acteurs", "Plate-forme multimodale",
                              "Entreprise multinationale"],
        "capacites": ["Se repérer : nommer et localiser les grands repères géographiques",
                      "Exploiter les outils spécifiques aux disciplines : compléter un croquis simple",
                      "Contextualiser : situer un document dans son contexte pour l'expliquer"],
        "reperes": [{"texte": "Les grandes routes maritimes mondiales", "vu_au_cycle_4": True},
                    {"texte": "Les principaux ports mondiaux", "vu_au_cycle_4": False}],
        "emc": None,
        "commentaire": {"texte": "Le thème étudie les réseaux de production et d'échanges à l'échelle mondiale et "
                                 "le rôle des transports (résumé de test).", "url": URL_PROGRAMME},
        "recommandations": [
            {"texte": "En seconde, consolider les acquis du cycle 4 ; identifier l'idée générale d'un document "
                      "avant toute analyse critique.", "url": URL_RESSOURCE},
            {"texte": "Privilégier en seconde la tâche cartographique simple (compléter un croquis simple).",
             "url": URL_RESSOURCE}],
        "attendus_examen": [{"texte": "Épreuve écrite E5/U52 en terminale : questions sur repères et notions, "
                                      "dossier documentaire, croquis à compléter.", "url": URL_SUJET}],
        "ressources": [{"texte": "Approche par compétences : mise en œuvre et progressivité sur le cycle bac "
                                 "professionnel", "url": URL_RESSOURCE}],
        "points_sans_source": [],
    },
    "2_cadrage": {
        "classe_theme_specialite": "Seconde bac pro Métiers du commerce et de la vente — géographie — Des réseaux "
                                   "de production et d'échanges mondialisés.",
        "problematique": "Comment un produit fabriqué à l'autre bout du monde arrive-t-il dans nos magasins ?",
        "place_progression": "Première séance du thème, après le thème d'histoire sur l'expansion du monde connu.",
        "objectifs": [
            {"texte": "Décrire le trajet d'un produit importé jusqu'à un magasin.",
             "capacite": "Mener et construire une démarche historique ou géographique et la justifier — décrire "
                         "une situation géographique"},
            {"texte": "Situer les grandes routes maritimes et les principaux ports.",
             "capacite": "Se repérer — nommer et localiser les grands repères géographiques"},
            {"texte": "Expliquer le rôle des ports dans les échanges mondiaux.",
             "capacite": "Contextualiser — situer un document dans son contexte pour l'expliquer"}],
        "notions": ["révolution des transports", "acteurs", "plate-forme multimodale"],
        "capacites": ["Se repérer", "Exploiter les outils spécifiques aux disciplines", "Contextualiser"],
        "reperes": ["Les grandes routes maritimes mondiales", "Les principaux ports mondiaux"],
        "prerequis": ["Lire une carte et sa légende.", "Connaître les continents et les océans."],
        "points_vigilance": ["Confusion entre « flux » et « produit ».", "Lecture d'une carte à petite échelle."],
        "exemples_specialite": ["Le trajet d'un téléviseur jusqu'au rayon d'un hypermarché.",
                                "Les délais de livraison d'une commande client."],
        "decoupage": [{"partie": "Accroche", "duree_min": 10}, {"partie": "Trajet d'un produit", "duree_min": 35},
                      {"partie": "Les ports", "duree_min": 35}, {"partie": "Croquis", "duree_min": 20},
                      {"partie": "Trace écrite", "duree_min": 10}],
    },
    "3_deroule": {
        "etapes": [
            {"duree_min": 10, "titre": "Accroche", "objectif": "faire émerger les représentations",
             "consigne": "Regardez l'étiquette de votre téléphone. Où a-t-il été fabriqué ?",
             "support": "Objets des élèves", "role_prof": "Note les pays au tableau"},
            {"duree_min": 35, "titre": "Trajet d'un produit", "objectif": "décrire un flux",
             "consigne": "Lisez le Doc 1. Retracez le trajet du téléviseur sur la carte du Doc 2.",
             "support": "Doc 1, Doc 2", "role_prof": "Circule, aide les binômes"},
            {"duree_min": 35, "titre": "Les ports", "objectif": "expliquer le rôle des ports",
             "consigne": "Comparez les ports du Doc 3. Lequel est le plus grand ? Pourquoi ?",
             "support": "Doc 3", "role_prof": "Guide la comparaison"},
            {"duree_min": 20, "titre": "Croquis", "objectif": "situer les routes et les ports",
             "consigne": "Complétez le croquis : placez les ports et les routes maritimes.",
             "support": "Fond de carte", "role_prof": "Corrige au fur et à mesure"},
            {"duree_min": 10, "titre": "Trace écrite", "objectif": "fixer les connaissances",
             "consigne": "Complétez le texte à trous.", "support": "Cours", "role_prof": "Valide collectivement"}],
        "documents_necessaires": [
            {"numero": 1, "nature": "Texte", "contenu_attendu": "le voyage d'un conteneur de Shanghai au Havre",
             "etape": "Trajet d'un produit"},
            {"numero": 2, "nature": "Carte", "contenu_attendu": "les grandes routes maritimes mondiales",
             "etape": "Trajet d'un produit"},
            {"numero": 3, "nature": "Tableau statistique", "contenu_attendu": "le trafic de grands ports",
             "etape": "Les ports"}],
        "aide_eleves_en_difficulte": "Carte du Doc 2 avec les noms des océans déjà inscrits ; questions guidées.",
        "prolongement": "Rechercher le port le plus proche du lycée et sa spécialité.",
        "besoins_particuliers": "Documents en police agrandie, consignes lues à voix haute, lexique illustré.",
        "trace_ecrite": "Texte à trous complété collectivement en fin de séance.",
        "conformite": [
            {"recommandation": "Identifier l'idée générale d'un document", "source": "Ressource Eduscol 25924",
             "application": "Question 1 sur le Doc 1 avant la comparaison"},
            {"recommandation": "Tâche cartographique simple en seconde", "source": "Ressource Eduscol 25924",
             "application": "Croquis à compléter (20 min)"}],
    },
    "4_support_cours": {
        "titre": "Le voyage d'un produit mondialisé",
        "ce_que_je_retiens": [
            "La **mondialisation** met en relation les régions du monde par les échanges.",
            "Les produits voyagent surtout par bateau, dans des **conteneurs**.",
            "Les **ports** relient la mer et la terre.",
            "Les grands ports sont des **plates-formes multimodales**."],
        "parties": [
            {"titre": "Un produit qui fait le tour du monde",
             "texte": "Ton téléviseur a souvent été fabriqué en Asie. Il a voyagé dans un conteneur, sur un énorme "
                      "navire. Ce voyage dure environ un mois (voir Doc 1). Ce déplacement s'appelle un **flux**."},
            {"titre": "Les ports, portes d'entrée",
             "texte": "Les navires arrivent dans de grands ports (voir Doc 3). Les marchandises passent du bateau au "
                      "camion ou au train. Un port est une **plate-forme multimodale**."}],
        "vocabulaire": [{"mot": "Mondialisation", "definition": "Mise en relation des pays du monde par les échanges."},
                        {"mot": "Flux", "definition": "Déplacement de marchandises, de personnes ou d'informations."},
                        {"mot": "Conteneur", "definition": "Grande boîte en métal standard pour le transport."}],
        "tableau": {"titre": "Le trajet du téléviseur", "colonnes": ["Étape", "Lieu", "Transport"],
                    "lignes": [["Fabrication", "Usine en Chine", "–"], ["Départ", "Port de Shanghai", "Navire"],
                               ["Arrivée", "Port du Havre", "Navire"], ["Vente", "Magasin", "Camion"]]},
        "schema_description": "",
        "frise_ou_carte": "Carte du monde : routes maritimes entre l'Asie et l'Europe ; placer Shanghai, Singapour, "
                          "Rotterdam et Le Havre.",
    },
    "5_documents_eleves": {
        "documents": [
            {"numero": 1, "titre": "Le voyage d'un conteneur", "nature": "Texte", "authentique": False,
             "auteur": "", "date": "", "url": "", "adapte": False,
             "contenu": "Le 3 mars, un conteneur rempli de téléviseurs quitte le port de Shanghai. Après 32 jours "
                        "de mer, il arrive au Havre. Il est posé sur un camion. Deux jours plus tard, les "
                        "téléviseurs sont en rayon.",
             "notes": [{"mot": "Conteneur", "definition": "grande boîte en métal pour transporter des marchandises"}]},
            {"numero": 2, "titre": "Les grandes routes maritimes mondiales", "nature": "Carte", "authentique": False,
             "auteur": "", "date": "", "url": "", "adapte": False,
             "contenu": "Carte des principales routes maritimes entre l'Asie, l'Europe et l'Amérique (fond fourni "
                        "par le professeur).", "notes": []},
            {"numero": 3, "titre": "Le trafic de grands ports", "nature": "Tableau statistique", "authentique": False,
             "auteur": "", "date": "", "url": "", "adapte": False,
             "contenu": "| Port | Pays | Trafic (Mt) |\n|---|---|---|\n| Shanghai | Chine | 750 |\n"
                        "| Rotterdam | Pays-Bas | 440 |\n| Le Havre | France | 70 |", "notes": []}],
        "questions": [{"texte": "Relevez les étapes du voyage du conteneur.", "documents": [1]},
                      {"texte": "Expliquez pourquoi le port du Havre est une plate-forme multimodale.",
                       "documents": [1]},
                      {"texte": "Comparez le trafic des ports. Que constatez-vous ?", "documents": [3]}],
        "croquis": {"titre": "Les grandes routes maritimes", "consigne": "Complétez le croquis.",
                    "elements_a_placer": ["Shanghai", "Singapour", "Rotterdam", "Le Havre"],
                    "legende": ["Grand port", "Route maritime principale"]},
        "exercice": "Vous êtes vendeur. Un client demande pourquoi sa commande arrive dans un mois. Expliquez-lui "
                    "le trajet du produit en trois phrases.",
        "coup_de_pouce": ["Pensez aux moyens de transport qui se rencontrent au port.",
                          "Utilisez le vocabulaire du cours : flux, conteneur."],
        "corrige": ["Shanghai, mer, Le Havre, camion, magasin.",
                    "Les marchandises y passent du navire au camion ou au train.",
                    "Shanghai traite dix fois plus que Le Havre."],
        "erreurs_frequentes": ["Confusion entre port de départ et port d'arrivée."],
    },
    "6_evaluation": {
        "quiz": [
            {"type": "qcm", "enonce": "Qu'est-ce qu'un flux ?",
             "propositions": ["Un magasin", "Un déplacement de marchandises", "Un pays"],
             "reponse": "Un déplacement de marchandises", "objectif": 1,
             "capacite": "Mener et construire une démarche historique ou géographique et la justifier"},
            {"type": "qcm", "enonce": "Quel est le plus grand port du tableau ?",
             "propositions": ["Le Havre", "Rotterdam", "Shanghai"], "reponse": "Shanghai", "objectif": 2,
             "capacite": "Se repérer"},
            {"type": "courte", "enonce": "Comment voyagent la plupart des marchandises ?", "propositions": [],
             "reponse": "Par bateau, dans des conteneurs.", "objectif": 1,
             "capacite": "Mener et construire une démarche historique ou géographique et la justifier"},
            {"type": "courte", "enonce": "Qu'est-ce qu'une plate-forme multimodale ?", "propositions": [],
             "reponse": "Un lieu où l'on passe d'un mode de transport à un autre.", "objectif": 3,
             "capacite": "Mémoriser et s'approprier les notions"},
            {"type": "courte", "enonce": "Citez un port européen.", "propositions": [],
             "reponse": "Rotterdam ou Le Havre.", "objectif": 2, "capacite": "Se repérer"}],
        "reflexion": {"enonce": "Justifiez l'affirmation suivante en quelques lignes : « Les ports sont "
                                "indispensables à la mondialisation ».",
                      "type_exercice_examen": "justifier une affirmation", "objectif": 3,
                      "capacite": "Contextualiser",
                      "elements_attendus": ["Rôle des conteneurs", "Passage d'un transport à l'autre",
                                            "Exemple d'un port"]},
        "auto_evaluation": [{"capacite": "Se repérer", "non_acquis": "Je ne place aucun port",
                             "en_cours": "Je place un ou deux ports", "acquis": "Je place les quatre ports",
                             "expert": "Je place ports et routes"}],
        "criteres_reussite": ["Vocabulaire utilisé correctement.", "Réponse organisée en deux idées au moins."],
    },
}

RECHERCHES = {  # texte libre rendu par la recherche web des agents 1 et 5 (avant structuration)
    "1_referentiel_officiel": "## Programme applicable\nProgramme de seconde professionnelle. " + URL_PROGRAMME,
    "5_documents_eleves": "## Partie élève\n### Doc 1 — Le voyage d'un conteneur\nTexte rédigé pour la séance.",
}
REFERENCES = {
    "1_referentiel_officiel": [{"title": "Programme HG seconde pro", "url": URL_PROGRAMME}],
    "5_documents_eleves": [],
}


def productions():
    """Markdown des productions (tel que le moteur le produit), à partir des structures."""
    modeles = {n: schemas.SCHEMAS[n].model_validate(d) for n, d in STRUCTURES.items()}
    return {n: schemas.vers_markdown(n, m, STRUCTURES) for n, m in modeles.items()}


OUTPUTS = {"demande": DEMANDE, **productions(), "_structures": STRUCTURES, "_contexte": CONTEXTE.to_dict()}
