@echo off
rem Lance l'interface VibeProf (Windows) : double-cliquez sur ce fichier.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python n'est pas installe. Installez-le depuis https://www.python.org/downloads/
    echo en cochant "Add python.exe to PATH", puis relancez ce fichier.
    pause
    exit /b 1
)
if not exist .venv (
    echo Premiere utilisation : installation, patientez quelques minutes...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade -r requirements.txt
echo VibeProf s'ouvre dans votre navigateur. Fermez cette fenetre pour arreter.
python -m streamlit run app.py
pause
