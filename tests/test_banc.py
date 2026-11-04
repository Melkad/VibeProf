"""Test du banc d'évaluation en mode simulation (aucun appel API)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "evaluation")]

import banc  # noqa: E402


class BancTests(unittest.TestCase):
    def test_cas_valides(self):
        cas = json.loads(banc.CAS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cas), 12)
        self.assertEqual(len({c["id"] for c in cas}), len(cas))
        self.assertEqual({c["classe"] for c in cas}, {"CAP", "seconde", "première", "terminale"})
        self.assertEqual({c["discipline"] for c in cas}, {"histoire", "géographie", "EMC"})
        from contexte import THEMES_OFFICIELS
        for c in cas:  # chaque cas porte sur un thème officiel en vigueur
            self.assertIn(c["theme"], THEMES_OFFICIELS[(c["classe"], c["discipline"])], c["id"])

    def test_simulation(self):
        cas = [c for c in json.loads(banc.CAS.read_text(encoding="utf-8")) if c["id"] == "2de-geo-1"]
        with tempfile.TemporaryDirectory() as d:
            dossier, lignes = banc.lancer(cas, d, banc.client_simulation, 2, journal=lambda m: None)
            rapport = (dossier / "rapport.md").read_text(encoding="utf-8")
            self.assertTrue((dossier / "2de-geo-1" / "1_fiche_professeur.docx").exists())
        self.assertTrue(lignes[0]["livre"])
        self.assertEqual(lignes[0]["bloquants"], [])
        self.assertIn("| 2de-geo-1 | seconde | géographie | oui | 4.4 |", rapport)


if __name__ == "__main__":
    unittest.main()
