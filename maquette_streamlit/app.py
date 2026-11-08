"""Maquette VibeProf v2 en Streamlit natif (aucun CSS) : données d'exemple, aucun appel à l'API.

Lancement (le thème est lu dans maquette_streamlit/.streamlit/config.toml) :
    cd maquette_streamlit && streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="VibeProf — maquette", page_icon=":material/menu_book:", layout="wide")

ECRANS = ["1 · Nouvelle séance", "2 · Rédaction en cours", "3 · Validation du cadrage", "4 · Séance prête"]
ETAPES = ["Ma séance", "Cadrage", "Déroulé", "Mes documents"]
THEMES = {
    "Des réseaux de production et d'échanges mondialisés": "Seconde professionnelle · arrêté du 3 avril 2019",
    "Une circulation croissante mais diverse des personnes à l'échelle mondiale":
        "Seconde professionnelle · arrêté du 3 avril 2019",
    "Autre sujet, saisi librement": "Vous décrivez le thème vous-même",
}
OBJECTIFS = [
    ("Décrire le trajet d'un produit importé jusqu'à un magasin.", "Mener et construire une démarche géographique"),
    ("Situer les grandes routes maritimes et les principaux ports.", "Se repérer"),
    ("Expliquer le rôle des ports dans les échanges mondiaux.", "Contextualiser"),
]
DECOUPAGE = [("Accroche", 10), ("Trajet d'un produit", 35), ("Les ports", 35), ("Croquis", 20), ("Trace écrite", 10)]
DOCUMENTS = [
    ("Fiche professeur", "Pour vous", "blue", "Cadrage, déroulé, corrigés · 3 pages", "assignment_ind"),
    ("Cours élève", "À distribuer", "green", "Ce que je retiens, vocabulaire, schéma · 2 pages", "school"),
    ("Documents élèves", "À distribuer", "green", "3 documents, questions, croquis · 2 pages", "folder_open"),
    ("Évaluation", "À distribuer", "green", "Quiz, réflexion, auto-évaluation · 1 page", "quiz"),
]
CRITERES = [("Ancrage au programme officiel", 5), ("Clarté et réalisme du déroulé", 4), ("Niveau de langage", 4),
            ("Cohérence d'ensemble", 5), ("Exactitude factuelle", 4)]
RECAP = "Seconde bac pro Commerce · Géographie · 2 h de TD"

if "retours" not in st.session_state:
    st.session_state.retours = {"Problématique": "Partir d'un produit que mes élèves vendent en stage, "
                                                 "par exemple un smartphone."}


# --------------------------------------------------------------------------- éléments communs

def entete(etape_active, etat_actif="blue"):
    """Logo, étapes du parcours (pastilles) et état de la clé API."""
    logo, etapes, cle = st.columns([2, 6, 2], vertical_alignment="center")
    logo.markdown("### :material/menu_book: VibeProf")
    pastilles = []
    for i, nom in enumerate(ETAPES):
        if i < etape_active:
            pastilles.append(f":green-badge[:material/check: {nom}]")
        elif i == etape_active:
            pastilles.append(f":{etat_actif}-badge[**{i + 1} · {nom}**]")
        else:
            pastilles.append(f":gray-badge[{i + 1} · {nom}]")
    etapes.markdown(" &nbsp;→&nbsp; ".join(pastilles))
    with cle:
        st.badge("Clé Mistral connectée", icon=":material/key:", color="green")
    st.divider()


def coche(texte, couleur="green", icone="check_circle"):
    st.markdown(f":{couleur}[:material/{icone}:] {texte}")


@st.dialog("Aperçu — Cours élève", width="large")
def apercu():
    st.markdown("#### Le voyage d'un produit mondialisé")
    st.info("**Ce que je retiens** — La mondialisation met en relation les régions du monde par les échanges. "
            "Les produits voyagent surtout par bateau, dans des conteneurs.", icon=":material/lightbulb:")
    st.markdown("**1. Un produit qui fait le tour du monde**  \nTon téléviseur a souvent été fabriqué en Asie. "
                "Il a voyagé dans un conteneur, sur un énorme navire…")
    st.download_button("Télécharger en Word", b"maquette", "2_cours_eleve.docx", icon=":material/download:",
                       type="primary")


# --------------------------------------------------------------------------- écran 1

def ecran_nouvelle_seance():
    entete(0)
    st.title("Préparons votre prochaine séance")
    st.markdown(":gray[Histoire, géographie ou EMC pour le lycée professionnel. Vous validez le cadrage et le "
                "déroulé avant que le cours soit rédigé.]")

    gauche, droite = st.columns([2, 1], gap="large")
    with gauche:
        with st.container(border=True):
            st.subheader(":blue-badge[A] La classe")
            st.pills("Niveau", ["Seconde bac pro", "Première bac pro", "Terminale bac pro", "CAP 1re année",
                                "CAP 2e année"], default="Seconde bac pro", key="niveau")
            st.text_input("Spécialité (facultatif)", "Métiers du commerce et de la vente")

        with st.container(border=True):
            st.subheader(":blue-badge[B] Le sujet")
            st.segmented_control("Discipline", [":material/account_balance: Histoire", ":material/public: Géographie",
                                                ":material/balance: EMC"],
                                 default=":material/public: Géographie", key="discipline", width="stretch")
            st.radio("Thème du programme officiel", list(THEMES), captions=list(THEMES.values()), key="theme")

        with st.container(border=True):
            st.subheader(":blue-badge[C] La séance")
            st.pills("Durée", ["55 min", "1 h", "1 h 30", "2 h", "3 h"], default="2 h", key="duree",
                     help="Une heure de cours compte 55 minutes : 2 h = 110 min de cours.")
            st.pills("Format", ["Étude de documents (TD)", "Cours dialogué", "Travail en groupes", "Jeu de rôle",
                                "Révision"], default="Étude de documents (TD)", key="format")
            st.text_area("Ce que je sais de ma classe (facultatif)",
                         "Plusieurs élèves allophones ; insister sur la carte.", height=90)

    with droite:
        with st.container(border=True):
            st.caption("VOTRE SÉANCE")
            st.markdown(f"#### {RECAP}  \nsur les réseaux d'échanges mondialisés")
            st.divider()
            st.markdown("**Vous recevrez**")
            for doc in ("Fiche professeur avec corrigés", "Cours élève à distribuer", "Documents élèves et croquis",
                        "Évaluation formative"):
                coche(doc)
            st.toggle("Je relis avant la rédaction", value=True,
                      help="Pause après le cadrage et après le déroulé pour valider ou demander des modifications.")
            st.button("Créer ma séance", type="primary", icon=":material/arrow_forward:", width="stretch")
            st.caption("Environ 5 à 8 minutes au total")
        st.file_uploader("Rouvrir un cours", type=["zip", "json"],
                         help="Le .zip téléchargé ou son fichier cours_final.json.")


# --------------------------------------------------------------------------- écran 2

def ecran_redaction():
    entete(1)
    gauche, droite = st.columns([2, 1], gap="large")
    with gauche:
        with st.container(border=True):
            st.caption(RECAP.upper())
            st.header("Nous préparons le cadrage de votre séance")
            st.markdown(":gray[Vous pourrez le relire et le modifier dans environ une minute. "
                        "Gardez cette page ouverte.]")
            st.progress(0.62, text="**Avant votre relecture** · 2 étapes sur 3")
            st.space("small")

            coche("**Recherche du programme officiel**  \n:gray[Programme de seconde professionnelle trouvé sur "
                  "eduscol.education.fr · 41 s]")
            with st.status("Cadrage : problématique, objectifs, découpage horaire", state="running", expanded=True):
                st.write("Rattachement des objectifs aux capacités officielles…")
                st.caption("Vérification : la durée totale doit faire 110 min.")
            coche("**Votre relecture du cadrage**  \n:gray[Vous validez ou demandez des modifications.]",
                  "orange", "person")
            coche(":gray[**Déroulé de séance, puis votre relecture**]", "gray", "radio_button_unchecked")
            coche(":gray[**Cours, documents, évaluation et relecture qualité**  \n"
                  "Environ 4 minutes, sans intervention de votre part.]", "gray", "radio_button_unchecked")

    with droite:
        with st.container(border=True):
            st.markdown("**Comment c'est fait**")
            st.markdown("Chaque partie est rédigée par un assistant spécialisé, à partir des textes officiels "
                        "(programme, ressources Eduscol, attendus de l'examen).")
            st.markdown(":gray[Le programme vérifie ce qui se calcule : durées, documents prévus, capacités citées. "
                        "Un relecteur contrôle ensuite la pédagogie et l'exactitude.]")
        with st.expander("Détails techniques", icon=":material/account_tree:"):
            st.graphviz_chart('digraph{rankdir=TB;node[shape=box,style="rounded,filled",fontname=Helvetica,'
                              'fontsize=10];a[label="1. Référentiel ✓",fillcolor="#E2F0D9"];'
                              'b[label="2. Cadrage…",fillcolor="#DCE6F2"];c[label="3. Déroulé",fillcolor="#F2F2F2"];'
                              'a->b->c}')
            st.code("[1/6] Référentiel officiel...\n[2/6] Cadrage...", language=None)
        st.button("Annuler la création", width="stretch")


# --------------------------------------------------------------------------- écran 3

def bloc(titre, contenu):
    """Partie du cadrage avec son bouton « Commenter » (popover) et l'état du commentaire."""
    with st.container(border=True):
        tete, action = st.columns([5, 2], vertical_alignment="center")
        nb = 1 if titre in st.session_state.retours else 0
        tete.markdown(f"**{titre.upper()}**" + (" &nbsp;:orange-badge[1 commentaire]" if nb else ""))
        with action.popover("Commenter", icon=":material/chat:", width="stretch"):
            texte = st.text_area(f"Que faut-il modifier — {titre} ?", st.session_state.retours.get(titre, ""),
                                 key=f"com_{titre}")
            if st.button("Enregistrer", key=f"ok_{titre}", type="primary"):
                if texte.strip():
                    st.session_state.retours[titre] = texte.strip()
                else:
                    st.session_state.retours.pop(titre, None)
                st.rerun()
        contenu()


def ecran_validation():
    entete(1, "orange")
    titre, onglets = st.columns([3, 1], vertical_alignment="bottom")
    with titre:
        st.title("Le cadrage vous convient-il ?")
        st.markdown(":gray[Cliquez sur « Commenter » à côté d'une partie pour demander une modification. "
                    "Le déroulé ne sera rédigé qu'après votre validation.]")
    onglets.segmented_control("Partie affichée", ["Cadrage", "Programme officiel"], default="Cadrage",
                              label_visibility="collapsed", width="stretch")

    gauche, droite = st.columns([2, 1], gap="large")
    with gauche:
        bloc("Problématique", lambda: st.markdown(
            "### Comment un produit fabriqué à l'autre bout du monde arrive-t-il dans nos magasins ?"))

        def objectifs():
            for i, (texte, capacite) in enumerate(OBJECTIFS, 1):
                st.markdown(f":blue-badge[{i}] {texte}  \n:gray-badge[{capacite}]")
        bloc("Objectifs d'apprentissage", objectifs)

        def decoupage():
            total = sum(d for _, d in DECOUPAGE)
            for partie, duree in DECOUPAGE:
                st.progress(duree / total, text=f"**{partie}** · {duree} min")
            st.caption(f"Total : {total} min sur 110 min de cours")
        bloc("Découpage horaire", decoupage)

        a, b = st.columns(2)
        with a.container(border=True, height="stretch"):
            st.markdown("**Exemples liés à la spécialité**")
            st.markdown(":gray[Le trajet d'un téléviseur jusqu'au rayon d'un hypermarché. "
                        "Les délais de livraison d'une commande client.]")
        with b.container(border=True, height="stretch"):
            st.markdown("**Points de vigilance**")
            st.markdown(":gray[Confusion entre « flux » et « produit ». Lecture d'une carte à petite échelle.]")

    with droite:
        retours = st.session_state.retours
        with st.container(border=True):
            st.markdown("**Vos demandes de modification**")
            if not retours:
                st.caption("Aucune pour l'instant.")
            for partie, texte in list(retours.items()):
                with st.container(border=True):
                    st.badge(partie, color="orange")
                    st.write(texte)
                    if st.button("Supprimer", key=f"suppr_{partie}", type="tertiary", icon=":material/delete:"):
                        del retours[partie]
                        st.rerun()
            st.text_area("Remarque générale", placeholder="ex : moins d'objectifs, plus de place pour le croquis")
            st.pills("Suggestions", ["Plus simple", "Plus lié au métier", "Moins d'objectifs", "Plus de carte"],
                     selection_mode="multi", label_visibility="collapsed")
            st.button(f"Refaire avec {len(retours)} modification(s)", icon=":material/refresh:", width="stretch",
                      disabled=not retours)
            st.button("Valider et rédiger le déroulé", type="primary", icon=":material/arrow_forward:",
                      width="stretch")
        with st.container(border=True):
            st.markdown("**Vérifications automatiques**")
            coche("Durée totale : 110 min sur 110")
            coche("Capacités du programme officiel")
            coche("Programme en vigueur (2019) sur Eduscol")
        st.button("Abandonner cette séance", type="tertiary", width="stretch")


# --------------------------------------------------------------------------- écran 4

def ecran_resultat():
    entete(4)
    with st.container(border=True):
        texte, actions = st.columns([2, 1], vertical_alignment="center", gap="large")
        with texte:
            st.badge("Votre séance est prête", icon=":material/check:", color="green")
            st.title("Le voyage d'un produit mondialisé")
            st.markdown(f":gray[{RECAP} · Programme de 2019]")
        with actions:
            st.download_button("Tout télécharger (.zip)", b"maquette", "vibeprof.zip", type="primary",
                               icon=":material/download:", width="stretch")
            st.caption("Le .zip contient aussi cours_final.json pour rouvrir ce cours plus tard.")

    st.subheader("Vos documents")
    for colonne, (nom, public, couleur, detail, icone) in zip(st.columns(4), DOCUMENTS):
        with colonne.container(border=True):
            st.markdown(f"## :{couleur}[:material/{icone}:]")
            st.badge(public, color=couleur)
            st.markdown(f"**{nom}**  \n:gray[{detail}]")
            voir, word = st.columns(2)
            if voir.button("Aperçu", key=f"voir_{nom}", width="stretch"):
                apercu()
            word.download_button("Word", b"maquette", f"{nom}.docx", key=f"dl_{nom}", icon=":material/download:",
                                 width="stretch")

    qualite, verifier, demandes = st.columns(3)
    with qualite.container(border=True, height="stretch"):
        st.metric("Contrôle qualité", "4,4 / 5", "livrable", delta_arrow="off")
        for critere, note in CRITERES:
            st.progress(note / 5, text=f"{critere} · {note}/5")
    with verifier.container(border=True, height="stretch"):
        st.markdown("**À vérifier avant le cours**")
        st.warning("**Cours élève** : 129 mots, plus court que prévu (350 à 550).", icon=":material/warning:")
        st.button("Allonger le cours élève", icon=":material/edit:")
    with demandes.container(border=True, height="stretch"):
        st.markdown("**Vos demandes prises en compte**")
        for partie, texte in st.session_state.retours.items():
            coche(f"**{partie}** : {texte}")
        st.button("Modifier une partie", icon=":material/edit_note:", width="stretch")
        st.button("Nouvelle séance", icon=":material/add:", width="stretch")


# --------------------------------------------------------------------------- navigation de la maquette

with st.sidebar:
    st.markdown("**Maquette** — écran affiché")
    ecran = st.radio("Écran", ECRANS, label_visibility="collapsed", key="ecran")
    st.caption("Données d'exemple, aucun appel à l'API. Dans l'application, ces écrans s'enchaînent seuls.")

{ECRANS[0]: ecran_nouvelle_seance, ECRANS[1]: ecran_redaction, ECRANS[2]: ecran_validation,
 ECRANS[3]: ecran_resultat}[ecran]()
