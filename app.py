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
from suivi_workflow import SuiviWorkflow

st.set_page_config(page_title="VibeProf", page_icon="📚", layout="centered")

CLASSES = ["Seconde bac pro", "Première bac pro", "Terminale bac pro", "CAP 1re année", "CAP 2e année"]
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

        st.divider()
        st.subheader("Rouvrir un cours")
        fichier = st.file_uploader("Fichier cours_final.json d'une génération précédente", type="json",
                                   help="Régénère les documents Word sans appeler l'API.")
        if fichier is not None and st.session_state.get("json_charge") != fichier.file_id:
            rouvrir(fichier)
    return cle, modeles, relectures


# --------------------------------------------------------------------------- génération

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


def generer(cle, modeles, relectures, demande):
    statut = st.status("Génération du cours en cours… (plusieurs minutes, ne fermez pas la page)", expanded=True)
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

    suivi = SuiviWorkflow(on_change=dessiner)
    dessiner(suivi)
    cw.configurer_session(modeles, journal=journal, evenements=suivi.recevoir)
    with tempfile.TemporaryDirectory(prefix="vibeprof_") as tmp:
        try:
            res = cw.generer_cours(cw.make_client(cle), demande, Path(tmp), relectures, avancement=avancement)
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
    st.caption("⬜ en attente · 🟦 en cours · 🟨 correction demandée par le relecteur · 🟩 terminé · 🟥 erreur "
               "— flèches pointillées : renvois du relecteur")


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

    with st.form("demande"):
        c1, c2 = st.columns(2)
        classe = c1.selectbox("Classe", CLASSES, index=2)
        specialite = c2.text_input("Spécialité", key="specialite", placeholder="ex : Métiers du commerce et de la vente")
        discipline = st.radio("Discipline", DISCIPLINES, horizontal=True)
        theme = st.text_input("Thème de la séance *", key="theme",
                              placeholder="ex : La France et l'Union européenne dans la mondialisation")
        c3, c4 = st.columns(2)
        duree = c3.selectbox("Durée", DUREES, index=3)
        format_ = c4.selectbox("Format", FORMATS)
        precisions = st.text_area("Précisions (facultatif)", height=80,
                                  placeholder="ex : classe avec plusieurs élèves allophones ; insister sur la carte")
        envoye = st.form_submit_button("Générer le cours", type="primary", use_container_width=True)

    if envoye:
        if not theme.strip():
            st.error("Indiquez le thème de la séance.")
        elif not cle:
            st.error("Saisissez votre clé API Mistral dans la barre latérale.")
        else:
            st.session_state.pop("resultat", None)
            generer(cle, modeles, relectures,
                    construire_demande(classe, specialite, discipline, theme, duree, format_, precisions))

    if "resultat" in st.session_state:
        afficher_resultat(st.session_state["resultat"])


main()
