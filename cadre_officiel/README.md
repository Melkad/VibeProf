# Cadre officiel de référence

Ces fiches sont injectées dans les consignes des agents de VibeProf pour que les cours suivent au plus près les
textes officiels de l'histoire-géographie et de l'EMC en lycée professionnel.

- Chaque fiche commence par un en-tête :
  - `agents` : les agents qui la reçoivent (REFERENTIEL, CADRAGE, DEROULE, SUPPORT, DOCUMENTS, EVALUATION, RELECTEUR) ;
  - `statut` : `vérifié` (relu dans le texte officiel), `partiel` ou `à compléter` ;
  - `sources` : les textes d'où viennent les informations ;
  - `classes` / `disciplines` (facultatifs) : la fiche n'est transmise que pour ces classes (CAP, seconde, première,
    terminale) ou ces disciplines (histoire, géographie, EMC). Sans filtre, elle est toujours transmise.
- Les commentaires `<!-- … -->` ne sont **pas** transmis aux agents : ils servent de consignes pour compléter la fiche.
- Seul ce qui est écrit en clair est transmis. N'écrivez ici que ce qui figure dans un texte officiel, avec sa source.

Après modification d'une fiche, relancez simplement VibeProf : les fiches sont relues à chaque démarrage.

| Fiche | Contenu | Transmise | Statut |
|---|---|---|---|
| `01_sources_officielles.md` | textes en vigueur et URL (HG, EMC 2024, ressources, sujet 2026) | toujours | vérifié |
| `02_structure_programmes.md` | organisation des programmes, thèmes par classe | toujours | vérifié |
| `03_capacites.md` | tableau officiel des capacités | toujours | vérifié |
| `04_examens.md` | épreuve écrite (sujet 2026) et oral de contrôle | toujours | partiel |
| `05_mise_en_oeuvre.md` | progressivité, repères et notions, liens | toujours | vérifié |
| `06_emc.md` | programme d'EMC 2024 : thèmes et méthodes | séances d'EMC | vérifié |
| `07_classe_*.md` | attendus propres à la classe (analyse de documents, croquis, récit) | selon la classe | vérifié (CAP : partiel) |
| `08_discipline_*.md` | repères et capacités propres à l'histoire ou à la géographie | selon la discipline | vérifié |

Dernière vérification : 04/11/2026, à partir des documents officiels téléchargés (Eduscol, education.gouv.fr).
