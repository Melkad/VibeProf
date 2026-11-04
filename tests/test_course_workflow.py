import json
import re
import unittest.mock
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

import copy  # noqa: E402

import course_workflow as cw  # noqa: E402
import exemple_cours as ex  # noqa: E402
from docx import Document  # noqa: E402
from mistralai.client.errors import MistralError  # noqa: E402


def api_error(status, body):
    return MistralError("erreur API", SimpleNamespace(status_code=status, text=body, headers={}), body)


def ns(**kw):
    return SimpleNamespace(**kw)


class FakeClient:
    """Faux client Mistral : enregistre les appels et renvoie des réponses scriptées.

    Les agents rendent les productions structurées de l'exemple (tests/fixtures/exemple_cours.py), modifiables
    par `structures` ; `invalides` : noms d'agents dont la première réponse n'est pas conforme au schéma."""

    def __init__(self, rapports=None, content_as_list=False, refused_models=(), no_reasoning_models=(),
                 structures=None, invalides=(), references=None):
        self.calls = []
        self.refused_models = set(refused_models)
        self.no_reasoning_models = set(no_reasoning_models)
        self.models = []  # (system prompt ou instructions, modèle, reasoning_effort, temperature)
        self.rapports = list(rapports or [])
        self.content_as_list = content_as_list
        self.structures = copy.deepcopy(structures or ex.STRUCTURES)
        self.invalides = set(invalides)
        self.references = references if references is not None else {
            "1_referentiel_officiel": [("Programme HG bac pro", "https://eduscol.education.fr/1234/programme"),
                                       ("Wikipédia", "https://fr.wikipedia.org/wiki/X")],
            "5_documents_eleves": [("Gallica", "https://gallica.bnf.fr/ark:/1")]}
        self.response_formats = []
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
        self.response_formats.append(response_format)
        if system == cw.PROMPT_RELECTEUR:
            return self._reply(json.dumps(self.rapports.pop(0)))
        agent = next(a for a in cw.AGENTS if system in (a["prompt"], a.get("prompt_structuration")))
        if agent["name"] in self.invalides:
            self.invalides.discard(agent["name"])
            return self._reply('{"incomplet": true}')
        return self._reply(json.dumps(self.structures[agent["name"]], ensure_ascii=False))

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
        agent = next(a for a in cw.AGENTS if a["prompt"] == self.current_agent)
        refs = [ns(type="tool_reference", title=t, url=u, tool="web_search")
                for t, u in self.references.get(agent["name"], [])]
        return ns(outputs=[ns(type="tool.execution"), ns(type="message.output", content=[
            ns(type="text", text=ex.RECHERCHES[agent["name"]]), *refs])])

    def inputs_for(self, agent_name):
        prompt = cw.AGENTS_BY_NAME[agent_name]["prompt"]
        return [c[2] for c in self.calls if c[0] in ("chat", "web") and c[1] == prompt]

    def model_of(self, prompt):
        return [m for m in self.models if m[0] == prompt][-1]


PROMPTS_PRINCIPAUX = [a["prompt"] for a in cw.AGENTS]


def principaux(calls, genre=None):
    """Prompts des appels principaux des agents (sans les étapes de structuration ni le relecteur)."""
    return [c[1] for c in calls if c[0] in ((genre,) if genre else ("chat", "web")) and c[1] in PROMPTS_PRINCIPAUX]


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
        out = cw.run_pipeline(client, ex.DEMANDE)
        cadrage_in = client.inputs_for("2_cadrage")[0]
        self.assertIn(f"<demande_du_professeur>\n{ex.DEMANDE}\n</demande_du_professeur>", cadrage_in)
        self.assertIn("Des réseaux de production et d'échanges mondialisés", cadrage_in)  # fiche de l'agent 1
        self.assertIn("## Consignes pour cette classe et cette discipline", cadrage_in)
        self.assertIn("Durée effective de la séance : 110 minutes", cadrage_in)
        self.assertIn("07_classe_seconde.md", cadrage_in)
        self.assertIn("08_discipline_geographie.md", cadrage_in)
        self.assertNotIn("06_emc.md", cadrage_in)
        eval_in = client.inputs_for("6_evaluation")[0]
        self.assertIn("## Problématique", eval_in)
        self.assertIn("## Ce que je retiens", eval_in)
        self.assertNotIn("## Partie élève", eval_in)  # l'évaluation ne reçoit pas les documents élèves
        docs_in = client.inputs_for("5_documents_eleves")[0]
        for marque in ("## Problématique", "## Déroulé", "# Le voyage d'un produit mondialisé"):
            self.assertIn(marque, docs_in)
        self.assertEqual(client.deleted, ["ag_1", "ag_1"])  # agents web 1 et 5 nettoyés
        self.assertEqual(set(out["_structures"]), {a["name"] for a in cw.AGENTS})
        self.assertEqual(out["_contexte"], {"classe": "seconde", "discipline": "géographie", "duree_min": 110})
        for a in cw.AGENTS:
            self.assertIsInstance(out[a["name"]], str)

    def test_structured_outputs(self):
        client = FakeClient()
        out = cw.run_pipeline(client, ex.DEMANDE)
        formats = [f for f in client.response_formats if f]
        self.assertTrue(all(f["type"] == "json_schema" and f["json_schema"]["strict"] for f in formats))
        self.assertEqual(len(formats), 6)  # 4 agents rédacteurs + 2 structurations après recherche web
        self.assertEqual(out["3_deroule"], ex.OUTPUTS["3_deroule"])
        self.assertIn("**Total : 110 min**", out["3_deroule"])  # total calculé par le programme

    def test_list_content_is_normalized(self):
        out = cw.run_pipeline(FakeClient(content_as_list=True), ex.DEMANDE)
        self.assertEqual(out["3_deroule"], ex.OUTPUTS["3_deroule"])

    def test_invalid_json_is_retried(self):
        client = FakeClient(invalides={"2_cadrage"})
        out = cw.run_pipeline(client, ex.DEMANDE)
        appels = [c for c in client.calls if c[0] == "chat" and c[1] == cw.PROMPT_CADRAGE]
        self.assertEqual(len(appels), 2)
        self.assertEqual(out["2_cadrage"], ex.OUTPUTS["2_cadrage"])

    def test_invalid_json_twice_fails(self):
        client = FakeClient()
        client.chat.complete = lambda **kw: ns(choices=[ns(message=ns(content='{"rien": 1}'))])
        with self.assertRaises(ValueError):
            cw.call_structured(client, cw.AGENTS_BY_NAME["2_cadrage"], "x", cw.schemas.Cadrage)

    def test_sources_are_kept_and_filtered(self):
        out = cw.run_pipeline(FakeClient(), ex.DEMANDE)
        ref = out["1_referentiel_officiel"]
        officielles, _, ecartees = ref.partition("Sources non officielles")
        self.assertIn("https://eduscol.education.fr/1234/programme", officielles.split("Sources officielles consultées")[1])
        self.assertIn("fr.wikipedia.org", ecartees)
        self.assertEqual(out["_references"]["5_documents_eleves"], ["https://gallica.bnf.fr/ark:/1"])

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
        self.assertEqual(principaux(client.calls, "chat"),
                         [cw.PROMPT_CADRAGE, cw.PROMPT_CONCEPTION, cw.PROMPT_REDACTION, cw.PROMPT_EVALUATION])

    def test_correction_only_reruns_dependents(self):
        client = FakeClient()
        out = cw.run_pipeline(client, "demande")
        client.calls.clear()
        cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 6")))
        self.assertEqual(len(client.calls), 1)  # personne ne dépend de l'évaluation
        client.calls.clear()
        cw.apply_correction(client, out, cw.normalize_rapport(rapport_ko("agent 4")))
        rerun = principaux(client.calls)
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
        structures = copy.deepcopy(ex.STRUCTURES)
        doc = structures["5_documents_eleves"]["documents"][0]
        doc.update(authentique=True, auteur="Un auteur", date="1905", url="https://invente.example/x")
        out = cw.run_pipeline(FakeClient(structures=structures), ex.DEMANDE)
        docs = out["5_documents_eleves"]
        consultees, _, a_verifier = docs.partition("URL citées non issues de la recherche")
        self.assertIn("https://gallica.bnf.fr/ark:/1", consultees.split("Sources consultées")[1])
        self.assertIn("invente.example", a_verifier)
        self.assertNotIn("gallica", a_verifier)
        alertes = [c for c in cw.controles_du_dossier(out) if c.code == "sources"]
        self.assertEqual([(c.agent, c.gravite) for c in alertes], [(5, "alerte")])


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
        self.assertIn("## Partie élève", cw.PROMPT_DOCUMENTS)
        self.assertIn("## Partie professeur", cw.PROMPT_DOCUMENTS)
        for nom in ("5_documents_eleves", "6_evaluation"):  # garanti par la mise en forme des données
            self.assertIn("## Partie élève", ex.OUTPUTS[nom])
            self.assertIn("## Partie professeur", ex.OUTPUTS[nom])

    def test_numerotation_documents_partagee(self):
        self.assertIn("Documents nécessaires", cw.PROMPT_CONCEPTION)
        self.assertIn("Documents nécessaires", cw.PROMPT_DOCUMENTS)
        self.assertIn("totalisent exactement", cw.PROMPT_CONCEPTION)

    def test_vocabulaire_francais_et_sujets_sensibles(self):
        for mot in ("trace écrite", "problématique", "laïcité", "neutralité", "<demande_du_professeur>",
                    "exit ticket"):
            self.assertIn(mot, cw.CONTEXTE_COMMUN)
        self.assertIn("N'emploie aucun calque de l'anglais", cw.CONTEXTE_COMMUN)

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
        rerun = [c for c in client.calls if c[0] in ("chat", "web") and c[1] in PROMPTS_PRINCIPAUX]
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
        numeros = [p.text for p in doc.paragraphs if re.match(r"\d+\.\t", p.text)]
        self.assertEqual(numeros, ["1.\tpremier", "2.\tsecond"])
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
        cellules = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        self.assertTrue(any("Seuil de qualité" in t for t in cellules))
        self.assertIn("Référentiel officiel", textes)
        self.assertNotIn("1_referentiel_officiel", textes)
        self.assertIn("Contrôle qualité", textes)
        self.assertTrue(any("Renvoi vers l'agent 3 (Déroulé de séance)" in t for t in textes))



def texts_of(path):
    doc = Document(path)
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    texte = "\n".join([p.text for p in doc.paragraphs] + cells)
    return texte.replace("\u00a0", " ").replace("\u202f", " "), doc


class DecoupageTests(RouteurReset):
    OUTPUTS = {
        "demande": "Terminale bac pro, mondialisation, 2h",
        "1_referentiel_officiel": "## Programme applicable\nBO n°1\n\n## Sources officielles consultées\n- P : https://eduscol.education.fr/x",
        "2_cadrage": "## Objectifs d'apprentissage\n- Situer les flux",
        "3_deroule": "## Déroulé\n| Horaire | Durée |\n|---|---|\n| 0-10 | 10 |\n\n**Total : 110 min**",
        "4_support_cours": "# La mondialisation des échanges\n\n## Ce que je retiens\n- Les flux augmentent",
        "5_documents_eleves": ("## Partie élève\n### Doc 1 — Un porte-conteneurs\nTexte DOC-ELEVE\n### Questions\n1. Relève\n"
                               "## Partie professeur\n### Corrigé\nREPONSE-SECRETE-DOCS\n\n"
                               "## Sources consultées (recherche web)\n- G : https://gallica.bnf.fr/1"),
        "6_evaluation": ("## Partie élève\n### Quiz\n1. QUESTION-EVAL\n"
                         "## Partie professeur\n### Corrigé\nREPONSE-SECRETE-EVAL"),
    }

    def build(self, outputs, livre=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        rapports = [cw.normalize_rapport(RAPPORT_OK)]
        chemins = cw.build_deliverables(self.tmp.name, outputs["demande"], outputs, rapports, livre)
        return {c.name: texts_of(c) for c in chemins}

    def test_split_parties(self):
        eleve, prof = cw.split_parties(self.OUTPUTS["5_documents_eleves"])
        self.assertIn("DOC-ELEVE", eleve)
        self.assertNotIn("REPONSE-SECRETE", eleve)
        self.assertIn("REPONSE-SECRETE-DOCS", prof)
        self.assertIn("gallica", prof)  # les sources ajoutées en fin de production restent côté prof
        self.assertEqual(cw.split_parties("## Partie Eleve\nA\n## **Partie professeur**\nB"), ("A", "B"))
        self.assertEqual(cw.split_parties("pas de parties"), (None, "pas de parties"))

    def test_fichiers_produits(self):
        docs = self.build(self.OUTPUTS)
        self.assertEqual(sorted(docs), ["1_fiche_professeur.docx", "2_cours_eleve.docx",
                                        "3_documents_eleves.docx", "4_evaluation_eleve.docx", "cours_complet.docx"])

    def test_aucun_corrige_cote_eleve(self):
        docs = self.build(self.OUTPUTS)
        for nom in ("2_cours_eleve.docx", "3_documents_eleves.docx", "4_evaluation_eleve.docx"):
            texte, _ = docs[nom]
            self.assertNotIn("REPONSE-SECRETE", texte, nom)
            self.assertNotIn("Rapports de relecture", texte, nom)
            self.assertNotIn("Total : 110 min", texte, nom)
            self.assertIn("Nom, prénom :", texte)
            self.assertIn("La mondialisation des échanges", texte)
        self.assertIn("DOC-ELEVE", docs["3_documents_eleves.docx"][0])
        self.assertIn("QUESTION-EVAL", docs["4_evaluation_eleve.docx"][0])
        self.assertIn("Les flux augmentent", docs["2_cours_eleve.docx"][0])

    def test_fiche_professeur(self):
        texte, doc = self.build(self.OUTPUTS)["1_fiche_professeur.docx"]
        for attendu in ("La mondialisation des échanges\nFICHE PROFESSEUR", "BO n°1", "Situer les flux",
                        "REPONSE-SECRETE-DOCS", "REPONSE-SECRETE-EVAL", "Contrôle qualité", "Score final : 4.4/5"):
            self.assertIn(attendu, texte)
        self.assertNotIn("DOC-ELEVE", texte)
        # titres calés : les sous-parties du corrigé sont sous le titre de section (niveau 1)
        niveaux = {p.text: p.style.name for p in doc.paragraphs if p.style.name.startswith("Heading")}
        self.assertEqual(niveaux["3. Corrigés"], "Heading 1")
        self.assertEqual(niveaux["Évaluation"], "Heading 2")
        self.assertEqual(niveaux["Corrigé"], "Heading 3")

    def test_production_non_separee_reste_chez_le_prof(self):
        outputs = dict(self.OUTPUTS, **{"6_evaluation": "### Quiz\n1. Q\n### Corrigé\nREPONSE-NON-SEPAREE"})
        docs = self.build(outputs)
        self.assertNotIn("REPONSE-NON-SEPAREE", docs["4_evaluation_eleve.docx"][0])
        self.assertIn("Contenu indisponible", docs["4_evaluation_eleve.docx"][0])
        self.assertIn("REPONSE-NON-SEPAREE", docs["1_fiche_professeur.docx"][0])

    def test_avertissement_seulement_cote_prof(self):
        docs = self.build(self.OUTPUTS, livre=False)
        self.assertIn("Seuil de qualité", docs["1_fiche_professeur.docx"][0])
        for nom in ("2_cours_eleve.docx", "3_documents_eleves.docx", "4_evaluation_eleve.docx"):
            self.assertNotIn("Seuil de qualité", docs[nom][0])



class RenduEleveTests(RouteurReset):
    def render(self, md):
        doc = Document()
        cw.Rendu(eleve=True).markdown(doc, md)
        return doc

    @staticmethod
    def lignes_reponse(doc):
        return sum(1 for p in doc.paragraphs if p.text == "\t")

    def test_lignes_de_reponse_et_qcm(self):
        doc = self.render("## Quiz\n1. Question ouverte ?\n2. QCM ?\n   - a) oui\n   - b) non\n3. Autre ?")
        textes = [p.text for p in doc.paragraphs]
        self.assertIn("☐  oui", textes)
        self.assertIn("☐  non", textes)
        self.assertEqual(self.lignes_reponse(doc), 2 * cw.Rendu.LIGNES_PAR_QUESTION)  # pas de lignes sous le QCM

    def test_lignes_reflexion(self):
        doc = self.render("## Question de réflexion\nExpliquez pourquoi.\n\n## Auto-évaluation\nGrille")
        self.assertEqual(self.lignes_reponse(doc), cw.Rendu.LIGNES_SECTION["reflexion"])

    def test_pas_de_lignes_cote_prof(self):
        doc = Document()
        cw.Rendu().markdown(doc, "## Quiz\n1. Question ?\n## Question de réflexion\nTexte")
        self.assertEqual(self.lignes_reponse(doc), 0)

    def test_numerotation_ne_continue_pas(self):
        doc = Document()
        cw.add_markdown(doc, "1. a\n2. b\n\n## Suite\n1. c")
        self.assertEqual([p.text for p in doc.paragraphs if "\t" in p.text], ["1.\ta", "2.\tb", "1.\tc"])

    def test_encadres_et_cadre_de_dessin(self):
        from exemple_cours import DEMANDE, OUTPUTS
        with tempfile.TemporaryDirectory() as d:
            cw.build_deliverables(d, DEMANDE, OUTPUTS, [], True)
            docs = Document(Path(d) / "3_documents_eleves.docx")
            cours = Document(Path(d) / "2_cours_eleve.docx")
        encadres = [t.cell(0, 0).paragraphs[0].text for t in docs.tables if len(t.columns) == 1]
        self.assertEqual(encadres[:3], ["Doc 1 — Le voyage d'un conteneur",
                                        "Doc 2 — Les grandes routes maritimes mondiales",
                                        "Doc 3 — Le trafic de grands ports"])
        self.assertTrue(any(t.rows[0].height is not None for t in docs.tables))  # cadre pour la carte
        self.assertIn("Ce que je retiens", [t.cell(0, 0).paragraphs[0].text for t in cours.tables])

    def test_rendu_depuis_json(self):
        from exemple_cours import DEMANDE, OUTPUTS
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "cours_final.json"
            source.write_text(json.dumps({"demande": DEMANDE, "dossier": OUTPUTS, "rapports_relecture": [],
                                          "livre": True, "modeles_utilises": {}}), encoding="utf-8")
            with unittest.mock.patch.object(sys, "argv", ["x", "--rendu", str(source)]):
                cw.main()
            self.assertTrue((Path(d) / "2_cours_eleve.docx").exists())


if __name__ == "__main__":
    unittest.main()
