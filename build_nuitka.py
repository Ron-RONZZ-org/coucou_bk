#!/usr/bin/env python3
"""
Script de compilation Nuitka pour l'application Coucou
Optimisé pour PySide6 et les dépendances spécifiques
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def clean_build():
    """Nettoie les anciens builds"""
    build_dirs = ["build", "main.dist", "main.build"]
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            print(f"🧹 Nettoyage de {dir_name}")
            shutil.rmtree(dir_name)


def get_nuitka_command():
    """Construit la commande Nuitka optimisée pour Coucou"""

    # Modules à inclure explicitement (seulement ceux qui existent vraiment)
    include_modules = [
        "PySide6",
        "toml",
        "gtts",
        "mlconjug3",
        "yaml",  # Le vrai nom du package est 'yaml', pas 'pyyaml'
        "joblib",
        "defusedxml",
        "click",
        "sklearn",  # Le vrai nom du package est 'sklearn', pas 'scikit_learn'
        "numpy",
        "rich",
        "pydub",
    ]

    # Modules locaux de votre application
    local_modules = [
        "retrieval",
        "record_manager",
        "massImporter",
        "massExporter",
        "db",
        "conjugator",
        "logger",
        "usage_statistics",
        "common_methods",
        "missing_responses_dialog",
        "addition",
        "settings_dialog",
    ]

    # Construction de la commande
    cmd = [
        "python",
        "-m",
        "nuitka",
        "--standalone",  # Crée un exécutable autonome
        "--enable-plugin=pyside6",  # Plugin PySide6
        "--show-progress",  # Affiche la progression
        "--warn-implicit-exceptions",  # Avertissements utiles
        "--warn-unusual-code",
        "--assume-yes-for-downloads",  # Télécharge automatiquement les dépendances
        "--output-filename=coucou",  # Nom de l'exécutable
        "--output-dir=dist",  # Dossier de sortie
        "--remove-output",  # Supprime l'ancien build
        # Optimisations
        "--lto=yes",  # Link Time Optimization
        "--jobs=4",  # Utilise 4 processeurs
        # Inclusions explicites des packages système
        "--include-package=PySide6",
        "--include-package=sqlite3",
        # Fichiers de données à inclure (seulement s'ils existent)
        "--include-data-files=config.toml=config.toml",
        # Script principal
        "main.py",
    ]

    # Ajouter les fichiers de données seulement s'ils existent
    if os.path.exists("data.db"):
        cmd.append("--include-data-files=data.db=data.db")
    if os.path.exists("assets"):
        cmd.append("--include-data-dir=assets=assets")

    # Ajouter les modules locaux
    for module in local_modules:
        if os.path.exists(f"{module}.py"):
            cmd.append(f"--include-module={module}")

    # Ajouter les modules externes
    for module in include_modules:
        cmd.append(f"--include-package={module}")

    return cmd


def build():
    """Lance la compilation"""
    print("🚀 Démarrage de la compilation Nuitka pour Coucou")
    print("=" * 60)

    # Vérification des prérequis
    if not os.path.exists("main.py"):
        print("❌ Erreur : main.py non trouvé")
        return False

    # Nettoyage
    clean_build()

    # Construction de la commande
    cmd = get_nuitka_command()

    print("📝 Commande Nuitka :")
    print(" ".join(cmd))
    print("=" * 60)

    # Lancement de la compilation
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("✅ Compilation réussie !")
        print("📁 L'exécutable se trouve dans : dist/coucou")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur de compilation : {e}")
        return False
    except KeyboardInterrupt:
        print("\n⏹️  Compilation interrompue par l'utilisateur")
        return False


def post_build():
    """Actions post-compilation"""
    dist_dir = Path("dist")
    if dist_dir.exists():
        print("\n📦 Post-traitement :")

        # Vérifier la taille
        executable = dist_dir / "coucou"
        if executable.exists():
            size_mb = executable.stat().st_size / (1024 * 1024)
            print(f"   📏 Taille de l'exécutable : {size_mb:.1f} MB")

        # Copier les fichiers de configuration si nécessaire
        config_files = ["config.toml", "francophonie.db", "tatoeba-fr.db"]
        for config_file in config_files:
            if os.path.exists(config_file):
                dest = dist_dir / config_file
                if not dest.exists():
                    shutil.copy2(config_file, dest)
                    print(f"   📄 Copié : {config_file}")


if __name__ == "__main__":
    print("🏗️  Script de compilation Nuitka pour Coucou")
    print(f"🐍 Python : {sys.version}")
    print(f"📁 Répertoire : {os.getcwd()}")
    print()

    if build():
        post_build()
        print("\n🎉 Compilation terminée avec succès !")
        print("🚀 Vous pouvez maintenant exécuter : ./dist/coucou")
    else:
        print("\n💥 Échec de la compilation")
        sys.exit(1)
