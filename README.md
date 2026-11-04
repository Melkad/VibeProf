# VibeProf

Workflow agentique (API Mistral) qui génère une séance d'histoire-géographie pour le lycée professionnel, ancrée dans les programmes officiels, et l'exporte en `.docx`.

## Fonctionnement

| # | Agent | Reçoit |
|---|-------|--------|
| 1 | Référentiel officiel (recherche web, eduscol / education.gouv) | demande |
| 2 | Cadrage | demande, référentiel |
| 3 | Déroulé de séance | demande, cadrage |
| 4 | Support de cours | cadrage, déroulé |
| 5 | Documents élèves | cadrage, déroulé, support |
| 6 | Évaluation | cadrage, support |

Un **relecteur** note ensuite le dossier sur 5 critères. Si la moyenne est sous 4/5, il renvoie vers l'agent fautif avec des consignes ; cet agent et ceux qui en dépendent sont régénérés (3 relectures max).

Les sources trouvées par la recherche web sont listées en fin de référentiel : seules celles des domaines officiels sont retenues, les autres sont signalées comme écartées.

## Installation

```bash
pip install -r requirements.txt
export MISTRAL_API_KEY=...
```

## Utilisation

```bash
python course_workflow.py "Terminale bac pro Commerce, thème : la mondialisation, 2h, TD"
```

Options : `--outdir` (défaut `output`), `--model` (défaut `mistral-large-4` ou `$MISTRAL_MODEL`), `--max-relectures` (défaut 3).

Résultat dans `output/<horodatage>/` :
- `cours_final.docx` : le cours mis en forme, avec les rapports de relecture (et un avertissement si le seuil n'est pas atteint) ;
- `cours_final.json` : toutes les productions, sauvegardé après chaque étape (rien n'est perdu en cas d'erreur).

## Tests

```bash
python -m unittest discover -s tests
```

Les tests utilisent un faux client Mistral : aucun appel réseau ni clé API requis.
