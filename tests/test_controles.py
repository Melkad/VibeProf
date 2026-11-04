"""Tests des contrôles automatiques, du contexte de la demande et de la typographie française."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tests" / "fixtures")]

import controles  # noqa: E402
import course_workflow as cw  # noqa: E402
import exemple_cours as ex  # noqa: E402
from contexte import Contexte, analyser_demande, consignes_contexte, duree_effective  # noqa: E402
from test_course_workflow import RAPPORT_OK, FakeClient  # noqa: E402


def structures_modifiees(**modifs):
    s = copy.deepcopy(ex.STRUCTURES)
    for chemin, valeur in modifs.items():
        nom, *cles = chemin.split("__")
        cible = s[nom]
        for c in cles[:-1]:
            cible = cible[int(c)] if c.isdigit() else cible[c]
        dernier = cles[-1]
        cible[int(dernier) if dernier.isdigit() else dernier] = valeur
    return s


def codes(liste, gravite=None):
    return sorted({(c.code, c.agent) for c in liste if gravite in (None, c.gravite)})


class ControlesTests(unittest.TestCase):
    def test_exemple_conforme(self):
        self.assertEqual(controles.bloquants(controles.verifier(ex.STRUCTURES, ex.CONTEXTE)), [])

    def test_duree(self):
        s = structures_modifiees(**{"3_deroule__etapes__0__duree_min": 25})
        self.assertIn(("duree", 3), codes(controles.verifier(s, ex.CONTEXTE), "bloquant"))
        s = structures_modifiees(**{"2_cadrage__decoupage__0__duree_min": 40})
        self.assertIn(("duree", 2), codes(controles.verifier(s, ex.CONTEXTE), "bloquant"))
        # sans durée demandée, le déroulé doit suivre le cadrage
        s = structures_modifiees(**{"3_deroule__etapes__0__duree_min": 25})
        self.assertIn(("duree", 3), codes(controles.verifier(s, Contexte("seconde", "géographie", None))))

    def test_documents_prevus_et_produits(self):
        s = copy.deepcopy(ex.STRUCTURES)
        s["5_documents_eleves"]["documents"].pop()
        liste = controles.verifier(s, ex.CONTEXTE)
        self.assertIn(("documents", 5), codes(liste, "bloquant"))
        self.assertIn("Doc 3", next(c.message for c in liste if c.code == "documents"))

    def test_source_authentique_sans_url(self):
        s = structures_modifiees(**{"5_documents_eleves__documents__0__authentique": True})
        self.assertIn(("sources", 5), codes(controles.verifier(s, ex.CONTEXTE), "bloquant"))

    def test_capacites_officielles(self):
        self.assertTrue(controles.capacite_officielle("Contextualiser — situer un document"))
        self.assertTrue(controles.capacite_officielle("mener et construire une démarche géographique"))
        self.assertFalse(controles.capacite_officielle("Analyser des flux"))
        s = structures_modifiees(**{"2_cadrage__objectifs__0__capacite": "Analyser des flux"})
        self.assertIn(("capacites", 2), codes(controles.verifier(s, ex.CONTEXTE), "bloquant"))
        # en EMC, pas de tableau de capacités : pas de contrôle
        self.assertNotIn(("capacites", 2), codes(controles.verifier(s, Contexte("seconde", "EMC", 110))))

    def test_objectifs_evalues(self):
        s = copy.deepcopy(ex.STRUCTURES)
        for q in s["6_evaluation"]["quiz"]:
            q["objectif"] = 1
        s["6_evaluation"]["reflexion"]["objectif"] = 1
        liste = controles.verifier(s, ex.CONTEXTE)
        self.assertIn(("objectifs", 6), codes(liste, "bloquant"))
        self.assertIn("2, 3", next(c.message for c in liste if c.code == "objectifs"))

    def test_longueurs(self):
        s = structures_modifiees(**{"5_documents_eleves__documents__0__contenu": "mot " * 300})
        self.assertIn(("longueur", 5), codes(controles.verifier(s, ex.CONTEXTE), "bloquant"))
        s = structures_modifiees(**{"4_support_cours__parties__0__texte": "mot " * 1200})
        self.assertIn(("longueur", 4), codes(controles.verifier(s, ex.CONTEXTE), "bloquant"))

    def test_quiz(self):
        s = structures_modifiees(**{"6_evaluation__quiz__0__reponse": "Autre chose"})
        self.assertIn(("quiz", 6), codes(controles.verifier(s, ex.CONTEXTE), "alerte"))

    def test_verifications_et_corrections(self):
        s = structures_modifiees(**{"3_deroule__etapes__0__duree_min": 25})
        liste = controles.verifier(s, ex.CONTEXTE)
        verifs = controles.verifications(liste, s)
        self.assertFalse(verifs["duree_totale_respectee"])
        self.assertTrue(verifs["documents_coherents"])
        self.assertIn(3, controles.corrections(liste))


class ContexteTests(unittest.TestCase):
    def test_duree_effective(self):
        self.assertEqual(duree_effective("2 h"), 110)
        self.assertEqual(duree_effective("2h, TD"), 110)
        self.assertEqual(duree_effective("1 h 30"), 85)
        self.assertEqual(duree_effective("55 min"), 55)
        self.assertIsNone(duree_effective("sans durée"))

    def test_analyser_demande(self):
        c = analyser_demande(ex.DEMANDE)
        self.assertEqual((c.classe, c.discipline, c.duree_min), ("seconde", "géographie", 110))
        c = analyser_demande("Terminale bac pro, EMC, le débat démocratique, 55 min")
        self.assertEqual((c.classe, c.discipline, c.duree_min), ("terminale", "EMC", 55))
        c = analyser_demande("CAP, histoire-géographie, 1 h")
        self.assertEqual((c.classe, c.discipline), ("CAP", None))

    def test_consignes(self):
        texte = consignes_contexte(Contexte("CAP", "histoire", 55))
        self.assertIn("Durée effective de la séance : 55 minutes", texte)
        self.assertIn("15 mots au maximum", texte)


class TypographieTests(unittest.TestCase):
    def test_typographie_francaise(self):
        t = cw.typographie_fr('Pourquoi ? Voir "Doc 1" ; source: https://a.fr/x:y?z=1 à 10:30')
        self.assertEqual(t, "Pourquoi ? Voir « Doc 1 » ; source : https://a.fr/x:y?z=1 à 10:30")


class BoucleCorrectionTests(unittest.TestCase):
    def setUp(self):
        cw.ROUTEUR.reset()

    def test_controle_bloquant_corrige_automatiquement(self):
        """Un déroulé à la durée fausse est renvoyé à l'agent 3 avec le message du contrôle, même si le
        relecteur est satisfait ; la séance n'est livrée qu'une fois le contrôle levé."""
        mauvais = structures_modifiees(**{"3_deroule__etapes__0__duree_min": 25})
        client = FakeClient(rapports=[RAPPORT_OK, RAPPORT_OK], structures=mauvais)
        original = client._complete

        def complete(**kw):
            if kw["messages"][0]["content"] == cw.PROMPT_CONCEPTION and "CORRECTIONS DEMANDÉES" in \
                    kw["messages"][1]["content"]:
                client.structures["3_deroule"] = copy.deepcopy(ex.STRUCTURES["3_deroule"])
            return original(**kw)

        client.chat.complete = complete
        with tempfile.TemporaryDirectory() as d:
            res = cw.generer_cours(client, ex.DEMANDE, d, max_relectures=3)
            data = json.loads((Path(d) / "cours_final.json").read_text(encoding="utf-8"))
        r1, r2 = res["rapports"]
        self.assertEqual(r1["livraison"], "non")  # relecteur à 4,4/5 mais contrôle bloquant
        self.assertFalse(r1["verifications"]["duree_totale_respectee"])
        self.assertIn("125 min au lieu de 110 min", r1["corrections"][0]["consignes"][0])
        self.assertEqual(r2["livraison"], "oui")
        self.assertTrue(res["livre"])
        relecture = [c for c in client.calls if c[1] == cw.PROMPT_RELECTEUR][0][2]
        self.assertIn("## Contrôles automatiques", relecture)
        self.assertIn("[bloquant] agent 3", relecture)
        self.assertEqual(data["dossier"]["_structures"]["3_deroule"], ex.STRUCTURES["3_deroule"])


if __name__ == "__main__":
    unittest.main()
