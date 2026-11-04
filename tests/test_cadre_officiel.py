"""Tests du cadre officiel injecté dans les consignes des agents."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import course_workflow as cw  # noqa: E402

FICHE = """---
agents: CADRAGE, evaluation
statut: vérifié
sources: BO test
---
## Titre
Texte transmis.
<!-- consigne interne
sur deux lignes -->
Suite transmise.
"""


class CadreOfficielTests(unittest.TestCase):
    def lire(self, fichiers):
        with tempfile.TemporaryDirectory() as d:
            for nom, texte in fichiers.items():
                (Path(d) / nom).write_text(texte, encoding="utf-8")
            return cw.lire_cadre_officiel(d)

    def test_lecture_et_commentaires(self):
        fiches = self.lire({"01_test.md": FICHE, "README.md": "ignoré"})
        self.assertEqual(len(fiches), 1)
        f = fiches[0]
        self.assertEqual(f["agents"], {"CADRAGE", "EVALUATION"})
        self.assertEqual((f["statut"], f["sources"]), ("vérifié", "BO test"))
        self.assertIn("Texte transmis.", f["corps"])
        self.assertIn("Suite transmise.", f["corps"])
        self.assertNotIn("consigne interne", f["corps"])

    def test_bloc_par_agent(self):
        fiches = self.lire({"01_test.md": FICHE, "02_vide.md": "---\nagents: CADRAGE\n---\n<!-- rien -->\n"})
        bloc = cw.cadre_officiel("cadrage", fiches)
        self.assertIn("CADRE OFFICIEL DE RÉFÉRENCE", bloc)
        self.assertIn("[Fiche 01_test.md — statut : vérifié — sources : BO test]", bloc)
        self.assertNotIn("02_vide", bloc)  # fiche sans contenu transmis : ignorée
        self.assertEqual(cw.cadre_officiel("SUPPORT", fiches), "")

    def test_dossier_absent(self):
        self.assertEqual(cw.lire_cadre_officiel("/dossier/inexistant"), [])

    def test_fiches_du_depot(self):
        """Les fiches livrées sont lues et chaque agent en reçoit au moins une."""
        self.assertGreaterEqual(len(cw.CADRE_OFFICIEL), 5)
        for f in cw.CADRE_OFFICIEL:
            self.assertIn(f["statut"], ("vérifié", "partiel", "à compléter"), f["fichier"])
            self.assertTrue(f["sources"], f["fichier"])
            self.assertNotIn("socle", f["corps"].lower(), f["fichier"])
        for cfg in cw.AGENTS + [cw.RELECTEUR]:
            self.assertIn("CADRE OFFICIEL DE RÉFÉRENCE", cfg["prompt"], cfg["key"])

    def test_contenu_verifie_livre(self):
        fiches = {f["fichier"]: f for f in cw.CADRE_OFFICIEL}
        verifiees = [n for n, f in fiches.items() if f["statut"] == "vérifié"]
        self.assertGreaterEqual(len(verifiees), 5)
        self.assertIn("BO n° 24 du 13 juin 2024", fiches["01_sources_officielles.md"]["corps"])
        self.assertIn("Contextualiser", fiches["03_capacites.md"]["corps"])
        self.assertIn("La vie démocratique : débat, délibération et prise de décision", fiches["06_emc.md"]["corps"])
        self.assertIn("EMC", cw.PROMPT_SOURCES)  # consigne propre à la structure du programme d'EMC
        self.assertNotIn("06_emc.md", cw.PROMPT_EVALUATION)  # fiche transmise seulement pour une séance d'EMC
        from contexte import Contexte
        self.assertIn("06_emc.md", cw.cadre_contextuel("EVALUATION", Contexte("terminale", "EMC", 55)))
        self.assertNotIn("06_emc.md", cw.cadre_contextuel("EVALUATION", Contexte("terminale", "histoire", 55)))

    def test_consignes_de_conformite(self):
        self.assertIn("## Recommandations officielles de mise en œuvre", cw.PROMPT_SOURCES)
        self.assertIn("## Attendus de l'examen", cw.PROMPT_SOURCES)
        self.assertIn("en vigueur", cw.PROMPT_SOURCES)
        self.assertIn("conformite", cw.PROMPT_CONCEPTION)
        self.assertIn("capacité du programme", cw.PROMPT_EVALUATION)
        self.assertIn("1_referentiel_officiel", cw.AGENTS_BY_NAME["3_deroule"]["inputs"])
        self.assertIn("1_referentiel_officiel", cw.AGENTS_BY_NAME["6_evaluation"]["inputs"])


if __name__ == "__main__":
    unittest.main()
