import json
import unittest.mock
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import course_workflow as cw  # noqa: E402
from docx import Document  # noqa: E402
from mistralai.client.errors import MistralError  # noqa: E402


def api_error(status, body):
    return MistralError("erreur API", SimpleNamespace(status_code=status, text=body, headers={}), body)


def ns(**kw):
    return SimpleNamespace(**kw)


class FakeClient:
    """Faux client Mistral : enregistre les appels et renvoie des réponses scriptées."""

    def __init__(self, rapports=None, content_as_list=False, refused_models=(), no_reasoning_models=()):
        self.calls = []
        self.refused_models = set(refused_models)
        self.no_reasoning_models = set(no_reasoning_models)
        self.models = []  # (system prompt ou nom d'agent, modèle, reasoning_effort, temperature)
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

    def _check_model(self, model, reasoning):
        if model in self.refused_models:
            raise api_error(400, f'{{"message": "Invalid model: {model}"}}')
        if reasoning and model in self.no_reasoning_models:
            raise api_error(422, '{"message": "reasoning_effort is not supported"}')

    def _complete(self, model, messages, temperature, response_format=None, reasoning_effort=None):
        system, user = messages[0]["content"], messages[1]["content"]
        assert isinstance(user, str)
        self._check_model(model, reasoning_effort)
        self.models.append((system, model, reasoning_effort, temperature))
        self.calls.append(("chat", system, user))
        if system == cw.PROMPT_RELECTEUR:
            return self._reply(json.dumps(self.rapports.pop(0)))
        agent = next(a for a in cw.AGENTS if a["prompt"] == system)
        return self._reply(f"# {agent['title']}\n\nSortie de {agent['name']}")

    def _create_agent(self, model, name, instructions, tools, completion_args):
        self._check_model(model, completion_args.get("reasoning_effort"))
        self.models.append((instructions, model, completion_args.get("reasoning_effort"),
                            completion_args["temperature"]))
        self.calls.append(("create_agent", tools))
        self.current_agent = instructions
        return ns(id="ag_1")

    def _delete_agent(self, agent_id):
        self.deleted.append(agent_id)

    def _start(self, agent_id, inputs):
        self.calls.append(("web", self.current_agent, inputs))
        if self.current_agent == cw.PROMPT_DOCUMENTS:
            return ns(outputs=[ns(type="message.output", content=[
                ns(type="text", text="Texte de Jaurès (https://gallica.bnf.fr/ark:/1) ; voir https://invente.example/x"),
                ns(type="tool_reference", title="Gallica", url="https://gallica.bnf.fr/ark:/1", tool="web_search"),
            ])])
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
        return [c[2] for c in self.calls if c[0] in ("chat", "web") and c[1] == prompt]

    def model_of(self, prompt):
        return [m for m in self.models if m[0] == prompt][-1]


RAPPORT_OK = {"score_global": 4.4, "notes": {"c1_ancrage_programme": 5, "c2_deroule": 4,
              "c3_niveau_langage": 4, "c4_coherence": 5, "c5_exactitude": 4},
              "livraison": "oui", "retour_vers": None, "consignes_correction": []}


def rapport_ko(retour):
    return {"score_global": "3,0", "notes": {k: 3 for k in RAPPORT_OK["notes"]}, "livraison": "non",
            "retour_vers": retour, "consignes_correction": ["Revoir la durée"]}


class RouteurReset(unittest.TestCase):
    def setUp(self):
        cw.ROUTEUR.reset()


class PipelineTests(RouteurReset):
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
        self.assertEqual(client.deleted, ["ag_1", "ag_1"])  # agents web 1 et 5 nettoyés
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
        self.assertEqual([c[1] for c in web], [cw.PROMPT_SOURCES, cw.PROMPT_DOCUMENTS])
        self.assertIn("Revoir la durée", web[0][2])
        self.assertEqual(len([c for c in client.calls if c[0] == "chat"]), 4)

    def test_correction_only_reruns_dependents(self):
        client = FakeClient()
        out = cw.run_pipeline(client, "demande")
        client.calls.clear()
        cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 6")))
        self.assertEqual(len(client.calls), 1)  # personne ne dépend de l'évaluation
        client.calls.clear()
        cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 4")))
        rerun = [c[1] for c in client.calls if c[0] in ("chat", "web")]
        self.assertEqual(rerun, [cw.PROMPT_REDACTION, cw.PROMPT_DOCUMENTS, cw.PROMPT_EVALUATION])

    def test_invalid_target(self):
        out = cw.run_pipeline(FakeClient(), "demande")
        for retour in (None, "null", "agent 7", "agent 0"):
            _, ok = cw.apply_correction(FakeClient(), out, cw.normalize_rapport(rapport_ko(retour)))
            self.assertFalse(ok, retour)


class ModelesTests(RouteurReset):
    def test_default_routing(self):
        client = FakeClient(rapports=[RAPPORT_OK])
        out = cw.run_pipeline(client, "demande")
        cw.run_relecture(client, out)
        principal, leger = cw.MODELES["principal"], cw.MODELES["leger"]
        self.assertEqual(client.model_of(cw.PROMPT_SOURCES)[1:], (principal, None, 0.1))
        self.assertEqual(client.model_of(cw.PROMPT_CADRAGE)[1], principal)
        self.assertEqual(client.model_of(cw.PROMPT_DOCUMENTS)[1], principal)
        self.assertEqual(client.model_of(cw.PROMPT_EVALUATION)[1], leger)
        self.assertEqual(client.model_of(cw.PROMPT_RELECTEUR)[1:], (leger, "high", 0))
        self.assertNotEqual(leger, principal)  # le relecteur ne juge pas son propre modèle
        self.assertEqual(cw.ROUTEUR.utilises["relecteur"], f"{leger} (raisonnement : high)")

    def test_env_override_per_agent(self):
        with unittest.mock.patch.dict("os.environ", {"MISTRAL_MODEL_EVALUATION": "mon-modele"}):
            client = FakeClient()
            cw.run_pipeline(client, "demande")
        self.assertEqual(client.model_of(cw.PROMPT_EVALUATION)[1], "mon-modele")

    def test_fallback_when_model_refused(self):
        principal, secours = cw.MODELES["principal"], cw.MODELES["secours"]
        client = FakeClient(refused_models=[principal])
        cw.run_pipeline(client, "demande")
        for prompt in (cw.PROMPT_SOURCES, cw.PROMPT_CADRAGE, cw.PROMPT_DOCUMENTS):
            self.assertEqual(client.model_of(prompt)[1], secours)
        self.assertEqual(cw.ROUTEUR.substitutions, {principal: secours})
        # la substitution est mémorisée : un seul refus, pas un par agent
        self.assertEqual(sum(1 for m in client.models if m[1] == principal), 0)
        self.assertEqual(client.model_of(cw.PROMPT_EVALUATION)[1], cw.MODELES["leger"])

    def test_reasoning_dropped_if_unsupported(self):
        client = FakeClient(rapports=[RAPPORT_OK], no_reasoning_models=[cw.MODELES["leger"]])
        out = cw.run_pipeline(client, "demande")
        rapport, _ = cw.run_relecture(client, out)
        self.assertEqual(rapport["livraison"], "oui")
        self.assertEqual(client.model_of(cw.PROMPT_RELECTEUR)[1:3], (cw.MODELES["leger"], None))

    def test_other_errors_are_raised(self):
        client = FakeClient()
        client.chat.complete = lambda **kw: (_ for _ in ()).throw(api_error(401, "Unauthorized"))
        with self.assertRaises(MistralError):
            cw.call_agent(client, cw.AGENTS_BY_NAME["2_cadrage"], "x")

    def test_documents_sources_not_restricted_to_official(self):
        out = cw.run_pipeline(FakeClient(), "demande")
        docs = out["5_documents_eleves"]
        consultees, _, a_verifier = docs.partition("URL citées non issues de la recherche")
        self.assertIn("https://gallica.bnf.fr/ark:/1", consultees.split("Sources consultées")[1])
        self.assertIn("invente.example", a_verifier)
        self.assertNotIn("gallica", a_verifier)


class PromptsTests(unittest.TestCase):
    PROMPTS = [a["prompt"] for a in cw.AGENTS] + [cw.PROMPT_RELECTEUR]

    def test_contexte_commun_partout(self):
        for prompt in self.PROMPTS:
            self.assertTrue(prompt.startswith(cw.CONTEXTE_COMMUN))

    def test_vocabulaire_institutionnel(self):
        for prompt in self.PROMPTS:
            specifique = prompt[len(cw.CONTEXTE_COMMUN):]
            self.assertNotIn("socle", specifique.lower())
        for mot in ("notions et mots-clés", "capacités", "repères"):
            self.assertIn(mot, cw.PROMPT_SOURCES)

    def test_parties_eleve_professeur(self):
        for prompt in (cw.PROMPT_DOCUMENTS, cw.PROMPT_EVALUATION):
            self.assertIn("## Partie élève", prompt)
            self.assertIn("## Partie professeur", prompt)

    def test_numerotation_documents_partagee(self):
        self.assertIn("## Documents nécessaires", cw.PROMPT_CONCEPTION)
        self.assertIn("Documents nécessaires", cw.PROMPT_DOCUMENTS)
        self.assertIn("Total", cw.PROMPT_CONCEPTION)

    def test_relecteur_connait_ses_cles(self):
        for key in list(cw.VERIFICATIONS) + list(cw.CRITERES):
            self.assertIn(key, cw.PROMPT_RELECTEUR)


class CorrectionsMultiplesTests(RouteurReset):
    def test_normalize_corrections(self):
        r = cw.normalize_rapport({"notes": {"a": 3}, "corrections": [
            {"agent": 5, "consignes": ["doc 2 manquant"]},
            {"agent": "agent 3", "consignes": "lister le doc 2"},
            {"agent": 9, "consignes": ["ignoré"]},
            {"agent": 3, "consignes": ["total faux"]},
        ]})
        self.assertEqual(r["corrections"], [
            {"agent": 3, "consignes": ["lister le doc 2", "total faux"]},
            {"agent": 5, "consignes": ["doc 2 manquant"]},
        ])

    def test_each_agent_regenerated_once_in_order(self):
        client = FakeClient()
        out = cw.run_pipeline(client, "demande")
        client.calls.clear()
        rapport = cw.normalize_rapport({"notes": {"a": 3}, "corrections": [
            {"agent": 5, "consignes": ["CONSIGNE-DOCS"]}, {"agent": 3, "consignes": ["CONSIGNE-DEROULE"]}]})
        _, ok = cw.apply_correction(client, out, rapport)
        self.assertTrue(ok)
        rerun = [c for c in client.calls if c[0] in ("chat", "web")]
        self.assertEqual([c[1] for c in rerun],
                         [cw.PROMPT_CONCEPTION, cw.PROMPT_REDACTION, cw.PROMPT_DOCUMENTS, cw.PROMPT_EVALUATION])
        self.assertIn("CONSIGNE-DEROULE", rerun[0][2])
        self.assertNotIn("CONSIGNE", rerun[1][2].split("---")[-1])  # agent 4 : simple mise à jour
        self.assertIn("CONSIGNE-DOCS", rerun[2][2])


class RapportTests(RouteurReset):
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


class DocxTests(RouteurReset):
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
        self.assertIn("Modèles utilisés", textes)
        self.assertTrue(any("Renvoi vers l'agent 3 (Déroulé de séance)" in t for t in textes))
        cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        self.assertIn(cw.MODELES["leger"], cells)


if __name__ == "__main__":
    unittest.main()
