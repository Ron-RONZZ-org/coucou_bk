#!/usr/bin/env python3
"""
Script de compilation Nuitka SIMPLIFIÉ pour l'application Coucou
Version robuste avec gestion d'erreurs améliorée
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def clean_build():
    """Nettoie les anciens builds"""
    build_dirs = ["build", "main.dist", "main.build", "dist"]
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            print(f"🧹 Nettoyage de {dir_name}")
            shutil.rmtree(dir_name)


def check_dependencies():
    """Vérifie que les dépendances principales sont disponibles"""
    try:
        import PySide6
        print(f"✅ PySide6 trouvé : {PySide6.__version__}")
    except ImportError:
        print("❌ PySide6 non trouvé")
        return False
    
    try:
        import toml
        print("✅ toml trouvé")
    except ImportError:
        print("❌ toml non trouvé") 
        return False
    
    return True


def get_simple_nuitka_command():
    """Commande Nuitka simplifiée et robuste"""
    
    cmd = [
        "python", "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--show-progress", 
        "--assume-yes-for-downloads",
        "--output-filename=coucou",
        "--output-dir=dist",
        "--remove-output",
        # Inclusions minimales mais essentielles
        "--include-package=PySide6",
        "--include-package=sqlite3",
        "--include-package=toml",
        # Fichier de config obligatoire
        "--include-data-files=config.toml=config.toml",
        # Script principal
        "main.py"
    ]
    
    # Ajouter les fichiers optionnels s'ils existent
    if os.path.exists("data.db"):
        cmd.append("--include-data-files=data.db=data.db")
        print("📄 data.db sera inclus")
    
    if os.path.exists("assets"):
        cmd.append("--include-data-dir=assets=assets")
        print("📁 Le dossier assets sera inclus")
    
    return cmd


def build():
    """Lance la compilation"""
    print("🚀 Compilation Nuitka SIMPLIFIÉE pour Coucou")
    print("=" * 50)
    
    # Vérifications
    if not os.path.exists("main.py"):
        print("❌ Erreur : main.py non trouvé")
        return False
    
    if not os.path.exists("config.toml"):
        print("❌ Erreur : config.toml non trouvé")
        return False
    
    if not check_dependencies():
        print("❌ Erreur : Dépendances manquantes")
        return False
    
    # Nettoyage
    clean_build()
    
    # Construction de la commande
    cmd = get_simple_nuitka_command()
    
    print("\n📝 Commande Nuitka :")
    print(" ".join(cmd))
    print("=" * 50)
    print("⏳ Compilation en cours... (cela peut prendre 5-15 minutes)")
    
    # Lancement de la compilation
    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ Compilation réussie !")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Erreur de compilation : {e}")
        print("\n💡 Conseils pour résoudre l'erreur :")
        print("   1. Vérifiez que tous les modules importés dans main.py sont installés")
        print("   2. Essayez de lancer l'application normalement avec 'python main.py'")
        print("   3. Consultez les logs d'erreur ci-dessus")
        return False
    except KeyboardInterrupt:
        print("\n⏹️  Compilation interrompue par l'utilisateur")
        return False


def post_build():
    """Actions post-compilation"""
    dist_dir = Path("dist")
    if not dist_dir.exists():
        return
    
    print("\n📦 Post-traitement :")
    
    # Vérifier l'exécutable
    executable = dist_dir / "coucou"
    if executable.exists():
        size_mb = executable.stat().st_size / (1024 * 1024)
        print(f"   📏 Taille de l'exécutable : {size_mb:.1f} MB")
        
        # Rendre exécutable
        os.chmod(executable, 0o755)
        print("   🔧 Permissions d'exécution définies")
    
    # Copier les bases de données supplémentaires si elles existent
    extra_dbs = ["francophonie.db", "tatoeba-fr.db"]
    for db_file in extra_dbs:
        if os.path.exists(db_file):
            dest = dist_dir / db_file
            if not dest.exists():
                shutil.copy2(db_file, dest)
                print(f"   📄 Copié : {db_file}")


if __name__ == "__main__":
    print("🏗️  Script de compilation Nuitka SIMPLIFIÉ")
    print(f"🐍 Python : {sys.version}")
    print(f"📁 Répertoire : {os.getcwd()}")
    print()
    
    if build():
        post_build()
        print("\n🎉 Compilation terminée avec succès !")
        print("🚀 Pour tester l'exécutable :")
        print("   cd dist && ./coucou")
    else:
        print("\n💥 Échec de la compilation")
        print("💡 Essayez d'abord de lancer 'python main.py' pour vérifier que l'app fonctionne")
        sys.exit(1)
