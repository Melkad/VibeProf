"""Banc d'évaluation de VibeProf : génère un cours pour chaque demande type et mesure la qualité.

Usage :
    python evaluation/banc.py                      # tous les cas (appels réels à l'API Mistral : coût réel)
    python evaluation/banc.py --cas 2de-geo-1 tle-emc-1
    python evaluation/banc.py --limite 3
    python evaluation/banc.py --simulation         # faux client, sans API : pour tester le banc lui-même

Résultats dans evaluation/resultats/<horodatage>/ : un dossier par cas (documents Word, cours_final.json),
resultats.json et rapport.md (tableau de synthèse, moyennes, contrôles les plus fréquents).
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import controles  # noqa: E402
import course_workflow as cw  # noqa: E402
from contexte import Contexte, duree_effective  # noqa: E402

CAS = Path(__file__).resolve().parent / "cas.json"
CLASSE_LIBELLE = {"CAP": "CAP", "seconde": "Seconde bac pro", "première": "Première bac pro",
                  "terminale": "Terminale bac pro"}


def demande_du_cas(cas):
    texte = (f"{CLASSE_LIBELLE[cas['classe']]} {cas['specialite']}, {cas['discipline']}, thème : {cas['theme']}, "
             f"{cas['duree']}, {cas['format']}")
    if cas.get("precisions"):
        texte += f". Précisions du professeur : {cas['precisions']}"
    return texte


def mesurer(cas, resultat, secondes):
    rapports = resultat["rapports"]
    dernier = rapports[-1] if rapports else {}
    liste = cw.controles_du_dossier(resultat["dossier"])
    structures = resultat["dossier"].get("_structures", {})
    support = structures.get("4_support_cours") or {}
    mots_support = controles.nb_mots(" ".join([*(support.get("ce_que_je_retiens") or []),
                                               *(p["texte"] for p in support.get("parties") or [])]))
    return {
        "id": cas["id"], "classe": cas["classe"], "discipline": cas["discipline"],
        "livre": resultat["livre"], "statut": resultat["statut"],
        "score_final": dernier.get("score_global"), "notes": dernier.get("notes", {}),
        "relectures": len(rapports), "secondes": round(secondes),
        "bloquants": [c.to_dict() for c in controles.bloquants(liste)],
        "alertes": [c.to_dict() for c in liste if c.gravite == "alerte"],
        "verifications": dernier.get("verifications", {}),
        "mots_support": mots_support,
        "modeles": dict(cw.ROUTEUR.utilises),
    }


def rapport_markdown(lignes, date):
    out = [f"# Banc d'évaluation VibeProf — {date}", "",
           "| Cas | Classe | Discipline | Livré | Score | Relectures | Bloquants | Alertes | Mots support | Durée |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for l in lignes:
        if "erreur" in l:
            out.append(f"| {l['id']} | {l['classe']} | {l['discipline']} | erreur | – | – | – | – | – | – |")
            continue
        out.append(f"| {l['id']} | {l['classe']} | {l['discipline']} | {'oui' if l['livre'] else 'non'} | "
                   f"{l['score_final']} | {l['relectures']} | {len(l['bloquants'])} | {len(l['alertes'])} | "
                   f"{l['mots_support']} | {l['secondes']} s |")
    ok = [l for l in lignes if "erreur" not in l]
    if ok:
        scores = [l["score_final"] for l in ok if l["score_final"] is not None]
        out += ["", "## Synthèse", "",
                f"- Cas réussis : {len(ok)}/{len(lignes)} ; livrés : {sum(l['livre'] for l in ok)}/{len(ok)}",
                f"- Score final moyen : {round(sum(scores) / len(scores), 2) if scores else '–'}/5",
                f"- Relectures moyennes : {round(sum(l['relectures'] for l in ok) / len(ok), 2)}",
                f"- Durée moyenne : {round(sum(l['secondes'] for l in ok) / len(ok))} s"]
        criteres = Counter()
        for l in ok:
            for k, v in (l["notes"] or {}).items():
                criteres[k] += float(v) if v is not None else 0
        if criteres:
            out.append("- Notes moyennes par critère : " + " · ".join(
                f"{cw.CRITERES.get(k, k)} {round(v / len(ok), 2)}" for k, v in criteres.items()))
        frequents = Counter((c["code"], c["agent"]) for l in ok for c in l["bloquants"] + l["alertes"])
        if frequents:
            out += ["", "## Contrôles les plus fréquents (fin de génération)", ""]
            out += [f"- {code} (agent {agent}) : {n} cas" for (code, agent), n in frequents.most_common(10)]
    erreurs = [l for l in lignes if "erreur" in l]
    if erreurs:
        out += ["", "## Erreurs", ""] + [f"- {l['id']} : {l['erreur']}" for l in erreurs]
    return "\n".join(out) + "\n"


def client_simulation():
    sys.path[:0] = [str(RACINE / "tests"), str(RACINE / "tests" / "fixtures")]
    from test_course_workflow import RAPPORT_OK, FakeClient
    return FakeClient(rapports=[RAPPORT_OK] * 10)


def lancer(cas_liste, sortie, client_fabrique, max_relectures, journal=print):
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    dossier = Path(sortie) / date
    dossier.mkdir(parents=True, exist_ok=True)
    lignes = []
    for i, cas in enumerate(cas_liste, 1):
        journal(f"[{i}/{len(cas_liste)}] {cas['id']} — {cas['theme']}")
        contexte = Contexte(cas["classe"], cas["discipline"], duree_effective(cas["duree"]))
        cw.configurer_session(journal=lambda m: None)
        debut = time.monotonic()
        try:
            res = cw.generer_cours(client_fabrique(), demande_du_cas(cas), dossier / cas["id"], max_relectures,
                                   contexte=contexte)
            ligne = mesurer(cas, res, time.monotonic() - debut)
            journal(f"    livré : {'oui' if ligne['livre'] else 'non'} — score {ligne['score_final']} — "
                    f"{len(ligne['bloquants'])} bloquant(s), {len(ligne['alertes'])} alerte(s)")
        except Exception as exc:
            ligne = {"id": cas["id"], "classe": cas["classe"], "discipline": cas["discipline"], "erreur": str(exc)}
            journal(f"    erreur : {exc}")
        finally:
            cw.configurer_session()
        lignes.append(ligne)
        (dossier / "resultats.json").write_text(json.dumps(lignes, ensure_ascii=False, indent=2), encoding="utf-8")
    (dossier / "rapport.md").write_text(rapport_markdown(lignes, date), encoding="utf-8")
    return dossier, lignes


def main():
    parser = argparse.ArgumentParser(description="Banc d'évaluation de VibeProf")
    parser.add_argument("--cas", nargs="*", help="identifiants des cas à lancer (défaut : tous)")
    parser.add_argument("--limite", type=int, help="nombre maximal de cas")
    parser.add_argument("--max-relectures", type=int, default=cw.MAX_RELECTURES)
    parser.add_argument("--sortie", default=str(Path(__file__).resolve().parent / "resultats"))
    parser.add_argument("--simulation", action="store_true", help="faux client Mistral (aucun appel API)")
    args = parser.parse_args()

    cas_liste = json.loads(CAS.read_text(encoding="utf-8"))
    if args.cas:
        cas_liste = [c for c in cas_liste if c["id"] in args.cas]
    if args.limite:
        cas_liste = cas_liste[:args.limite]
    if not cas_liste:
        sys.exit("Aucun cas sélectionné.")

    if args.simulation:
        fabrique = client_simulation
    else:
        cle = os.environ.get("MISTRAL_API_KEY")
        if not cle:
            sys.exit("Erreur : variable d'environnement MISTRAL_API_KEY manquante (ou utilisez --simulation).")
        print(f"{len(cas_liste)} cas à générer avec l'API Mistral : chaque cas coûte une génération complète.")
        fabrique = lambda: cw.make_client(cle)
    dossier, _ = lancer(cas_liste, args.sortie, fabrique, args.max_relectures)
    print(f"Rapport : {dossier / 'rapport.md'}")


if __name__ == "__main__":
    main()
