"""Exemple réaliste de productions d'agents (format des prompts), pour tester et prévisualiser le rendu.

Le thème et le programme cités sont réels ; le reste du contenu (documents, chiffres, recommandations) est un exemple
de test, non vérifié."""

DEMANDE = "Seconde bac pro Métiers du commerce et de la vente, géographie, thème : des réseaux de production et d'échanges mondialisés, 2 h, Étude de documents (TD)"

OUTPUTS = {
    "demande": DEMANDE,
    "1_referentiel_officiel": """## Programme applicable
Classe de seconde professionnelle, géographie. Programme d'histoire-géographie de seconde professionnelle (arrêté du 3 avril 2019, BO du 11 avril 2019). URL : https://eduscol.education.fr/document/25906/download
Vérification : aucun programme plus récent pour cette classe sur la page Eduscol de la voie professionnelle.

## Thème du programme
**Production mondiale et circulation des personnes, des biens et des informations — thème « Des réseaux de production et d'échanges mondialisés ».** Le thème demandé correspond exactement à un intitulé du programme.

## Notions et mots-clés
- Révolution des transports
- Acteurs
- Plate-forme multimodale
- Entreprise multinationale

## Capacités
- Se repérer : nommer et localiser les grands repères géographiques ainsi que les principaux processus étudiés.
- Exploiter les outils spécifiques aux disciplines : compléter ou réaliser un croquis simple de géographie.
- Contextualiser : situer un document dans son contexte pour l'expliquer.

## Repères
- *Principales façades maritimes européennes*
- Les principaux ports européens (Rotterdam, Anvers, Hambourg, Le Havre)
- Les grandes métropoles françaises et européennes

## Commentaire du programme
Le thème étudie les réseaux de production et d'échanges à l'échelle mondiale et le rôle des transports dans la mondialisation (résumé de test). URL : https://eduscol.education.fr/document/25906/download

## Recommandations officielles de mise en œuvre
- En seconde, consolider les acquis du cycle 4 ; identifier l'idée générale d'un document avant toute analyse critique. URL : https://eduscol.education.fr/document/25924/download
- Privilégier en seconde la tâche cartographique simple (compléter un croquis simple). URL : https://eduscol.education.fr/document/25924/download
- Éclairer les mutations de l'économie que les élèves appréhendent en période de formation en milieu professionnel. URL : https://eduscol.education.fr/document/25906/download

## Attendus de l'examen
- Épreuve écrite E5/U52 en terminale (2 h 30) : questions sur repères et notions, dossier documentaire avec croquis à compléter, texte d'une dizaine de lignes. URL : https://www.education.gouv.fr/sites/default/files/document/baccalaureat-professionnel-2026-histoire-geographie-emc-516839.pdf

## Ressources d'accompagnement officielles
- Approche par compétences : mise en œuvre et progressivité sur le cycle bac professionnel : https://eduscol.education.fr/document/25924/download

## Points sans source officielle
- Aucun.

## Sources officielles consultées
- Programme d'histoire-géographie de seconde professionnelle : https://eduscol.education.fr/document/25906/download
- Ressources d'accompagnement : https://eduscol.education.fr/document/25924/download""",
    "2_cadrage": """## Classe, thème et spécialité
Seconde bac pro Métiers du commerce et de la vente. Géographie, thème « Des réseaux de production et d'échanges mondialisés ». Séance de 2 heures (110 minutes effectives) en TD.

## Place dans la progression (proposition)
Première séance du thème de géographie, après le thème d'histoire sur l'expansion du monde connu.

## Objectifs d'apprentissage
1. **Situer** les principales façades maritimes et ports européens sur une carte (capacité : situer et caractériser les flux).
2. **Décrire** le trajet d'un produit importé jusqu'à un magasin français (notion : flux).
3. **Expliquer** pourquoi les ports sont des interfaces essentielles dans la mondialisation (notion : interface).

## Notions, capacités et repères travaillés
- Notions : mondialisation, flux, interface, façade maritime.
- Capacités : situer et caractériser les principaux flux ; réaliser une production graphique.
- Repères : principales façades maritimes européennes ; ports de Rotterdam, Anvers, Hambourg, Le Havre.

## Prérequis
- Savoir lire une carte et sa légende.
- Connaître les continents et les océans.

## Points de vigilance (hypothèses)
- Confusion possible entre « flux » et « produit ».
- Difficulté à lire une carte à petite échelle.

## Exemples liés à la spécialité
- Le trajet d'un téléviseur fabriqué en Chine jusqu'au rayon d'un hypermarché.
- La gestion des stocks et des délais de livraison dans un magasin.

## Découpage horaire
| Partie | Durée |
|---|---|
| Accroche | 10 min |
| Étude du trajet d'un produit | 35 min |
| Les ports européens | 35 min |
| Production graphique | 20 min |
| Trace écrite | 10 min |
| **Total** | **110 min** |""",
    "3_deroule": """## Déroulé
| Durée | Étape et objectif | Consigne aux élèves | Support | Rôle du prof |
|---|---|---|---|---|
| 10 min | **Accroche** — faire émerger les représentations | Regardez l'étiquette de votre téléphone. Où a-t-il été fabriqué ? | Objets des élèves | Note les pays au tableau |
| 35 min | **Trajet d'un produit** — décrire un flux | Lisez le Doc 1. Retracez le trajet du téléviseur sur la carte. | Doc 1, Doc 2 | Circule, aide les binômes |
| 35 min | **Les ports européens** — expliquer le rôle d'interface | Comparez les ports du Doc 3. Lequel est le plus grand ? Pourquoi ? | Doc 3 | Guide la comparaison |
| 20 min | **Production graphique** — situer les façades | Complétez le croquis : placez les ports et la façade maritime. | Fond de carte | Corrige au fur et à mesure |
| 10 min | **Trace écrite** — fixer les connaissances | Complétez le texte à trous. | Cours | Valide collectivement |

**Total : 110 min**

## Documents nécessaires
- **Doc 1** — Texte : le voyage d'un conteneur de Shanghai au Havre (récit, 120 mots). Étape 2.
- **Doc 2** — Carte : les grandes routes maritimes mondiales. Étape 2.
- **Doc 3** — Tableau statistique : trafic des principaux ports européens. Étape 3.

## Différenciation
- Élèves en difficulté : carte du Doc 2 avec les noms des océans déjà inscrits ; questions guidées.
- Élèves rapides : rechercher le port le plus proche du lycée et sa spécialité.

## Trace écrite
Texte à trous complété collectivement en fin de séance.

## Conformité aux recommandations officielles
| Recommandation officielle | Source | Application dans la séance |
|---|---|---|
| Consolider les acquis du cycle 4, identifier l'idée générale d'un document | Ressource Eduscol 25924 | Trajet d'un téléviseur (Doc 1) avant les ports européens |
| Tâche cartographique simple en seconde | Ressource Eduscol 25924 | Croquis des ports et de la façade (20 min) |
| Lien avec la formation professionnelle | Préambule du programme | Exercice du vendeur, accroche sur les étiquettes |""",
    "4_support_cours": """# Le voyage d'un produit mondialisé

## Ce que je retiens
- La **mondialisation** est la mise en relation des différentes régions du monde par des échanges.
- Les produits voyagent surtout par bateau, dans des **conteneurs**.
- Les **ports** sont des **interfaces** : ils relient la mer et la terre.
- La **façade maritime** de la mer du Nord concentre les plus grands ports d'Europe.
- La France possède de grands ports, comme Le Havre et Marseille, mais ils sont moins puissants que Rotterdam.

## Cours
### 1. Un produit qui fait le tour du monde
Ton téléviseur a souvent été fabriqué en Asie. Il a voyagé dans un conteneur, sur un énorme navire. Ce voyage dure environ un mois (voir Doc 1). Ce déplacement de marchandises s'appelle un **flux**. Les flux relient les usines, les ports et les magasins.

### 2. Les ports, portes d'entrée de l'Europe
Les navires arrivent dans de grands ports européens. Le plus grand est Rotterdam, aux Pays-Bas (voir Doc 3). Ces ports sont des **interfaces** : les marchandises passent du bateau au camion ou au train. La plupart des grands ports sont situés sur la **façade maritime** de la mer du Nord, appelée la « Northern Range ».

### 3. La place de la France
La France a des atouts : une longue côte, des ports comme Le Havre et Marseille-Fos. Mais ses ports reçoivent moins de marchandises que ceux de la mer du Nord. Beaucoup de produits vendus en France arrivent d'abord à Anvers ou Rotterdam.

## Vocabulaire
| Mot | Définition simple |
|---|---|
| Mondialisation | Mise en relation des pays du monde par les échanges. |
| Flux | Déplacement de marchandises, de personnes ou d'informations. |
| Interface | Lieu de contact entre deux espaces (ex : la mer et la terre). |
| Façade maritime | Littoral où se regroupent plusieurs grands ports. |
| Conteneur | Grande boîte en métal standard pour transporter les marchandises. |

## Schéma ou tableau
| Étape | Lieu | Moyen de transport |
|---|---|---|
| Fabrication | Usine en Chine | – |
| Départ | Port de Shanghai | Porte-conteneurs |
| Arrivée | Port du Havre | Porte-conteneurs |
| Distribution | Entrepôt puis magasin | Camion |

## Frise ou carte
Carte de l'Europe : faire figurer la mer du Nord, la Manche, la Méditerranée ; placer Rotterdam, Anvers, Hambourg, Le Havre, Marseille ; colorier la façade de la mer du Nord ; légende : port majeur (gros point), façade maritime (trait épais bleu).""",
    "5_documents_eleves": """## Partie élève
### Doc 1 — Le voyage d'un conteneur
*Texte rédigé pour la séance (non authentique)*

Le 3 mars, un conteneur rempli de téléviseurs quitte le port de Shanghai. Il est chargé sur un porte-conteneurs de 400 mètres de long. Le navire traverse l'océan Indien, passe par le canal de Suez, puis longe les côtes européennes. Après 32 jours de mer, il arrive au Havre. Le conteneur est déchargé par une grue, puis posé sur un camion. Deux jours plus tard, les téléviseurs sont en rayon dans un hypermarché de Rouen.

### Doc 2 — Les grandes routes maritimes mondiales
Carte : principales routes maritimes reliant l'Asie, l'Europe et l'Amérique (source : à fournir par le professeur).

### Doc 3 — Le trafic des principaux ports européens
| Port | Pays | Trafic (millions de tonnes) |
|---|---|---|
| Rotterdam | Pays-Bas | 440 |
| Anvers | Belgique | 270 |
| Hambourg | Allemagne | 115 |
| Le Havre | France | 70 |
*Chiffres arrondis — source : à vérifier par le professeur.*

### Questions
1. Relevez dans le Doc 1 les étapes du voyage du conteneur.
2. Expliquez pourquoi le port du Havre est une interface.
3. À l'aide du Doc 3, montrez que les ports français sont moins puissants que ceux de la mer du Nord.

### Carte ou schéma à compléter
Titre : « Les grands ports de la façade maritime européenne ». Placer : Rotterdam, Anvers, Hambourg, Le Havre, Marseille. Légende : port majeur, façade de la mer du Nord.

### Exercice d'application
Vous êtes vendeur dans un magasin d'électroménager. Un client demande pourquoi sa commande arrive dans un mois. Expliquez-lui en trois phrases le trajet du produit.

### Coup de pouce
- Pour la question 2, pensez aux moyens de transport qui se rencontrent au port.
- Utilisez le vocabulaire du cours : flux, interface, conteneur.

## Partie professeur
### Corrigé
1. Shanghai, océan Indien, canal de Suez, côtes européennes, Le Havre, camion, Rouen.
2. Le port est un lieu où les marchandises passent du bateau au camion : il relie la mer et la terre.
3. Rotterdam traite 440 Mt contre 70 Mt pour Le Havre, soit plus de six fois plus.

### Erreurs fréquentes
- Confusion entre le port de départ et le port d'arrivée.
- Oubli du transport terrestre final.

## Sources consultées (recherche web)
- Aucune source trouvée par la recherche web.""",
    "6_evaluation": """## Partie élève
### Quiz
1. Qu'est-ce qu'un flux ?
   - a) Un magasin
   - b) Un déplacement de marchandises, de personnes ou d'informations
   - c) Un pays
2. Quel est le plus grand port d'Europe ?
   - a) Le Havre
   - b) Marseille
   - c) Rotterdam
3. Comment voyagent la plupart des marchandises ?
4. Qu'est-ce qu'une interface ?
5. Citez deux ports français.

### Question de réflexion
En quelques lignes, expliquez pourquoi les ports sont indispensables dans la mondialisation.

### Auto-évaluation
| Capacité | Non acquis | En cours | Acquis | Expert |
|---|---|---|---|---|
| Situer les ports européens | Je ne sais pas placer les ports | J'en place 1 ou 2 | Je place les 4 ports | Je place les ports et la façade |
| Décrire un flux | Je ne sais pas | Je cite le départ et l'arrivée | Je décris les étapes | Je décris et j'explique |

## Partie professeur
### Corrigé
1. b — 2. c — 3. Par bateau, dans des conteneurs. — 4. Un lieu de contact entre deux espaces. — 5. Le Havre, Marseille.

### Correspondance questions / objectifs
| Question | Objectif évalué | Capacité du programme |
|---|---|---|
| 1, 3 | Décrire un flux | Mener et construire une démarche géographique : décrire une situation géographique |
| 2, 5 | Situer les ports | Se repérer : nommer et localiser les grands repères géographiques |
| 4, réflexion | Expliquer le rôle d'interface | Contextualiser : situer un document dans son contexte pour l'expliquer |

### Critères de réussite
- Vocabulaire utilisé correctement.
- Réponse de réflexion organisée en au moins deux idées.""",
}
