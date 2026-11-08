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
import exemple_cours as ex  # noqa: E402
from test_course_workflow import RAPPORT_OK, FakeClient, rapport_ko  # noqa: E402

APP = str(ROOT / "app.py")
AUTRE = "Autre thème (saisie libre)"


def remplir(at, theme="La mondialisation"):
    """Thème saisi librement (choix « Autre thème »)."""
    at.selectbox(key="theme_officiel").set_value(AUTRE).run()
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
        at.selectbox(key="theme_officiel").set_value(AUTRE).run()
        at.button[0].click().run()
        self.assertIn("thème", at.error[0].value)
        remplir(at).button[0].click().run()
        self.assertIn("clé API", at.error[0].value)

    def test_themes_officiels_selon_classe_et_discipline(self):
        at = self.run_app()
        at.selectbox(key="classe").set_value("Seconde bac pro").run()
        at.radio(key="discipline").set_value("Géographie").run()
        options = at.selectbox(key="theme_officiel").options
        self.assertEqual(options, ["Des réseaux de production et d'échanges mondialisés",
                                   "Une circulation croissante mais diverse des personnes à l'échelle mondiale",
                                   AUTRE])
        at.selectbox(key="classe").set_value("Première bac pro").run()
        at.radio(key="discipline").set_value("EMC").run()
        self.assertEqual(at.selectbox(key="theme_officiel").options,
                         ["Les valeurs et les principes de la République à l'épreuve de la cohésion sociale",
                          "La République et la Nation", AUTRE])
        self.assertEqual(at.selectbox(key="duree").format_func("2 h"), "2 h (110 min de cours)")

    def test_generation_complete(self):
        client = FakeClient(rapports=[rapport_ko("agent 3"), RAPPORT_OK])
        with mock.patch.object(cw, "make_client", return_value=client):
            at = self.run_app()
            at.text_input(key="cle_api").input("cle-test")
            at.selectbox(key="classe").set_value("Seconde bac pro").run()
            at.radio(key="discipline").set_value("Géographie").run()
            at.text_input(key="specialite").input("Commerce")
            at.checkbox(key="validation_etapes").uncheck()
            at.button[0].click().run()
        self.assertFalse(at.exception, at.exception)
        demande = client.calls[1][2]  # entrée de l'agent 1
        self.assertIn("Seconde bac pro Commerce, géographie", demande)
        self.assertIn("thème : Des réseaux de production et d'échanges mondialisés, 2 h", demande)
        self.assertIn("Durée effective de la séance : 110 minutes", demande)  # contexte du formulaire
        self.assertIn("Contrôle qualité : 4.4/5 après 2 relecture(s).", [s.value for s in at.success])
        self.assertTrue(any("Contrôles automatiques" in e.label for e in at.expander))
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


    def test_validation_par_etapes(self):
        client = FakeClient(rapports=[RAPPORT_OK])
        with mock.patch.object(cw, "make_client", return_value=client):
            at = self.run_app()
            at.text_input(key="cle_api").input("cle-test")
            remplir(at).button[0].click().run()
            self.assertFalse(at.exception, at.exception)
            # pause 1 : programme et cadrage, rien d'autre n'est rédigé
            self.assertIn("Étape 1/2", at.subheader[0].value)
            self.assertEqual(client.inputs_for("3_deroule"), [])
            self.assertTrue(at.button[0].disabled)  # formulaire figé pendant la validation
            at.button(key="appliquer").click().run()
            self.assertIn("au moins une zone", at.warning[0].value)
            at.text_area(key="retour_2_cadrage_0").input("Problématique plus concrète")
            at.button(key="valider").click().run()
            self.assertIn("Appliquer mes modifications", at.warning[0].value)  # commentaire non appliqué
            self.assertEqual(at.session_state["boucle"]["etape"], 0)
            at.button(key="appliquer").click().run()
            self.assertFalse(at.exception, at.exception)
            self.assertEqual(len(client.inputs_for("2_cadrage")), 2)
            self.assertIn("Problématique plus concrète", client.inputs_for("2_cadrage")[-1])
            self.assertEqual(at.text_area(key="retour_2_cadrage_1").value, "")  # zone vidée
            self.assertTrue(any("Déjà demandé" in c.value for c in at.caption))
            # pause 2 : déroulé
            at.button(key="valider").click().run()
            self.assertIn("Étape 2/2", at.subheader[0].value)
            self.assertEqual(len(client.inputs_for("3_deroule")), 1)
            self.assertEqual(client.inputs_for("4_support_cours"), [])
            # fin : rédaction du reste, relecture, documents
            at.button(key="valider").click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertNotIn("boucle", at.session_state)
        res = at.session_state["resultat"]
        self.assertTrue(res["livre"])
        self.assertEqual(len(at.get("download_button")), 6)
        self.assertEqual(json.loads(res["json"])["dossier"]["_retours_professeur"],
                         {"2_cadrage": ["Problématique plus concrète"]})
        self.assertIn('"demande" -> "2_cadrage" [style=dashed', res["graphe"])
        self.assertFalse(at.button[0].disabled)

    def test_abandon_de_la_validation(self):
        with mock.patch.object(cw, "make_client", return_value=FakeClient()):
            at = self.run_app()
            at.text_input(key="cle_api").input("cle-test")
            remplir(at).button[0].click().run()
            at.button(key="abandonner").click().run()
        self.assertNotIn("boucle", at.session_state)
        self.assertNotIn("resultat", at.session_state)
        self.assertFalse(at.button[0].disabled)


if __name__ == "__main__":
    unittest.main()
