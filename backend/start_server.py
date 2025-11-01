#!/usr/bin/env python
"""
Script de démarrage pour NextPost Backend
"""
import os
import sys
import subprocess
from pathlib import Path

# Chemin vers le répertoire du projet
PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = PROJECT_ROOT.parent / ".venv" / "Scripts" / "python.exe"

def main():
    """Démarre le serveur Django"""
    # S'assurer qu'on est dans le bon répertoire
    os.chdir(PROJECT_ROOT)
    
    # Vérifier que manage.py existe
    if not (PROJECT_ROOT / "manage.py").exists():
        print("❌ manage.py non trouvé dans", PROJECT_ROOT)
        sys.exit(1)
    
    # Vérifier que l'environnement virtuel existe
    if not VENV_PYTHON.exists():
        print("❌ Environnement virtuel non trouvé:", VENV_PYTHON)
        print("💡 Créez l'environnement virtuel d'abord")
        sys.exit(1)
    
    print("🚀 Démarrage du serveur NextPost...")
    print(f"📂 Répertoire: {PROJECT_ROOT}")
    print(f"🐍 Python: {VENV_PYTHON}")
    
    # Lancer le serveur
    try:
        subprocess.run([
            str(VENV_PYTHON),
            "manage.py",
            "runserver",
            "127.0.0.1:8000"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors du démarrage: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()