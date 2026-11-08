"""Tests du graphe d'avancement (événements du moteur -> état -> DOT)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import course_workflow as cw  # noqa: E402
from suivi_workflow import SuiviWorkflow, aretes_principales  # noqa: E402
from test_course_workflow import RAPPORT_OK, FakeClient, rapport_ko  # noqa: E402


class SuiviTests(unittest.TestCase):
    def test_aretes_sans_redondance(self):
        self.assertEqual(aretes_principales(), [
            ("1_referentiel_officiel", "2_cadrage"), ("2_cadrage", "3_deroule"), ("3_deroule", "4_support_cours"),
            ("4_support_cours", "5_documents_eleves"), ("4_support_cours", "6_evaluation")])

    def test_etats_et_durees(self):
        t = [0.0]
        s = SuiviWorkflow(horloge=lambda: t[0])
        s.recevoir("2_cadrage", "en_cours")
        self.assertIn("⏳ en cours", s.to_dot())
        t[0] = 75
        s.recevoir("2_cadrage", "termine")
        self.assertEqual(s.etapes["2_cadrage"]["etat"], "termine")
        self.assertIn("✓ 1 min 15 s", s.to_dot())
        s.recevoir("2_cadrage", "correction")
        t[0] = 80
        s.recevoir("2_cadrage", "termine")
        self.assertIn("✓ 1 min 20 s · 2 passages", s.to_dot())

    def test_erreur(self):
        s = SuiviWorkflow()
        s.recevoir("3_deroule", "en_cours")
        s.marquer_erreur("boom")
        self.assertEqual(s.etapes["3_deroule"]["etat"], "erreur")
        self.assertEqual(s.message_erreur, "boom")
        self.assertIn("✗ erreur", s.to_dot())

    def test_evenement_inconnu_ignore(self):
        s = SuiviWorkflow()
        s.recevoir("agent_fantome", "en_cours")
        self.assertNotIn("agent_fantome", s.to_dot())

    def test_dot_echappe_le_html(self):
        s = SuiviWorkflow()
        s.recevoir("relecteur", "termine", {"iteration": 1, "score": "<b>", "livre": False, "corrections": []})
        self.assertIn("&lt;b&gt;/5", s.to_dot())

    def test_workflow_complet_branche_sur_le_moteur(self):
        """Événements réellement émis par generer_cours, avec une correction vers l'agent 3."""
        import tempfile
        appels = []
        suivi = SuiviWorkflow(on_change=lambda s: appels.append(1))
        cw.configurer_session(evenements=suivi.recevoir)
        try:
            client = FakeClient(rapports=[rapport_ko("agent 3"), RAPPORT_OK])
            with tempfile.TemporaryDirectory() as d:
                cw.generer_cours(client, "demande", d, max_relectures=3)
        finally:
            cw.configurer_session()
        etats = {n: e["etat"] for n, e in suivi.etapes.items()}
        self.assertEqual(set(etats.values()), {"termine"})
        self.assertEqual(suivi.etapes["2_cadrage"]["passages"], 1)
        for nom in ("3_deroule", "4_support_cours", "5_documents_eleves", "6_evaluation"):
            self.assertEqual(suivi.etapes[nom]["passages"], 2, nom)
        self.assertEqual(suivi.etapes["relecteur"]["passages"], 2)
        self.assertEqual(suivi.renvois, [(1, 3)])
        dot = suivi.to_dot()
        self.assertIn('"relecteur" -> "3_deroule" [style=dashed', dot)
        self.assertIn("4.4/5 — livrable", dot)
        self.assertGreater(len(appels), 20)

    def test_sans_suivi_rien_ne_change(self):
        cw.configurer_session()
        cw.evenement("2_cadrage", "en_cours")  # aucun rappel branché : sans effet


    def test_attente_et_retours_du_professeur(self):
        suivi = SuiviWorkflow()
        cw.configurer_session(evenements=suivi.recevoir)
        try:
            cw.evenement("2_cadrage", "termine")
            cw.mettre_en_attente(0)
            self.assertEqual(suivi.etapes["2_cadrage"]["etat"], "attente_prof")
            self.assertIn("à valider par le professeur", suivi.to_dot())
            cw.evenement("demande", "retour_prof", agent=2)
            cw.evenement("demande", "retour_prof", agent=2)
            self.assertEqual(suivi.etapes["demande"]["etat"], "termine")
            dot = suivi.to_dot()
            self.assertIn('"demande" -> "2_cadrage" [style=dashed, color="#7030A0"', dot)
            self.assertIn("retour prof ×2", dot)
            cw.valider_etape(0)
            self.assertEqual(suivi.etapes["2_cadrage"]["etat"], "termine")
        finally:
            cw.configurer_session()


if __name__ == "__main__":
    unittest.main()
