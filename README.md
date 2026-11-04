# VibeProf

Workflow agentique (API Mistral) qui génère une séance d'histoire-géographie pour le lycée professionnel, ancrée dans les programmes officiels, et l'exporte en `.docx`.

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

## Installation

```bash
pip install -r requirements.txt
export MISTRAL_API_KEY=...
```

## Utilisation

```bash
python course_workflow.py "Terminale bac pro Commerce, thème : la mondialisation, 2h, TD"
```

Options : `--outdir` (défaut `output`), `--model`, `--model-leger`, `--model-secours` (voir ci-dessus), `--max-relectures` (défaut 3).

Résultat dans `output/<horodatage>/` :

| Fichier | Pour qui | Contenu |
|---------|----------|---------|
| `1_fiche_professeur.docx` | professeur | programme officiel et sources, cadrage, déroulé, corrigés des documents et de l'évaluation, rapports de relecture, modèles utilisés |
| `2_cours_eleve.docx` | élèves | support de cours (« Ce que je retiens », cours, vocabulaire, schéma, frise/carte) |
| `3_documents_eleves.docx` | élèves | documents et activités (partie élève uniquement) |
| `4_evaluation_eleve.docx` | élèves | quiz, question de réflexion, auto-évaluation (partie élève uniquement) |
| `cours_complet.docx` | archive | tout le dossier dans un seul fichier |
| `cours_final.json` | – | toutes les productions brutes, sauvegardé après chaque étape |

Les documents élèves ont un en-tête Nom / Prénom / Classe / Date et ne contiennent jamais de corrigé : si un agent n'a pas séparé « Partie élève » et « Partie professeur », sa production est placée en entier dans la fiche professeur. L'avertissement « seuil non atteint » n'apparaît que côté professeur.

## Tests

```bash
python -m unittest discover -s tests
```

Les tests utilisent un faux client Mistral : aucun appel réseau ni clé API requis.
