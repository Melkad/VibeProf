"""Tests de l'interface Streamlit (AppTest, sans navigateur ni appel API)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tests" / "fixtures")]

from streamlit.testing.v1 import AppTest  # noqa: E402

import course_workflow as cw  # noqa: E402
from test_course_workflow import RAPPORT_OK, FakeClient, rapport_ko  # noqa: E402

APP = str(ROOT / "app.py")


def remplir(at, theme="La mondialisation"):
    at.text_input(key="theme").input(theme)
    return at


class AppTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict("os.environ", {}, clear=False)
        self.env.start()
        for var in ("MISTRAL_API_KEY", "VIBEPROF_CODE_ACCES"):
            __import__("os").environ.pop(var, None)
        self.addCleanup(self.env.stop)

    def run_app(self):
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_page_initiale(self):
        at = self.run_app()
        self.assertEqual(at.title[0].value, "📚 VibeProf")
        self.assertEqual(at.text_input(key="cle_api").label, "Clé API Mistral")
        self.assertEqual(at.selectbox[0].value, "Terminale bac pro")

    def test_theme_et_cle_obligatoires(self):
        at = self.run_app()
        at.button[0].click().run()
        self.assertIn("thème", at.error[0].value)
        remplir(at).button[0].click().run()
        self.assertIn("clé API", at.error[0].value)

    def test_generation_complete(self):
        client = FakeClient(rapports=[rapport_ko("agent 3"), RAPPORT_OK])
        with mock.patch.object(cw, "make_client", return_value=client):
            at = self.run_app()
            at.text_input(key="cle_api").input("cle-test")
            remplir(at, "La France dans la mondialisation")
            at.text_input(key="specialite").input("Commerce")
            at.button[0].click().run()
        self.assertFalse(at.exception, at.exception)
        demande = client.calls[1][2]  # entrée de l'agent 1
        self.assertIn("Terminale bac pro Commerce, histoire", demande)
        self.assertIn("thème : La France dans la mondialisation, 2 h", demande)
        self.assertIn("Contrôle qualité : 4.4/5 après 2 relecture(s).", [s.value for s in at.success])
        res = at.session_state["resultat"]
        self.assertEqual(sorted(res["fichiers"]), ["1_fiche_professeur.docx", "2_cours_eleve.docx",
                                                   "3_documents_eleves.docx", "4_evaluation_eleve.docx",
                                                   "cours_complet.docx"])
        self.assertEqual(len(at.get("download_button")), 6)  # zip + 5 documents
        self.assertTrue(json.loads(res["json"])["livre"])
        self.assertIn('"relecteur" -> "3_deroule" [style=dashed', res["graphe"])  # parcours du workflow

    def test_echec_affiche_une_erreur(self):
        client = FakeClient()
        client.chat.complete = mock.Mock(side_effect=RuntimeError("clé refusée"))
        with mock.patch.object(cw, "make_client", return_value=client):
            at = self.run_app()
            at.text_input(key="cle_api").input("mauvaise-cle")
            remplir(at).button[0].click().run()
        self.assertIn("clé refusée", at.error[0].value)
        self.assertNotIn("resultat", at.session_state)

    def test_code_acces(self):
        __import__("os").environ["VIBEPROF_CODE_ACCES"] = "secret"
        at = self.run_app()
        self.assertEqual(len(at.button), 0)
        at.text_input(key="code_acces").input("faux").run()
        self.assertEqual(at.error[0].value, "Code incorrect.")
        at.text_input(key="code_acces").input("secret").run()
        self.assertEqual(at.title[0].value, "📚 VibeProf")
        self.assertEqual(len(at.button), 1)

    def test_cle_serveur(self):
        __import__("os").environ["MISTRAL_API_KEY"] = "cle-serveur"
        at = self.run_app()
        self.assertIn("configurée sur le serveur", at.success[0].value)
        self.assertNotIn("Clé API Mistral", [t.label for t in at.text_input])

    def test_construire_demande(self):
        sys.modules.pop("app", None)
        with mock.patch("streamlit.set_page_config"), mock.patch.dict(sys.modules):
            src = Path(APP).read_text(encoding="utf-8").replace("\nmain()\n", "\n")
            ns = {"__name__": "app_sans_main"}
            exec(compile(src, APP, "exec"), ns)
        d = ns["construire_demande"]("CAP 1re année", " ", "EMC", " La laïcité ", "55 min", "Cours dialogué", "")
        self.assertEqual(d, "CAP 1re année, emc, thème : La laïcité, 55 min, Cours dialogué")
        d = ns["construire_demande"]("Seconde bac pro", "MELEC", "Histoire", "X", "1 h", "TD", "élèves allophones")
        self.assertTrue(d.endswith(". Précisions du professeur : élèves allophones"))


if __name__ == "__main__":
    unittest.main()
