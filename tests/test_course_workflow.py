import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import course_workflow as cw  # noqa: E402
from docx import Document  # noqa: E402


def ns(**kw):
    return SimpleNamespace(**kw)


class FakeClient:
    """Faux client Mistral : enregistre les appels et renvoie des réponses scriptées."""

    def __init__(self, rapports=None, content_as_list=False):
        self.calls = []
        self.rapports = list(rapports or [])
        self.content_as_list = content_as_list
        self.deleted = []
        self.chat = ns(complete=self._complete)
        self.beta = ns(
            agents=ns(create=self._create_agent, delete=self._delete_agent),
            conversations=ns(start=self._start),
        )

    def _reply(self, text):
        content = [ns(type="thinking", thinking=[]), ns(type="text", text=text)] if self.content_as_list else text
        return ns(choices=[ns(message=ns(content=content))])

    def _complete(self, model, messages, temperature, response_format=None):
        system, user = messages[0]["content"], messages[1]["content"]
        assert isinstance(user, str)
        self.calls.append(("chat", system, user))
        if system == cw.PROMPT_RELECTEUR:
            return self._reply(json.dumps(self.rapports.pop(0)))
        agent = next(a for a in cw.AGENTS if a["prompt"] == system)
        return self._reply(f"# {agent['title']}\n\nSortie de {agent['name']}")

    def _create_agent(self, **kw):
        self.calls.append(("create_agent", kw["tools"]))
        return ns(id="ag_1")

    def _delete_agent(self, agent_id):
        self.deleted.append(agent_id)

    def _start(self, agent_id, inputs):
        self.calls.append(("web", inputs))
        return ns(outputs=[
            ns(type="tool.execution"),
            ns(type="message.output", content=[
                ns(type="text", text="Programme de terminale. Voir aussi https://blog.exemple.com/cours."),
                ns(type="tool_reference", title="Programme HG bac pro",
                   url="https://eduscol.education.fr/1234/programme", tool="web_search"),
                ns(type="tool_reference", title="Wikipédia", url="https://fr.wikipedia.org/wiki/X",
                   tool="web_search"),
            ]),
        ])

    def inputs_for(self, agent_name):
        prompt = cw.AGENTS_BY_NAME[agent_name]["prompt"]
        return [u for kind, s, u in (c for c in self.calls if c[0] == "chat") if s == prompt]


RAPPORT_OK = {"score_global": 4.4, "notes": {"c1_ancrage_programme": 5, "c2_deroule": 4,
              "c3_niveau_langage": 4, "c4_coherence": 5, "c5_exactitude": 4},
              "livraison": "oui", "retour_vers": None, "consignes_correction": []}


def rapport_ko(retour):
    return {"score_global": "3,0", "notes": {k: 3 for k in RAPPORT_OK["notes"]}, "livraison": "non",
            "retour_vers": retour, "consignes_correction": ["Revoir la durée"]}


class PipelineTests(unittest.TestCase):
    def test_agents_receive_all_declared_inputs(self):
        client = FakeClient()
        out = cw.run_pipeline(client, "Terminale bac pro, mondialisation, 2h")
        cadrage_in = client.inputs_for("2_cadrage")[0]
        self.assertIn("Terminale bac pro, mondialisation, 2h", cadrage_in)
        self.assertIn("eduscol.education.fr/1234", cadrage_in)
        eval_in = client.inputs_for("6_evaluation")[0]
        self.assertIn("Sortie de 2_cadrage", eval_in)
        self.assertIn("Sortie de 4_support_cours", eval_in)
        self.assertNotIn("Sortie de 5_documents_eleves", eval_in)
        docs_in = client.inputs_for("5_documents_eleves")[0]
        for n in ("2_cadrage", "3_deroule", "4_support_cours"):
            self.assertIn(f"Sortie de {n}", docs_in)
        self.assertEqual(client.deleted, ["ag_1"])
        self.assertTrue(all(isinstance(v, str) for v in out.values()))

    def test_list_content_is_normalized(self):
        out = cw.run_pipeline(FakeClient(content_as_list=True), "demande")
        self.assertEqual(out["3_deroule"], "# Déroulé de séance\n\nSortie de 3_deroule")

    def test_sources_are_kept_and_filtered(self):
        out = cw.run_pipeline(FakeClient(), "demande")
        ref = out["1_referentiel_officiel"]
        officielles, _, ecartees = ref.partition("Sources non officielles")
        self.assertIn("https://eduscol.education.fr/1234/programme", officielles.split("Sources officielles consultées")[1])
        self.assertIn("fr.wikipedia.org", ecartees)
        self.assertIn("blog.exemple.com", ecartees)

    def test_is_official_url(self):
        self.assertTrue(cw.is_official_url("https://eduscol.education.fr/x"))
        self.assertTrue(cw.is_official_url("https://www.education.gouv.fr/x"))
        self.assertFalse(cw.is_official_url("https://education.gouv.fr.evil.com/x"))
        self.assertFalse(cw.is_official_url("https://faux-education.gouv.fr/x"))

    def test_correction_agent1_uses_web_and_reruns_everything(self):
        client = FakeClient()
        out = cw.run_pipeline(client, "demande")
        client.calls.clear()
        _, ok = cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 1")))
        self.assertTrue(ok)
        web = [c for c in client.calls if c[0] == "web"]
        self.assertEqual(len(web), 1)
        self.assertIn("Revoir la durée", web[0][1])
        self.assertEqual(len([c for c in client.calls if c[0] == "chat"]), 5)

    def test_correction_only_reruns_dependents(self):
        client = FakeClient()
        out = cw.run_pipeline(client, "demande")
        client.calls.clear()
        cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 5")))
        self.assertEqual(len(client.calls), 1)  # personne ne dépend des documents élèves
        client.calls.clear()
        cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 4")))
        rerun = [s for _, s, _ in client.calls]
        self.assertEqual(rerun, [cw.PROMPT_REDACTION, cw.PROMPT_DOCUMENTS, cw.PROMPT_EVALUATION])

    def test_invalid_target(self):
        out = cw.run_pipeline(FakeClient(), "demande")
        for retour in (None, "null", "agent 7", "agent 0"):
            _, ok = cw.apply_correction(FakeClient(), out, cw.normalize_rapport(rapport_ko(retour)))
            self.assertFalse(ok, retour)


class RapportTests(unittest.TestCase):
    def test_normalize_recomputes_score(self):
        r = cw.normalize_rapport({"score_global": None, "notes": {"a": 4, "b": "5"}, "livraison": "non"})
        self.assertEqual(r["score_global"], 4.5)
        self.assertEqual(r["livraison"], "oui")

    def test_normalize_missing_everything(self):
        r = cw.normalize_rapport({})
        self.assertIsNone(r["score_global"])
        self.assertEqual(r["livraison"], "non")

    def test_extract_json_variants(self):
        self.assertEqual(cw.extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(cw.extract_json('Voici : {"a": 1} fin'), {"a": 1})
        with self.assertRaises(ValueError):
            cw.extract_json("pas de json")

    def test_relecture_retries_on_bad_json(self):
        client = FakeClient()
        replies = iter(["pas du json", json.dumps(RAPPORT_OK)])
        client.chat.complete = lambda **kw: ns(choices=[ns(message=ns(content=next(replies)))])
        out = cw.run_pipeline(FakeClient(), "demande")
        rapport, _ = cw.run_relecture(client, out)
        self.assertEqual(rapport["livraison"], "oui")


class DocxTests(unittest.TestCase):
    def test_markdown_rendering(self):
        md = ("# Titre\n## Sous-titre\nTexte **gras** et *italique*.\n\n- un\n- deux\n  - sous-point\n"
              "1. premier\n2. second\n\n| Date | Événement |\n|---|---|\n| 1945 | Fin de la guerre |\n")
        doc = Document()
        cw.add_markdown(doc, md)
        styles = [p.style.name for p in doc.paragraphs]
        self.assertEqual(styles.count("List Bullet"), 2)
        self.assertEqual(styles.count("List Bullet 2"), 1)
        self.assertEqual(styles.count("List Number"), 2)
        self.assertIn("Heading 2", styles)
        self.assertIn("Heading 3", styles)
        texte = next(p for p in doc.paragraphs if "gras" in p.text)
        self.assertEqual(texte.text, "Texte gras et italique.")
        self.assertTrue(any(r.bold and r.text == "gras" for r in texte.runs))
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual(doc.tables[0].cell(1, 1).text, "Fin de la guerre")
        self.assertFalse(any("**" in p.text or p.text.startswith("- ") for p in doc.paragraphs))

    def test_build_docx_with_warning(self):
        out = cw.run_pipeline(FakeClient(), "demande")
        rapports = [cw.normalize_rapport(rapport_ko("agent 3"))]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.docx"
            cw.build_docx(path, "demande", out, rapports, livre=False)
            doc = Document(path)
        textes = [p.text for p in doc.paragraphs]
        self.assertTrue(any("ATTENTION" in t for t in textes))
        self.assertIn("Référentiel officiel", textes)
        self.assertNotIn("1_referentiel_officiel", textes)


if __name__ == "__main__":
    unittest.main()
