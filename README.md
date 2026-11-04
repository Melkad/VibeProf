# VibeProf

Workflow agentique (API Mistral) qui génère une séance d'histoire-géographie pour le lycée professionnel, ancrée dans les programmes officiels, et l'exporte en `.docx`.

## Interface web (sans environnement de développement)

VibeProf s'utilise depuis le navigateur : on remplit un formulaire (classe, spécialité, discipline, thème, durée, format), on suit la progression sur un **graphe du workflow** mis à jour en direct (agent en cours, terminé avec sa durée, renvois du relecteur en pointillés), puis on télécharge les documents Word (un par un ou en `.zip`) et on les prévisualise.

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
| 2 | Cadrage | demande, référentiel | principal | 0,2 |
| 3 | Déroulé de séance | demande, cadrage | principal | 0,5 |
| 4 | Support de cours | cadrage, déroulé | principal | 0,4 |
| 5 | Documents élèves (recherche web, sources vérifiables) | cadrage, déroulé, support | principal | 0,5 |
| 6 | Évaluation | cadrage, support | léger | 0,3 |
| – | Relecteur (raisonnement `high`) | tout le dossier | léger | 0 |

Tous les agents partagent un contexte commun : public de lycée pro, HG-EMC, vocabulaire officiel des programmes (notions et mots-clés, capacités, repères), sortie en markdown, interdiction d'inventer. L'agent 1 recopie mot pour mot les rubriques du programme ; l'agent 3 fixe la liste numérotée des documents (Doc 1, Doc 2…) que l'agent 5 produit à l'identique ; documents élèves et évaluation séparent « Partie élève » et « Partie professeur ».

Un **relecteur** fait ensuite 5 vérifications (durée totale, cohérence des documents, objectifs évalués, programme repris, parties séparées) et note le dossier sur 5 critères avec une grille détaillée. Si la moyenne est sous 4/5, il désigne un ou plusieurs agents à refaire avec des consignes ; ces agents et ceux qui en dépendent sont régénérés, chacun une seule fois (3 relectures max).

Les sources trouvées par la recherche web sont listées à la fin des productions 1 et 5 :
- référentiel : seules les sources des domaines officiels sont retenues, les autres sont signalées comme écartées ;
- documents élèves : toutes les sources consultées sont listées, et les URL citées sans provenir de la recherche sont signalées « à vérifier ».

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

## Tests

```bash
python -m unittest discover -s tests
```

Les tests utilisent un faux client Mistral : aucun appel réseau ni clé API requis. `tests/test_app.py` teste l'interface Streamlit (formulaire, génération, erreurs, code d'accès) avec `streamlit.testing`.
