#!/bin/bash
# Lance l'interface VibeProf (macOS / Linux) : double-cliquez sur ce fichier (ou ./lancer_vibeprof.command).
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python n'est pas installé. Installez-le depuis https://www.python.org/downloads/ puis relancez."
    read -r -p "Appuyez sur Entrée pour fermer."
    exit 1
fi
if [ ! -d .venv ]; then
    echo "Première utilisation : installation, patientez quelques minutes..."
    python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --quiet --upgrade -r requirements.txt
echo "VibeProf s'ouvre dans votre navigateur. Fermez cette fenêtre pour arrêter."
python -m streamlit run app.py
