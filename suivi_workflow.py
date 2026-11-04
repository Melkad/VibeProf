"""Graphe d'avancement du workflow : état de chaque étape et rendu au format DOT (Graphviz).

Le moteur signale les étapes via `course_workflow.evenement` ; `SuiviWorkflow.recevoir` est le rappel à brancher
dans `configurer_session(evenements=...)`. `to_dot()` produit le graphe, affiché par st.graphviz_chart.
"""
import time

import course_workflow as cw

COULEURS = {  # état -> (fond, bordure, police)
    "attente": ("#F2F2F2", "#BFBFBF", "#7F7F7F"),
    "en_cours": ("#DCE6F2", "#1F4E79", "#1F4E79"),
    "correction": ("#FFF2CC", "#BF8F00", "#7F6000"),
    "termine": ("#E2F0D9", "#548235", "#385723"),
    "erreur": ("#F8D7DA", "#C00000", "#C00000"),
}
SYMBOLES = {"attente": "en attente", "en_cours": "⏳ en cours…", "correction": "✎ correction…",
            "termine": "✓", "erreur": "✗ erreur"}


def aretes_principales():
    """Dépendances entre agents sans les arêtes redondantes (réduction transitive) : le graphe reste lisible."""
    noms = [a["name"] for a in cw.AGENTS]
    deps = {a["name"]: {i for i in a["inputs"] if i in noms} for a in cw.AGENTS}

    def ancetres(nom, vus=None):
        vus = set() if vus is None else vus
        for d in deps[nom]:
            if d not in vus:
                vus.add(d)
                ancetres(d, vus)
        return vus

    aretes = []
    for nom in noms:
        for d in deps[nom]:
            # d -> nom est redondante si d est déjà un ancêtre d'une autre dépendance de nom
            if not any(d in ancetres(autre) for autre in deps[nom] if autre != d):
                aretes.append((d, nom))
    return aretes


def _duree(secondes):
    secondes = int(round(secondes))
    return f"{secondes} s" if secondes < 60 else f"{secondes // 60} min {secondes % 60:02d} s"


class SuiviWorkflow:
    """Mémorise l'état de chaque étape. `on_change` (facultatif) est appelé après chaque événement."""

    def __init__(self, on_change=None, horloge=time.monotonic):
        self.on_change = on_change
        self.horloge = horloge
        noms = ["demande"] + [a["name"] for a in cw.AGENTS] + ["relecteur", "documents"]
        self.etapes = {n: {"etat": "attente", "debut": None, "duree": 0.0, "passages": 0} for n in noms}
        self.etapes["demande"]["etat"] = "termine"
        self.relecture = {}          # dernière relecture : iteration, max_relectures, score, livre
        self.renvois = []            # [(iteration, numéro d'agent)] demandés par le relecteur
        self.message_erreur = None

    # -- réception des événements du moteur

    def recevoir(self, etape, etat, infos=None):
        infos = infos or {}
        e = self.etapes.get(etape)
        if e is None:
            return
        maintenant = self.horloge()
        if etat in ("en_cours", "correction"):
            e["debut"] = maintenant
            e["passages"] += 1
        elif e["debut"] is not None:
            e["duree"] += maintenant - e["debut"]
            e["debut"] = None
        e["etat"] = etat
        if etape == "relecteur":
            self.relecture.update({k: v for k, v in infos.items() if k != "corrections"})
            if etat == "termine":
                self.renvois += [(infos.get("iteration"), n) for n in infos.get("corrections") or []]
        if etat == "erreur":
            self.message_erreur = infos.get("message")
        if self.on_change:
            self.on_change(self)

    def marquer_erreur(self, message=None):
        """Échec global : l'étape en cours (s'il y en a une) passe en erreur."""
        for nom, e in self.etapes.items():
            if e["etat"] in ("en_cours", "correction"):
                self.recevoir(nom, "erreur", {"message": message})
                return
        self.message_erreur = message

    # -- rendu

    def _titre(self, nom):
        if nom == "demande":
            return "Demande du prof"
        if nom == "relecteur":
            return "Relecteur"
        if nom == "documents":
            return "Documents Word"
        agent = cw.AGENTS_BY_NAME[nom]
        return f"{nom.split('_')[0]}. {agent['title']}"

    def _detail(self, nom):
        e = self.etapes[nom]
        if nom == "demande":
            return ""
        if nom == "relecteur":
            r = self.relecture
            if e["etat"] in ("en_cours", "correction") and r.get("iteration"):
                return f"⏳ relecture {r['iteration']}/{r.get('max_relectures', '?')}…"
            if e["etat"] == "termine" and r.get("score") is not None:
                verdict = "livrable" if r.get("livre") else "corrections demandées"
                return f"✓ {r['score']}/5 — {verdict}"
        texte = SYMBOLES[e["etat"]]
        if e["etat"] == "termine":
            texte += f" {_duree(e['duree'])}"
            if e["passages"] > 1:
                texte += f" · {e['passages']} passages"
        elif e["etat"] in ("en_cours", "correction") and e["passages"] > 1:
            texte += f" (passage {e['passages']})"
        return texte

    def _sous_titre(self, nom):
        if nom in cw.AGENTS_BY_NAME and cw.AGENTS_BY_NAME[nom]["web"]:
            return "recherche web"
        return ""

    def to_dot(self):
        lignes = [
            "digraph workflow {",
            '  graph [rankdir=TB, nodesep=0.35, ranksep=0.32, bgcolor="transparent", fontname="Helvetica"];',
            '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, penwidth=1.4, '
            'margin="0.18,0.07", width=2.6];',
            '  edge [color="#8C8C8C", arrowsize=0.7];',
        ]
        for nom, e in self.etapes.items():
            fond, bordure, police = COULEURS[e["etat"]]
            parties = [f"<B>{_echapper(self._titre(nom))}</B>"]
            if self._sous_titre(nom):
                parties.append(f'<FONT POINT-SIZE="9">{self._sous_titre(nom)}</FONT>')
            if self._detail(nom):
                parties.append(f'<FONT POINT-SIZE="10">{_echapper(self._detail(nom))}</FONT>')
            epaisseur = 2.6 if e["etat"] in ("en_cours", "correction") else 1.4
            lignes.append(f'  "{nom}" [label=<{"<BR/>".join(parties)}>, fillcolor="{fond}", color="{bordure}", '
                          f'fontcolor="{police}", penwidth={epaisseur}];')
        lignes.append('  "demande" -> "1_referentiel_officiel";')
        for source, cible in aretes_principales():
            lignes.append(f'  "{source}" -> "{cible}";')
        feuilles = [a["name"] for a in cw.AGENTS
                    if not any(a["name"] in b["inputs"] for b in cw.AGENTS)]
        for f in feuilles:
            lignes.append(f'  "{f}" -> "relecteur";')
        lignes.append('  "relecteur" -> "documents";')
        for iteration, numero in self.renvois:
            if 1 <= numero <= len(cw.AGENTS):
                cible = cw.AGENTS[numero - 1]["name"]
                lignes.append(f'  "relecteur" -> "{cible}" [style=dashed, color="#BF8F00", fontcolor="#7F6000", '
                              f'fontsize=9, label=" correction {iteration}", constraint=false];')
        lignes.append("}")
        return "\n".join(lignes)


def _echapper(texte):
    return (str(texte).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
