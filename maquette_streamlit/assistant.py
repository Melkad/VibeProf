"""Maquette VibeProf v3 : assistant pas à pas, Streamlit + CSS léger (style.css). Données d'exemple, aucun appel
à l'API.

Lancement local : cd maquette_streamlit && streamlit run assistant.py

Streamlit Community Cloud : dépôt Melkad/VibeProf, fichier principal maquette_streamlit/assistant.py. Les dépendances
viennent de maquette_streamlit/requirements.txt ; les couleurs du thème sont aussi dans style.css, car Cloud peut
n'appliquer que le .streamlit/config.toml racine (celui de l'application réelle).
"""
import time
from pathlib import Path

import streamlit as st

from donnees import CRITERES, DECOUPAGE, DEROULE, DOCUMENTS, OBJECTIFS, THEMES

ss = st.session_state
ss.setdefault("ecran", "accueil")
ss.setdefault("choix", {})
ss.setdefault("avis", {})      # (partie, bloc) -> "ok" | "modif"
ss.setdefault("retours", [])   # demandes du professeur déjà appliquées : (partie, bloc, texte)

st.set_page_config(page_title="VibeProf", page_icon=":material/menu_book:",
                   layout="wide" if ss.ecran == "pret" else "centered", initial_sidebar_state="collapsed")
# Pas de chevrons dans style.css (même en commentaire) : st.html les lit comme des balises et ignore la feuille.
st.html(f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>")

NIVEAUX = [("Seconde bac pro", "1re année du lycée professionnel"), ("Première bac pro", "Préparation du bac pro"),
           ("Terminale bac pro", "Année de l'examen"), ("CAP 1re année", "Première année de CAP"),
           ("CAP 2e année", "Année de l'examen du CAP")]
DISCIPLINES = [("Histoire", ":material/account_balance:", "Repères, acteurs, sources"),
               ("Géographie", ":material/public:", "Territoires, flux, cartes et croquis"),
               ("EMC", ":material/balance:", "Valeurs, droit, débat argumenté")]
DUREES = {"55 min": 55, "1 h": 55, "1 h 30": 85, "2 h": 110, "3 h": 165}
FORMATS = [("Étude de documents", ":material/description:"), ("Cours dialogué", ":material/forum:"),
           ("Travail en groupes", ":material/groups:"), ("Jeu de rôle", ":material/theater_comedy:"),
           ("Révision", ":material/replay:")]
QUESTIONS = ["q_classe", "q_discipline", "q_theme", "q_seance"]
SUGGESTIONS = ["Plus simple", "Plus lié au métier", "Plus court", "Plus d'exemples", "Plus de carte"]
VERIFS = {"cadrage": ["Durée : 110 min sur 110", "Capacités officielles", "Programme en vigueur (2019)"],
          "deroule": ["Durée : 110 min sur 110", "3 documents prévus", "Consignes courtes"]}
ECRANS_DEMO = {"accueil": "Accueil", "q_classe": "Question 1 · Classe", "q_discipline": "Question 2 · Discipline",
               "q_theme": "Question 3 · Thème", "q_seance": "Question 4 · Séance", "recap": "Récapitulatif",
               "redaction_cadrage": "Rédaction du cadrage", "relecture_cadrage": "Relecture du cadrage",
               "relecture_deroule": "Relecture du déroulé", "pret": "Séance prête"}
EXEMPLE = {"niveau": "Seconde bac pro", "specialite": "Métiers du commerce et de la vente",
           "discipline": "Géographie", "theme": next(iter(THEMES)), "duree": "2 h", "format": "Étude de documents",
           "precisions": "Plusieurs élèves allophones ; insister sur la carte.", "relire": True}


def aller(ecran):
    ss.ecran = ecran
    st.rerun()


def resume():
    c = {**EXEMPLE, **ss.choix}
    return f"{c['niveau']} · {c['discipline']} · {c['duree']} · {c['format']}"


# --------------------------------------------------------------------------- éléments communs

def entete():
    logo, cle = st.columns([3, 2], vertical_alignment="center")
    if logo.button(":material/menu_book: **VibeProf**", type="tertiary", key="logo"):
        aller("accueil")
    cle.badge("Clé Mistral connectée", icon=":material/key:", color="green")


def tuiles(groupe, options, choisi, colonnes=2):
    """Grandes tuiles cliquables. `options` : (valeur, libellé affiché). Retourne la valeur cliquée ou None."""
    clique = None
    for debut in range(0, len(options), colonnes):  # ligne par ligne : bon ordre une fois empilé sur téléphone
        cols = st.columns(colonnes)
        for j, (valeur, libelle) in enumerate(options[debut:debut + colonnes]):
            i = debut + j
            etat = "on" if valeur == choisi else "off"
            if cols[j].button(libelle, key=f"tuile_{etat}_{groupe}_{i}", width="stretch"):
                clique = valeur
    return clique


def etape_question(numero, titre, aide):
    """En-tête de l'assistant : progression, choix déjà faits (cliquables), question."""
    st.caption(f"ÉTAPE {numero} SUR 4")
    st.progress(numero / 4)
    deja = [(q, v) for q, v in zip(QUESTIONS, (ss.choix.get("niveau"), ss.choix.get("discipline"),
                                                 ss.choix.get("theme"), None)) if v][:numero - 1]
    if deja:
        cols = st.columns(len(deja) + 1)
        for col, (q, valeur) in zip(cols, deja):
            court = valeur if len(valeur) < 28 else valeur[:26] + "…"
            if col.button(f":material/edit: {court}", key=f"puce_{q}", help="Revenir à cette question"):
                aller(q)
    st.title(titre)
    st.markdown(f":gray[{aide}]")


def navigation(precedent, suivant, pret):
    st.space("small")
    retour, _, continuer = st.columns([1, 1, 1.4])
    if precedent and retour.button("Retour", icon=":material/arrow_back:", width="stretch", key="retour"):
        aller(precedent)
    if continuer.button("Continuer", type="primary", icon=":material/arrow_forward:", width="stretch",
                        disabled=not pret, key="continuer"):
        aller(suivant)


# --------------------------------------------------------------------------- accueil

def ecran_accueil():
    entete()
    with st.container(key="hero"):
        st.markdown("<p style='opacity:.85;margin:0'>Histoire · Géographie · EMC — lycée professionnel</p>",
                    unsafe_allow_html=True)
        st.title("Votre prochaine séance, prête en 10 minutes")
        st.markdown("Répondez à 4 questions. Vous relisez le cadrage et le déroulé ; VibeProf rédige le reste "
                    "à partir des programmes officiels.")
        a, b = st.columns(2)
        if a.button("Créer une séance", type="primary", icon=":material/add:", width="stretch", key="cta"):
            aller("q_classe")
        with b.popover("Rouvrir un cours", icon=":material/upload_file:", width="stretch"):
            st.file_uploader("Fichier .zip ou cours_final.json", type=["zip", "json"])
    st.space("medium")
    for col, (icone, titre, texte) in zip(st.columns(3), [
            ("verified", "Programme officiel", "Thèmes, capacités et attendus de l'examen vérifiés sur Eduscol."),
            ("rate_review", "Vous gardez la main", "Vous validez le cadrage et le déroulé avant la suite."),
            ("print", "Prêt à imprimer", "Fiche professeur, cours, documents et évaluation en Word.")]):
        with col.container(key=f"carte_benefice_{icone}"):
            st.markdown(f"### :blue[:material/{icone}:]")
            st.markdown(f"**{titre}**  \n:gray[{texte}]")


# --------------------------------------------------------------------------- assistant

def q_classe():
    entete()
    etape_question(1, "Pour quelle classe ?", "Les consignes et la longueur des textes s'adaptent au niveau.")
    choisi = ss.choix.get("niveau")
    clic = tuiles("niveau", [(n, f"**{n}**\n{d}") for n, d in NIVEAUX], choisi)
    if clic:
        ss.choix["niveau"] = clic
        st.rerun()
    if choisi:
        ss.choix["specialite"] = st.text_input("Spécialité de la classe (facultatif)",
                                               ss.choix.get("specialite", ""),
                                               placeholder="ex : Métiers du commerce et de la vente")
    navigation(None, "q_discipline", bool(choisi))


def q_discipline():
    entete()
    etape_question(2, "Quelle discipline ?", "Nous chargeons les thèmes officiels correspondants.")
    choisi = ss.choix.get("discipline")
    clic = tuiles("discipline", [(n, f"{i} **{n}**\n{d}") for n, i, d in DISCIPLINES], choisi, colonnes=3)
    if clic:
        ss.choix["discipline"] = clic
        st.rerun()
    navigation("q_classe", "q_theme", bool(choisi))


def q_theme():
    entete()
    etape_question(3, "Quel thème du programme ?", "Thèmes en vigueur pour la seconde professionnelle.")
    choisi = ss.choix.get("theme")
    options = [(t, f"**{t}**\n{ref}") for t, ref in THEMES.items()]
    clic = tuiles("theme", options, choisi, colonnes=1)
    if clic:
        ss.choix["theme"] = clic
        st.rerun()
    if choisi == "Autre sujet, saisi librement":
        ss.choix["sujet_libre"] = st.text_input("Décrivez le sujet de la séance", ss.choix.get("sujet_libre", ""),
                                                placeholder="ex : une étude de cas sur le port du Havre")
    navigation("q_discipline", "q_seance", bool(choisi))


def q_seance():
    entete()
    etape_question(4, "Comment sera la séance ?", "Dernière étape avant le récapitulatif.")
    with st.container(key="carte_seance"):
        ss.choix["duree"] = st.pills("Durée", list(DUREES), default=ss.choix.get("duree", "2 h"),
                                     format_func=lambda d: f"{d} · {DUREES[d]} min de cours" if d == "2 h" else d)
        st.markdown("**Format**")
        clic = tuiles("format", [(f, f"{i} {f}") for f, i in FORMATS], ss.choix.get("format"), colonnes=3)
        if clic:
            ss.choix["format"] = clic
            st.rerun()
        ss.choix["precisions"] = st.text_area("Ce que je sais de ma classe (facultatif)",
                                              ss.choix.get("precisions", ""), height=90,
                                              placeholder="ex : plusieurs élèves allophones ; insister sur la carte")
        ss.choix["relire"] = st.toggle("Je relis le cadrage et le déroulé avant la rédaction",
                                       value=ss.choix.get("relire", True))
    navigation("q_theme", "recap", bool(ss.choix.get("duree") and ss.choix.get("format")))


def ecran_recap():
    entete()
    st.caption("RÉCAPITULATIF")
    st.title("Tout est prêt pour créer votre séance")
    c = {**EXEMPLE, **ss.choix}
    with st.container(key="carte_recap"):
        for libelle, valeur, question in [
                ("Classe", f"{c['niveau']}" + (f" · {c['specialite']}" if c.get("specialite") else ""), "q_classe"),
                ("Discipline", c["discipline"], "q_discipline"), ("Thème", c["theme"], "q_theme"),
                ("Séance", f"{c['duree']} · {c['format']}", "q_seance")]:
            texte, action = st.columns([5, 1], vertical_alignment="center")
            texte.markdown(f":gray[{libelle}]  \n**{valeur}**")
            if action.button("Modifier", key=f"modif_{question}", type="tertiary"):
                aller(question)
        st.divider()
        st.markdown("**Vous recevrez**")
        for col, (nom, _, couleur, _, icone) in zip(st.columns(4), DOCUMENTS):
            col.markdown(f":{couleur}[:material/{icone}:]  \n{nom}")
    st.info("Vous relirez le **cadrage** puis le **déroulé**. Comptez 5 à 8 minutes au total.",
            icon=":material/rate_review:")
    retour, creer = st.columns([1, 2])
    if retour.button("Retour", icon=":material/arrow_back:", width="stretch"):
        aller("q_seance")
    if creer.button("Créer ma séance", type="primary", icon=":material/auto_awesome:", width="stretch", key="cta"):
        aller("redaction_cadrage")


# --------------------------------------------------------------------------- rédaction (simulée)

def ecran_redaction(titre, etapes, suivant, pause=0.6):
    entete()
    st.caption(resume().upper())
    st.title(titre)
    st.markdown(":gray[Gardez cette page ouverte : cela prend environ une minute.]")
    with st.container(key="carte_redaction"):
        barre = st.progress(0.0)
        for i, (libelle, detail) in enumerate(etapes):
            with st.status(libelle, expanded=False) as statut:
                st.write(detail)
                time.sleep(pause)
                statut.update(state="complete")
            barre.progress((i + 1) / len(etapes))
    aller(suivant)


# --------------------------------------------------------------------------- relecture

def bloc(partie, nom, contenu):
    """Partie à relire : « Ça me va » ou « Modifier » (zone de texte et suggestions dépliées sur place)."""
    avis = ss.avis.get((partie, nom))
    with st.container(key=f"carte_{avis or 'neutre'}_{partie}_{nom}".replace(" ", "_").replace("'", "")):
        tete, ok, modif = st.columns([3, 1.2, 1.2], vertical_alignment="center")
        etiquette = {"ok": " :green-badge[:material/check: validé]", "modif": " :orange-badge[à modifier]"}
        tete.markdown(f"**{nom}**" + etiquette.get(avis, ""))
        if ok.button("Ça me va", icon=":material/thumb_up:", key=f"ok_{partie}_{nom}", width="stretch",
                     type="primary" if avis == "ok" else "secondary"):
            ss.avis[(partie, nom)] = "ok"
            st.rerun()
        if modif.button("Modifier", icon=":material/edit:", key=f"mod_{partie}_{nom}", width="stretch"):
            ss.avis[(partie, nom)] = "modif"
            st.rerun()
        contenu()
        if avis == "modif":
            st.text_area("Qu'est-ce qui ne vous convient pas ?", key=f"txt_{partie}_{nom}",
                         placeholder="ex : partir d'un produit vendu par les élèves en stage")
            st.pills("Suggestions", SUGGESTIONS, selection_mode="multi", key=f"sug_{partie}_{nom}",
                     label_visibility="collapsed")


def demande(partie, nom):
    texte = (ss.get(f"txt_{partie}_{nom}") or "").strip()
    sugg = ss.get(f"sug_{partie}_{nom}") or []
    return " ; ".join([texte] * bool(texte) + list(sugg))


def ecran_relecture(partie):
    entete()
    cadrage = partie == "cadrage"
    st.caption(f"VOTRE RELECTURE · {'1' if cadrage else '2'} SUR 2")
    st.title("Le cadrage vous convient-il ?" if cadrage else "Et le déroulé ?")
    st.markdown(" ".join(f":green-badge[:material/check: {v}]" for v in VERIFS[partie]))
    st.markdown(":gray[Validez chaque partie ou dites ce qu'il faut changer : elle sera refaite.]")

    if cadrage:
        bloc(partie, "Problématique", lambda: st.markdown(
            "### Comment un produit fabriqué à l'autre bout du monde arrive-t-il dans nos magasins ?"))
        bloc(partie, "Objectifs", lambda: [st.markdown(f":blue-badge[{i}] {t}  \n:gray-badge[{c}]")
                                           for i, (t, c) in enumerate(OBJECTIFS, 1)])
        bloc(partie, "Découpage horaire", lambda: [st.progress(d / 110, text=f"**{p}** · {d} min")
                                                   for p, d in DECOUPAGE])
    else:
        def etapes():
            for titre, duree, consigne, support in DEROULE:
                st.markdown(f":blue-badge[{duree} min] **{titre}**  \n{consigne}  \n:gray[Support : {support}]")
        bloc(partie, "Étapes de la séance", etapes)
        bloc(partie, "Différenciation", lambda: st.markdown(
            "- **En difficulté** : carte avec les océans déjà nommés, questions guidées\n"
            "- **Plus rapides** : trouver le port le plus proche du lycée\n"
            "- **Besoins particuliers** : police agrandie, consignes lues à voix haute"))

    modifs = [(nom, demande(p, nom)) for (p, nom), a in ss.avis.items() if p == partie and a == "modif"]
    a_refaire = [(nom, d) for nom, d in modifs if d]
    with st.container(key="barre_actions"):
        info, refaire, valider = st.columns([1.6, 1.4, 1.6], vertical_alignment="center")
        info.markdown(f"**{len(a_refaire)} modification(s)**  \n:gray[demandée(s)]" if modifs
                      else ":gray[Tout vous convient ?]")
        if refaire.button(f"Refaire ({len(a_refaire)})", icon=":material/refresh:", width="stretch",
                          disabled=not a_refaire, key="refaire"):
            for nom, d in a_refaire:
                ss.retours.append((partie, nom, d))
                ss.avis[(partie, nom)] = "ok"
            st.toast("Partie refaite selon vos demandes. Relisez-la.", icon=":material/check_circle:")
            st.rerun()
        if valider.button("Valider et continuer", type="primary", icon=":material/arrow_forward:",
                          width="stretch", disabled=bool(modifs), key="valider",
                          help="Appliquez d'abord vos modifications." if modifs else None):
            aller("redaction_deroule" if cadrage else "redaction_fin")


# --------------------------------------------------------------------------- séance prête

@st.dialog("Aperçu — Cours élève", width="large")
def apercu():
    st.markdown("#### Le voyage d'un produit mondialisé")
    st.info("**Ce que je retiens** — La mondialisation met en relation les régions du monde par les échanges.",
            icon=":material/lightbulb:")
    st.markdown("**1. Un produit qui fait le tour du monde**  \nTon téléviseur a souvent été fabriqué en Asie…")
    st.download_button("Télécharger en Word", b"maquette", "2_cours_eleve.docx", type="primary",
                       icon=":material/download:")


def ecran_pret():
    if not ss.get("toast_pret"):
        st.toast("Votre séance est prête !", icon=":material/celebration:")
        ss.toast_pret = True
    entete()
    with st.container(key="carte_titre"):
        texte, actions = st.columns([2, 1], vertical_alignment="center", gap="large")
        with texte:
            st.badge("Prête à imprimer", icon=":material/check:", color="green")
            st.title("Le voyage d'un produit mondialisé")
            st.markdown(f":gray[{resume()} · Programme de 2019]")
        with actions:
            st.download_button("Tout télécharger (.zip)", b"maquette", "vibeprof.zip", type="primary",
                               icon=":material/download:", width="stretch", key="cta")
            st.caption("Le .zip permet aussi de rouvrir ce cours plus tard.")

    st.subheader("Vos documents")
    for col, (nom, public, couleur, detail, icone) in zip(st.columns(4), DOCUMENTS):
        with col.container(key=f"carte_doc_{icone}"):
            st.markdown(f"## :{couleur}[:material/{icone}:]")
            st.badge(public, color=couleur)
            st.markdown(f"**{nom}**  \n:gray[{detail}]")
            voir, word = st.columns(2)
            if voir.button("Aperçu", key=f"voir_{icone}", width="stretch"):
                apercu()
            word.download_button("Word", b"maquette", f"{nom}.docx", key=f"dl_{icone}", width="stretch")

    qualite, verifier, demandes = st.columns(3)
    with qualite.container(key="carte_qualite", height="stretch"):
        st.metric("Contrôle qualité", "4,4 / 5", "Livrable", delta_arrow="off")
        with st.expander("Détail par critère"):
            for critere, note in CRITERES:
                st.progress(note / 5, text=f"{critere} · {note}/5")
    with verifier.container(key="carte_verifier", height="stretch"):
        st.markdown("**À vérifier avant le cours**")
        st.warning("**Cours élève** : 129 mots, plus court que prévu (350 à 550).", icon=":material/warning:")
        st.button("Allonger le cours élève", icon=":material/edit:", width="stretch")
    with demandes.container(key="carte_demandes", height="stretch"):
        st.markdown("**Vos demandes prises en compte**")
        for partie, nom, texte in ss.retours or [("cadrage", "Problématique", "partir d'un produit vendu en stage")]:
            st.markdown(f":green[:material/check_circle:] **{nom}** : {texte}")
        if st.button("Nouvelle séance", icon=":material/add:", width="stretch"):
            ss.choix, ss.avis, ss.retours, ss.toast_pret = {}, {}, [], False
            aller("q_classe")


# --------------------------------------------------------------------------- démonstration et routage

def raccourci():
    ss.ecran = ss.demo
    if ss.ecran not in ("accueil", "q_classe"):
        ss.choix = {**EXEMPLE, **ss.choix}


with st.sidebar:
    st.markdown("**Maquette** — aller à un écran")
    st.radio("Écran", list(ECRANS_DEMO), format_func=ECRANS_DEMO.get, key="demo", on_change=raccourci,
             label_visibility="collapsed")
    st.caption("Données d'exemple, aucun appel à l'API.")

ECRANS = {
    "accueil": ecran_accueil, "q_classe": q_classe, "q_discipline": q_discipline, "q_theme": q_theme,
    "q_seance": q_seance, "recap": ecran_recap,
    "redaction_cadrage": lambda: ecran_redaction("Nous préparons le cadrage", [
        ("Recherche du programme officiel", "Programme de seconde professionnelle trouvé sur eduscol.education.fr"),
        ("Problématique et objectifs", "Objectifs rattachés aux capacités officielles"),
        ("Découpage horaire", "Durée vérifiée : 110 min")], "relecture_cadrage"),
    "relecture_cadrage": lambda: ecran_relecture("cadrage"),
    "redaction_deroule": lambda: ecran_redaction("Nous rédigeons le déroulé", [
        ("Étapes et consignes", "5 étapes, consignes à l'impératif"),
        ("Documents prévus et différenciation", "3 documents, 3 profils d'élèves")], "relecture_deroule"),
    "relecture_deroule": lambda: ecran_relecture("deroule"),
    "redaction_fin": lambda: ecran_redaction("Nous terminons votre séance", [
        ("Cours élève", "Ce que je retiens, vocabulaire, schéma"),
        ("Documents élèves", "Recherche de sources vérifiables"),
        ("Évaluation", "Quiz et question de réflexion"),
        ("Relecture qualité", "Score 4,4/5 : livrable"),
        ("Mise en page Word", "4 documents prêts")], "pret"),
    "pret": ecran_pret,
}
ECRANS[ss.ecran]()
