# VibeProf

Workflow agentique (API Mistral) qui génère une séance d'histoire-géographie pour le lycée professionnel, ancrée dans les programmes officiels, et l'exporte en `.docx`.

## Nouveautés de la version 2 : la boucle avec le professeur

La génération ne se fait plus forcément d'une traite : **le professeur valide les étapes clés** avant que la suite soit rédigée.

1. **Programme et cadrage** : relecture du référentiel officiel et du cadrage (problématique, objectifs, découpage horaire).
2. **Déroulé de séance** : relecture des étapes, consignes et documents prévus.

À chaque pause, une zone « Ce qu'il faut modifier » accompagne chaque partie. Le commentaire est transmis à l'agent concerné, qui refait sa production ; les parties déjà rédigées qui en dépendent sont mises à jour (une retouche du référentiel refait aussi le cadrage). Les contrôles automatiques sont recalculés aussitôt, sans relecteur IA. On peut retoucher autant de fois que nécessaire, puis « Valider et continuer ». Après la dernière validation, la fin du cours est rédigée, relue par le relecteur et mise en page comme avant.

Les demandes du professeur restent transmises à l'agent lors des corrections suivantes (le relecteur ne peut pas les défaire), le relecteur les reçoit comme « déjà appliquées », et elles sont conservées dans `cours_final.json` (`dossier._retours_professeur`) et en annexe de `cours_complet.docx`. Sur le graphe du workflow, les parties à valider sont en violet et les retours du professeur apparaissent en flèches pointillées violettes.

Décocher « Valider le cadrage et le déroulé avant la suite » dans le formulaire retrouve la génération d'une traite. En ligne de commande, `course_workflow.py` génère toujours d'une traite ; les fonctions `demarrer_dossier`, `avancer_pipeline`, `reviser_partie` et `finaliser_cours` permettent de piloter la boucle depuis un autre programme.

## Interface web (sans environnement de développement)

VibeProf s'utilise depuis le navigateur : on remplit un formulaire (classe, spécialité, discipline, thème choisi parmi les thèmes officiels en vigueur ou saisi librement, durée, format), on suit la progression sur un **graphe du workflow** mis à jour en direct (agent en cours, terminé avec sa durée, renvois du relecteur en pointillés), puis on télécharge les documents Word (un par un ou en `.zip`) et on les prévisualise.

Il faut une **clé API Mistral** (à créer sur [console.mistral.ai](https://console.mistral.ai)) : elle se saisit dans la barre latérale et n'est jamais enregistrée.

### Sur son ordinateur

1. Installer [Python](https://www.python.org/downloads/) (sous Windows, cocher « Add python.exe to PATH »).
2. Télécharger le projet (bouton « Code » → « Download ZIP » sur GitHub) et le décompresser.
3. Double-cliquer sur :
   - **Windows** : `lancer_vibeprof.bat`
   - **macOS** : `lancer_vibeprof.command` (la première fois : clic droit → Ouvrir)

La première fois, l'installation prend quelques minutes ; ensuite l'interface s'ouvre directement dans le navigateur. Fermer la fenêtre noire arrête VibeProf.

### En ligne, pour toute une équipe

L'application peut être hébergée gratuitement sur [Streamlit Community Cloud](https://streamlit.io/cloud) : « New app » → choisir ce dépôt et le fichier `app.py`. Dans « Secrets », on peut définir :

```toml
MISTRAL_API_KEY = "..."         # facultatif : clé partagée, les utilisateurs n'ont plus à saisir la leur
VIBEPROF_CODE_ACCES = "..."     # fortement conseillé avec une clé partagée : code demandé à l'ouverture
```

Sans `VIBEPROF_CODE_ACCES`, toute personne ayant le lien pourrait générer des cours aux frais de la clé partagée.

### Rouvrir un cours

Le `.zip` contient `cours_final.json`. Le déposer plus tard dans « Rouvrir un cours » (barre latérale) régénère les documents Word sans appeler l'API.

## Fonctionnement

| # | Agent | Reçoit | Modèle | Temp. |
|---|-------|--------|--------|-------|
| 1 | Référentiel officiel (recherche web, eduscol / education.gouv uniquement) | demande | principal | 0,1 |
| 2 | Cadrage (problématique, objectifs, découpage horaire) | demande, référentiel | principal | 0,2 |
| 3 | Déroulé de séance | demande, référentiel, cadrage | principal | 0,5 |
| 4 | Support de cours | cadrage, déroulé | principal | 0,4 |
| 5 | Documents élèves (recherche web, sources vérifiables) | cadrage, déroulé, support | principal | 0,5 |
| 6 | Évaluation formative | référentiel, cadrage, support | léger | 0,3 |
| – | Relecteur (raisonnement `high`) | tout le dossier + contrôles automatiques | léger | 0 |

**Sorties structurées.** Chaque agent rend un objet JSON strict (schémas dans [`schemas.py`](schemas.py), noms de champs en français) ; les agents 1 et 5 font d'abord leur recherche web en texte libre, puis une étape de structuration la convertit fidèlement. Le programme produit ensuite le markdown lu par les agents suivants et les documents Word. Ce qui se calcule (durée totale, correspondance questions / objectifs) est calculé par le code, pas demandé au modèle.

**Contrôles automatiques** ([`controles.py`](controles.py)), avant chaque relecture :

| Contrôle | Gravité |
|---|---|
| durée du découpage et du déroulé = durée effective demandée (une heure de cours = 55 min) | bloquant |
| documents produits = documents prévus par le déroulé | bloquant |
| document présenté comme authentique sans URL | bloquant |
| capacités citées = intitulés du tableau officiel (histoire-géographie) | bloquant |
| chaque objectif évalué par au moins une question | bloquant |
| longueurs (textes, support, consignes, nombre d'étapes) adaptées à la classe | alerte, bloquant si très excessif |
| forme du quiz, URL non consultée, programme hors site officiel | alerte |

Un contrôle bloquant renvoie l'agent concerné avec un message précis, sans attendre le relecteur, et empêche la livraison. Le relecteur reçoit les résultats et se concentre sur ce que le code ne peut pas juger (pédagogie, exactitude, programme en vigueur, recommandations appliquées, sujets sensibles). Les points restants figurent dans la fiche professeur (« Points à vérifier avant utilisation ») et dans l'interface.

**Adapté aux professeurs français.** Vocabulaire de l'Éducation nationale (séance, problématique, consigne, trace écrite, évaluation formative, différenciation, élèves à besoins éducatifs particuliers), aucun calque de l'anglais, consignes à l'impératif, typographie française dans les documents Word (« guillemets », espaces insécables). Consignes propres à chaque classe ([`contexte.py`](contexte.py) : longueur des phrases et des textes, nombre de documents) et fiches officielles filtrées par classe et par discipline.

**Sujets sensibles et sécurité.** Neutralité et laïcité, faits historiques établis présentés avec rigueur (génocides, traites et esclavage, colonisation…), questions vives présentées sans prise de parti, documents adaptés à l'âge. La demande du professeur est transmise comme une donnée balisée, jamais comme une instruction.

## Cadre officiel

Pour coller au plus près des textes officiels, les agents reçoivent dans leurs consignes les fiches du dossier [`cadre_officiel/`](cadre_officiel/README.md) : sources officielles à consulter en priorité, organisation des programmes, capacités, épreuves d'examen, recommandations de mise en œuvre. Chaque fiche indique son statut (`vérifié`, `partiel`, `à compléter`) et ses sources ; on les complète en recopiant les textes officiels, sans toucher au code.

Les agents doivent aussi :
- vérifier que le programme cité est **celui en vigueur** (date du texte) ;
- relever les **recommandations de mise en œuvre** de la ressource d'accompagnement Eduscol du thème, et les **attendus de l'examen** ;
- rattacher objectifs et questions d'évaluation aux **capacités** avec leurs intitulés exacts ;
- produire un tableau **« Conformité aux recommandations officielles »** (recommandation, source, application dans la séance), repris dans la fiche professeur.

Le relecteur contrôle en plus que le programme en vigueur a été vérifié et que les recommandations sont appliquées.

## Modèles

| Niveau | Défaut | Rôle | Surcharge |
|--------|--------|------|-----------|
| principal | `mistral-large-4` | rédaction, raisonnement pédagogique | `--model` / `$MISTRAL_MODEL` |
| léger | `mistral-small-2603` | évaluation et relecture (modèle **différent** des rédacteurs, pour limiter l'auto-complaisance) | `--model-leger` / `$MISTRAL_MODEL_LEGER` |
| secours | `mistral-large-2512` | utilisé automatiquement si un modèle est refusé par l'API (préversion retirée, identifiant inconnu) | `--model-secours` / `$MISTRAL_MODEL_SECOURS` |

Chaque agent peut aussi être forcé individuellement : `MISTRAL_MODEL_REFERENTIEL`, `_CADRAGE`, `_DEROULE`, `_SUPPORT`, `_DOCUMENTS`, `_EVALUATION`, `_RELECTEUR`.

Si un modèle n'accepte pas `reasoning_effort`, l'appel est refait sans raisonnement. Les modèles réellement utilisés sont tracés dans `cours_final.json` (`modeles_utilises`, `substitutions`) et en annexe du `.docx`.

Pour vérifier les identifiants disponibles sur votre compte :

```bash
python -c "from mistralai.client import Mistral; import os; [print(m.id) for m in Mistral(api_key=os.environ['MISTRAL_API_KEY']).models.list().data]"
```

## Ligne de commande

```bash
pip install -r requirements.txt
export MISTRAL_API_KEY=...
```

Interface web en local : `streamlit run app.py`.

### Utilisation

```bash
python course_workflow.py "Terminale bac pro Commerce, thème : la mondialisation, 2h, TD"
```

Options : `--outdir` (défaut `output`), `--model`, `--model-leger`, `--model-secours` (voir ci-dessus), `--max-relectures` (défaut 3).

Résultat dans `output/<horodatage>/` :

| Fichier | Pour qui | Contenu |
|---------|----------|---------|
| `1_fiche_professeur.docx` | professeur | ~3 pages : objectifs et cadrage, déroulé, corrigés ; en annexe : référence du programme, sources, synthèse du contrôle qualité |
| `2_cours_eleve.docx` | élèves | ~2 pages : « Ce que je retiens » encadré, cours, vocabulaire, schéma, frise/carte |
| `3_documents_eleves.docx` | élèves | ~2 pages : documents encadrés, questions avec lignes de réponse, cadre pour la carte à compléter, exercice, coup de pouce |
| `4_evaluation_eleve.docx` | élèves | 1 page : quiz (cases à cocher pour les QCM, lignes de réponse), question de réflexion, auto-évaluation |
| `cours_complet.docx` | archive | tout le dossier, programme complet et toutes les relectures en détail |
| `cours_final.json` | – | toutes les productions brutes, sauvegardé après chaque étape |

Les documents élèves ont un en-tête Nom / Classe / Date, une police plus grande et ne contiennent jamais de corrigé : si un agent n'a pas séparé « Partie élève » et « Partie professeur », sa production est placée en entier dans la fiche professeur. L'avertissement « seuil non atteint » n'apparaît que côté professeur. Les longueurs sont cadrées dans les prompts (nombre de mots, de questions, de lignes de tableau) et le relecteur pénalise les documents trop longs.

Pour retoucher la mise en page sans relancer les agents (aucun appel à l'API) :

```bash
python course_workflow.py --rendu output/<horodatage>/cours_final.json
```

## Banc d'évaluation

[`evaluation/cas.json`](evaluation/cas.json) contient 14 demandes types sur des thèmes officiels (CAP, seconde, première, terminale ; histoire, géographie, EMC). Le banc génère un cours pour chacune et produit un rapport (livraison, score, notes par critère, contrôles restants, longueurs, durée) pour comparer les versions de VibeProf :

```bash
python evaluation/banc.py --limite 3        # appels réels à l'API : coût réel
python evaluation/banc.py --simulation      # vérifie le banc lui-même, sans API
```

Résultats dans `evaluation/resultats/<horodatage>/rapport.md`.

## Tests

```bash
python -m unittest discover -s tests
```

Les tests utilisent un faux client Mistral : aucun appel réseau ni clé API requis. `tests/test_app.py` teste l'interface Streamlit (formulaire, génération, erreurs, code d'accès) avec `streamlit.testing`.
