"""Interface web VibeProf (Streamlit).

Lancement : streamlit run app.py
"""
import hmac
import io
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st

import course_workflow as cw
from contexte import THEMES_OFFICIELS, Contexte, duree_effective
from suivi_workflow import SuiviWorkflow

st.set_page_config(page_title="VibeProf", page_icon="📚", layout="centered")

CLASSES = ["Seconde bac pro", "Première bac pro", "Terminale bac pro", "CAP 1re année", "CAP 2e année"]
CLASSE_CODE = {"Seconde bac pro": "seconde", "Première bac pro": "première", "Terminale bac pro": "terminale",
               "CAP 1re année": "CAP", "CAP 2e année": "CAP"}
AUTRE_THEME = "Autre thème (saisie libre)"
DISCIPLINES = ["Histoire", "Géographie", "EMC"]
DUREES = ["55 min", "1 h", "1 h 30", "2 h", "3 h"]
FORMATS = ["Étude de documents (TD)", "Cours dialogué", "Travail en groupes", "Mise en situation / jeu de rôle",
           "Séance de révision"]
LIBELLES = {
    "1_fiche_professeur.docx": ("Fiche professeur", "cadrage, déroulé, corrigés"),
    "2_cours_eleve.docx": ("Cours élève", "à distribuer"),
    "3_documents_eleves.docx": ("Documents élèves", "à distribuer"),
    "4_evaluation_eleve.docx": ("Évaluation élève", "à distribuer"),
    "cours_complet.docx": ("Dossier complet", "archive"),
}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# --------------------------------------------------------------------------- configuration

def secret(nom):
    """Valeur d'une variable d'environnement ou d'un secret Streamlit (déploiement), sinon None."""
    if os.environ.get(nom):
        return os.environ[nom]
    try:
        return st.secrets.get(nom)
    except Exception:  # pas de fichier secrets.toml
        return None


def controle_acces():
    """Si VIBEPROF_CODE_ACCES est défini (déploiement en ligne), demande ce code avant d'ouvrir l'application."""
    code = secret("VIBEPROF_CODE_ACCES")
    if not code or st.session_state.get("acces_ok"):
        return
    st.title("📚 VibeProf")
    saisie = st.text_input("Code d'accès", type="password", key="code_acces")
    if saisie and hmac.compare_digest(saisie, code):
        st.session_state["acces_ok"] = True
        st.rerun()
    elif saisie:
        st.error("Code incorrect.")
    st.stop()


def barre_laterale():
    with st.sidebar:
        st.header("Réglages")
        cle_serveur = secret("MISTRAL_API_KEY")
        if cle_serveur:
            st.success("Clé API Mistral configurée sur le serveur.", icon="🔑")
            cle = cle_serveur
        else:
            cle = st.text_input("Clé API Mistral", type="password", key="cle_api",
                                help="Créez une clé sur console.mistral.ai. Elle n'est utilisée que pendant "
                                     "votre session et n'est jamais enregistrée.")
        with st.expander("Réglages avancés"):
            modeles = {
                "principal": st.text_input("Modèle principal (rédaction)", cw.MODELES_DEFAUT["principal"]),
                "leger": st.text_input("Modèle léger (évaluation, relecture)", cw.MODELES_DEFAUT["leger"]),
                "secours": st.text_input("Modèle de secours", cw.MODELES_DEFAUT["secours"]),
            }
            relectures = st.slider("Nombre maximal de relectures", 1, 5, cw.MAX_RELECTURES,
                                   help="Chaque relecture peut faire corriger le cours, ce qui allonge la génération.")

        with st.expander("Cadre officiel"):
            st.caption("Extraits de textes officiels transmis aux agents (dossier `cadre_officiel/`).")
            for f in cw.CADRE_OFFICIEL:
                icone = {"vérifié": "🟢", "partiel": "🟡"}.get(f["statut"], "⚪")
                st.markdown(f"{icone} `{f['fichier']}` — {f['statut']}")

        st.divider()
        st.subheader("Rouvrir un cours")
        fichier = st.file_uploader("Fichier cours_final.json d'une génération précédente", type="json",
                                   help="Régénère les documents Word sans appeler l'API.")
        if fichier is not None and st.session_state.get("json_charge") != fichier.file_id:
            rouvrir(fichier)
    return cle, modeles, relectures


# --------------------------------------------------------------------------- génération

def contexte_formulaire(classe, discipline, duree):
    code = discipline if discipline == "EMC" else discipline.lower()
    return Contexte(CLASSE_CODE.get(classe), code, duree_effective(duree))


def construire_demande(classe, specialite, discipline, theme, duree, format_, precisions):
    demande = f"{classe}"
    if specialite.strip():
        demande += f" {specialite.strip()}"
    demande += f", {discipline.lower()}, thème : {theme.strip()}, {duree}, {format_}"
    if precisions.strip():
        demande += f". Précisions du professeur : {precisions.strip()}"
    return demande


def memoriser(demande, dossier_sortie, fichiers, livre, rapports, dossier, graphe=None):
    """Garde en session le contenu des fichiers (le dossier temporaire peut ensuite disparaître)."""
    st.session_state["resultat"] = {
        "demande": demande,
        "fichiers": {f.name: f.read_bytes() for f in fichiers},
        "json": (Path(dossier_sortie) / "cours_final.json").read_bytes()
        if (Path(dossier_sortie) / "cours_final.json").exists() else None,
        "livre": livre,
        "rapports": rapports,
        "dossier": dossier,
        "date": datetime.now().strftime("%Y%m%d_%H%M"),
        "graphe": graphe,
    }


def tableau_de_bord(titre, suivi, modeles):
    """Encadré d'avancement (barre, graphe, journal) branché sur le moteur. Retourne (statut, avancement)."""
    statut = st.status(titre, expanded=True)
    with statut:
        barre = st.progress(0.0, text="Préparation")
        zone_graphe = st.empty()
        legende()
        zone_journal = st.empty()
    lignes = []

    def journal(message):
        lignes.append(message)
        zone_journal.code("\n".join(lignes[-6:]), language=None)

    def avancement(fraction, libelle):
        barre.progress(fraction, text=libelle)

    def dessiner(suivi_):
        zone_graphe.graphviz_chart(suivi_.to_dot(), use_container_width=True)

    suivi.on_change = dessiner
    dessiner(suivi)
    cw.configurer_session(modeles, journal=journal, evenements=suivi.recevoir)
    return statut, avancement


def generer(cle, modeles, relectures, demande, contexte=None):
    suivi = SuiviWorkflow()
    statut, avancement = tableau_de_bord("Génération du cours en cours… (plusieurs minutes, ne fermez pas la page)",
                                         suivi, modeles)
    with tempfile.TemporaryDirectory(prefix="vibeprof_") as tmp:
        try:
            res = cw.generer_cours(cw.make_client(cle), demande, Path(tmp), relectures, avancement=avancement,
                                   contexte=contexte)
        except cw.GenerationError as exc:
            suivi.marquer_erreur(str(exc))
            statut.update(label="La génération a échoué", state="error", expanded=True)
            st.error(f"{exc}\n\nVérifiez votre clé API et réessayez. Si le problème persiste, il peut venir du "
                     "nom d'un modèle (réglages avancés).")
            partiel = Path(exc.outdir) / "cours_final.json"
            if partiel.exists():
                st.download_button("Télécharger les productions partielles (JSON)", partiel.read_bytes(),
                                   "cours_partiel.json", "application/json")
            return
        finally:
            cw.configurer_session()  # ne pas garder le journal de l'interface dans ce fil
        memoriser(demande, tmp, res["fichiers"], res["livre"], res["rapports"], res["dossier"], suivi.to_dot())
    statut.update(label="Cours généré", state="complete", expanded=False)


# --------------------------------------------------------------------------- génération pas à pas

def parties_etape(boucle):
    return cw.ETAPES_VALIDATION[boucle["etape"]]["parties"]


def executer(boucle, cle, modeles, titre, action):
    """Lance `action(client, avancement)` avec l'encadré d'avancement. Retourne False (et affiche l'erreur)
    en cas d'échec ; le dossier déjà produit est conservé pour pouvoir réessayer."""
    suivi = boucle["suivi"]
    statut, avancement = tableau_de_bord(titre, suivi, modeles)
    try:
        action(cw.make_client(cle), avancement)
    except Exception as exc:
        suivi.marquer_erreur(str(exc))
        statut.update(label="La génération a échoué", state="error", expanded=True)
        st.error(f"{exc}\n\nVérifiez votre clé API et réessayez : ce qui a déjà été rédigé est conservé.")
        st.download_button("Télécharger les productions partielles (JSON)",
                           json.dumps(boucle["outputs"], ensure_ascii=False, indent=2), "cours_partiel.json",
                           "application/json", key="partiel_boucle")
        return False
    finally:
        cw.configurer_session()  # ne pas garder le journal de l'interface dans ce fil
        suivi.on_change = None   # le suivi reste en session : pas de référence aux éléments de cette page
    statut.update(label="Étape terminée", state="complete", expanded=False)
    return True


def demarrer_pas_a_pas(cle, modeles, demande, contexte):
    boucle = {"demande": demande, "outputs": cw.demarrer_dossier(demande, contexte), "etape": 0,
              "suivi": SuiviWorkflow(), "controles": [], "version": 0}

    def action(client, avancement):
        avancement(0.0, "Rédaction jusqu'à l'étape de validation 1")
        cw.avancer_pipeline(client, boucle["outputs"], jusqu_a=parties_etape(boucle)[-1])
        cw.mettre_en_attente(0)
        boucle["controles"] = cw.controles_du_dossier(boucle["outputs"])
        avancement(1.0, "En attente de votre validation")

    if executer(boucle, cle, modeles, "Rédaction de la première étape… (ne fermez pas la page)", action):
        st.session_state["boucle"] = boucle
        st.rerun()


def appliquer_retours(boucle, cle, modeles, commentaires):
    def action(client, avancement):
        for i, (nom, texte) in enumerate(commentaires.items()):
            avancement(i / len(commentaires), f"Modification : {cw.AGENTS_BY_NAME[nom]['title']}")
            boucle["controles"] = cw.reviser_partie(client, boucle["outputs"], nom, texte)
        cw.mettre_en_attente(boucle["etape"])
        avancement(1.0, "En attente de votre validation")

    if executer(boucle, cle, modeles, "Prise en compte de vos modifications…", action):
        boucle["version"] += 1  # nouvelles zones de commentaire, vides
        st.rerun()


def valider_et_continuer(boucle, cle, modeles, relectures):
    suivante = boucle["etape"] + 1
    if suivante < len(cw.ETAPES_VALIDATION):
        def action(client, avancement):
            cw.valider_etape(boucle["etape"])
            avancement(0.0, f"Rédaction jusqu'à l'étape de validation {suivante + 1}")
            cw.avancer_pipeline(client, boucle["outputs"], jusqu_a=cw.ETAPES_VALIDATION[suivante]["parties"][-1])
            cw.mettre_en_attente(suivante)
            boucle["controles"] = cw.controles_du_dossier(boucle["outputs"])
            avancement(1.0, "En attente de votre validation")

        if executer(boucle, cle, modeles, "Rédaction de l'étape suivante… (ne fermez pas la page)", action):
            boucle["etape"] = suivante
            st.rerun()
        return

    with tempfile.TemporaryDirectory(prefix="vibeprof_") as tmp:
        def action(client, avancement):
            cw.valider_etape(boucle["etape"])
            res = cw.finaliser_cours(client, boucle["outputs"], Path(tmp), relectures, avancement=avancement)
            memoriser(boucle["demande"], tmp, res["fichiers"], res["livre"], res["rapports"], res["dossier"],
                      boucle["suivi"].to_dot())

        ok = executer(boucle, cle, modeles,
                      "Rédaction de la fin du cours et relecture… (plusieurs minutes, ne fermez pas la page)", action)
    if ok:
        del st.session_state["boucle"]
        st.rerun()


def afficher_validation(boucle, cle, modeles, relectures):
    etape = cw.ETAPES_VALIDATION[boucle["etape"]]
    st.divider()
    st.subheader(f"🧑‍🏫 Étape {boucle['etape'] + 1}/{len(cw.ETAPES_VALIDATION)} : {etape['titre']}")
    st.markdown("Relisez cette partie avant que la suite du cours soit rédigée. Si quelque chose ne convient "
                "pas, écrivez ce qu'il faut modifier : la partie sera refaite, puis vous pourrez la relire à "
                "nouveau. Sinon, validez pour continuer.")
    with st.expander("Parcours du workflow"):
        st.graphviz_chart(boucle["suivi"].to_dot(), use_container_width=True)
        legende()

    commentaires = {}
    for nom in etape["parties"]:
        agent = cw.AGENTS_BY_NAME[nom]
        st.markdown(f"#### {agent['title']}")
        with st.container(border=True, height=450):
            st.markdown(reduire_titres(boucle["outputs"].get(nom, "")))
        precedents = (boucle["outputs"].get("_retours_professeur") or {}).get(nom) or []
        if precedents:
            st.caption("Déjà demandé : " + " · ".join(precedents))
        texte = st.text_area(f"Ce qu'il faut modifier — {agent['title']} (facultatif)", height=80,
                             max_chars=800, key=f"retour_{nom}_{boucle['version']}",
                             placeholder="ex : problématique plus concrète, partir d'un exemple local")
        if texte.strip():
            commentaires[nom] = texte.strip()

    afficher_controles(boucle["controles"])

    c1, c2, c3 = st.columns([2, 2, 1])
    appliquer = c1.button("✎ Appliquer mes modifications", use_container_width=True, key="appliquer")
    dernier = boucle["etape"] + 1 == len(cw.ETAPES_VALIDATION)
    valider = c2.button("✓ Valider et terminer le cours" if dernier else "✓ Valider et continuer",
                        type="primary", use_container_width=True, key="valider")
    abandonner = c3.button("Abandonner", use_container_width=True, key="abandonner")

    if abandonner:
        del st.session_state["boucle"]
        st.rerun()
    elif appliquer:
        if not commentaires:
            st.warning("Écrivez d'abord ce qu'il faut modifier dans au moins une zone de commentaire.")
        elif not cle:
            st.error("Saisissez votre clé API Mistral dans la barre latérale.")
        else:
            appliquer_retours(boucle, cle, modeles, commentaires)
    elif valider:
        if commentaires:
            st.warning("Vous avez écrit des modifications : cliquez sur « Appliquer mes modifications », ou "
                       "videz les zones de commentaire pour valider la partie telle quelle.")
        elif not cle:
            st.error("Saisissez votre clé API Mistral dans la barre latérale.")
        else:
            valider_et_continuer(boucle, cle, modeles, relectures)


def rouvrir(fichier):
    try:
        data = json.loads(fichier.getvalue().decode("utf-8"))
        data["demande"], data["dossier"]  # champs obligatoires
    except Exception:
        st.sidebar.error("Ce fichier n'est pas un cours_final.json valide.")
        return
    cw.configurer_session()
    with tempfile.TemporaryDirectory(prefix="vibeprof_") as tmp:
        source = Path(tmp) / "cours_final.json"
        source.write_bytes(fichier.getvalue())
        fichiers = cw.rendre_depuis_json(source)
        memoriser(data["demande"], tmp, fichiers, bool(data.get("livre")),
                  data.get("rapports_relecture") or [], data["dossier"])
    st.session_state["json_charge"] = fichier.file_id


# --------------------------------------------------------------------------- affichage du résultat

def reduire_titres(markdown, decalage=3):
    """Aperçu : titres markdown rétrogradés (# → ####) pour rester à l'échelle de la page."""
    return re.sub(r"^(#{1,6})(\s)", lambda m: "#" * min(len(m.group(1)) + decalage, 6) + m.group(2),
                  markdown or "", flags=re.MULTILINE)


def legende():
    st.caption("⬜ en attente · 🟦 en cours · 🟪 à valider par le professeur · 🟨 correction · 🟩 terminé · "
               "🟥 erreur — flèches pointillées : renvois du relecteur (jaune) et retours du professeur (violet)")


def afficher_controles(liste):
    with st.expander(f"Contrôles automatiques ({len(liste)} point(s) à vérifier)" if liste
                     else "Contrôles automatiques : aucun problème détecté"):
        st.caption("Vérifiés par le programme : durées, documents prévus et produits, capacités officielles, "
                   "objectifs évalués, sources, longueurs.")
        for c in liste:
            c = c if isinstance(c, dict) else c.to_dict()
            icone = "⛔" if c["gravite"] == "bloquant" else "⚠️"
            st.markdown(f"{icone} **{cw.AGENTS[c['agent'] - 1]['title']}** — {c['message']}")


def archive_zip(res):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, contenu in res["fichiers"].items():
            z.writestr(nom, contenu)
        if res["json"]:
            z.writestr("cours_final.json", res["json"])
    return tampon.getvalue()


def afficher_resultat(res):
    st.divider()
    titre = cw.session_title(res["dossier"], res["demande"])
    st.subheader(f"✅ {titre}")
    st.caption(res["demande"])

    if res["rapports"]:
        dernier = res["rapports"][-1]
        score = dernier.get("score_global")
        if res["livre"]:
            st.success(f"Contrôle qualité : {score}/5 après {len(res['rapports'])} relecture(s).")
        else:
            st.warning(f"Contrôle qualité : {score}/5, sous le seuil de {cw.SEUIL_LIVRAISON}/5. "
                       "Relisez attentivement le cours avant de l'utiliser (détails dans la fiche professeur).")

        afficher_controles(dernier.get("controles") or [])

    if res.get("graphe"):
        with st.expander("Parcours du workflow"):
            st.graphviz_chart(res["graphe"], use_container_width=True)
            legende()

    st.markdown("#### Télécharger")
    st.download_button("📦 Tout télécharger (.zip)", archive_zip(res), f"vibeprof_{res['date']}.zip",
                       "application/zip", type="primary", use_container_width=True)
    colonnes = st.columns(2)
    for i, (nom, (libelle, aide)) in enumerate(LIBELLES.items()):
        if nom in res["fichiers"]:
            colonnes[i % 2].download_button(f"📄 {libelle}", res["fichiers"][nom], nom, DOCX_MIME,
                                            help=aide, use_container_width=True, key=f"dl_{nom}")
    if res["json"]:
        st.caption("Gardez aussi le fichier `cours_final.json` (inclus dans le .zip) : il permet de rouvrir ce "
                   "cours plus tard depuis la barre latérale.")

    st.markdown("#### Aperçu")
    dossier = res["dossier"]
    docs_eleve, docs_prof = cw.split_parties(dossier.get("5_documents_eleves", ""))
    eval_eleve, eval_prof = cw.split_parties(dossier.get("6_evaluation", ""))
    onglets = st.tabs(["Cours", "Documents", "Évaluation", "Déroulé", "Cadrage", "Corrigés", "Programme"])
    contenus = [
        dossier.get("4_support_cours", ""),
        docs_eleve or "_Non séparé : voir la fiche professeur._",
        eval_eleve or "_Non séparé : voir la fiche professeur._",
        dossier.get("3_deroule", ""),
        dossier.get("2_cadrage", ""),
        f"# Documents\n\n{docs_prof}\n\n# Évaluation\n\n{eval_prof}",
        dossier.get("1_referentiel_officiel", ""),
    ]
    for onglet, contenu in zip(onglets, contenus):
        with onglet:
            with st.container(border=True, height=600):
                st.markdown(reduire_titres(contenu))


# --------------------------------------------------------------------------- page

def main():
    controle_acces()
    cle, modeles, relectures = barre_laterale()

    st.title("📚 VibeProf")
    st.markdown("Créez une séance d'**histoire-géographie-EMC pour le lycée professionnel**, ancrée dans le "
                "programme officiel : fiche professeur, cours, documents et évaluation prêts à imprimer.")

    verrou = "boucle" in st.session_state  # un cours est en cours de validation : formulaire figé
    with st.container(border=True):
        c1, c2 = st.columns(2)
        classe = c1.selectbox("Classe", CLASSES, index=2, key="classe", disabled=verrou)
        specialite = c2.text_input("Spécialité", key="specialite", disabled=verrou,
                                   placeholder="ex : Métiers du commerce et de la vente")
        discipline = st.radio("Discipline", DISCIPLINES, horizontal=True, key="discipline", disabled=verrou)
        contexte = contexte_formulaire(classe, discipline, "")
        themes = THEMES_OFFICIELS.get((contexte.classe, contexte.discipline), [])
        choix = st.selectbox("Thème du programme officiel", themes + [AUTRE_THEME], key="theme_officiel",
                             disabled=verrou,
                             help="Thèmes des programmes en vigueur pour cette classe et cette discipline.")
        theme = choix
        if choix == AUTRE_THEME:
            theme = st.text_input("Thème de la séance *", key="theme", disabled=verrou,
                                  placeholder="ex : une étude de cas sur un port de commerce")
        c3, c4 = st.columns(2)
        duree = c3.selectbox("Durée", DUREES, index=3, key="duree", disabled=verrou,
                             format_func=lambda d: f"{d} ({duree_effective(d)} min de cours)",
                             help="Une heure de cours compte 55 minutes.")
        format_ = c4.selectbox("Format", FORMATS, key="format", disabled=verrou)
        precisions = st.text_area("Précisions (facultatif)", height=80, max_chars=800, key="precisions",
                                  disabled=verrou,
                                  placeholder="ex : classe avec plusieurs élèves allophones ; insister sur la carte")
        pas_a_pas = st.checkbox("Valider le cadrage et le déroulé avant la suite", value=True,
                                key="validation_etapes", disabled=verrou,
                                help="La génération s'arrête après le cadrage, puis après le déroulé : vous "
                                     "relisez, demandez des modifications si besoin, puis validez.")
        envoye = st.button("Générer le cours", type="primary", use_container_width=True, disabled=verrou)

    if envoye:
        if not theme.strip():
            st.error("Indiquez le thème de la séance.")
        elif not cle:
            st.error("Saisissez votre clé API Mistral dans la barre latérale.")
        else:
            st.session_state.pop("resultat", None)
            demande = construire_demande(classe, specialite, discipline, theme, duree, format_, precisions)
            if pas_a_pas:
                demarrer_pas_a_pas(cle, modeles, demande, contexte_formulaire(classe, discipline, duree))
            else:
                generer(cle, modeles, relectures, demande, contexte_formulaire(classe, discipline, duree))

    if "boucle" in st.session_state:
        afficher_validation(st.session_state["boucle"], cle, modeles, relectures)
    elif "resultat" in st.session_state:
        afficher_resultat(st.session_state["resultat"])

main()
