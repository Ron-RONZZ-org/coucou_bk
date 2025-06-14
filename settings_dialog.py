from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
    QComboBox,
)
from PySide6.QtCore import Qt
import os
import toml


class SettingsDialog(QDialog):
    def __init__(self, parent=None, app_dir=None, current_db=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres")
        self.resize(420, 440)
        self.app_dir = app_dir or os.getcwd()
        self.selected_db = None
        self.selected_username = None
        self.selected_language_code = None
        layout = QVBoxLayout(self)
        # Titre principal
        title = QLabel("Paramètres de l'application")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #1976d2; margin-bottom: 12px;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        # Section base de données
        db_section = QLabel("Changer la base de données utilisée :")
        db_section.setStyleSheet("font-size: 15px; font-weight: bold; margin-top: 8px;")
        layout.addWidget(db_section)
        self.list_widget = QListWidget()
        db_files = [f for f in os.listdir(self.app_dir) if f.endswith(".db")]
        self.list_widget.addItems(db_files)
        if current_db and os.path.basename(current_db) in db_files:
            self.list_widget.setCurrentRow(db_files.index(os.path.basename(current_db)))
        layout.addWidget(self.list_widget)
        self.custom_path_edit = QLineEdit()
        self.custom_path_edit.setPlaceholderText("Ou entrez un chemin personnalisé...")
        layout.addWidget(self.custom_path_edit)

        # Charger la config pour pré-remplir username et language_code
        config_path = os.path.join(self.app_dir, "config.toml")
        try:
            config = toml.load(config_path)
            current_username = config.get("username", "")
            current_language_code = config.get("language_code", "fr")
        except Exception:
            current_username = ""
            current_language_code = "fr"

        user_section = QLabel("Nom d'utilisateur :")
        user_section.setStyleSheet(
            "font-size: 15px; font-weight: bold; margin-top: 12px;"
        )
        layout.addWidget(user_section)
        self.username_edit = QLineEdit()
        self.username_edit.setText(current_username)
        self.username_edit.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.username_edit)

        lang_section = QLabel("Code langue :")
        lang_section.setStyleSheet(
            "font-size: 15px; font-weight: bold; margin-top: 12px;"
        )
        layout.addWidget(lang_section)
        self.language_code_combo = QComboBox()
        self.language_code_combo.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.language_code_combo.addItems(
            ["fr", "en", "es", "de", "it", "zh", "ja", "ru"]
        )
        idx = self.language_code_combo.findText(current_language_code)
        if idx >= 0:
            self.language_code_combo.setCurrentIndex(idx)
        else:
            self.language_code_combo.setCurrentText(current_language_code)
        layout.addWidget(self.language_code_combo)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        layout.addWidget(self.button_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def get_selected_db(self):
        if self.list_widget.currentItem():
            return os.path.join(self.app_dir, self.list_widget.currentItem().text())
        elif self.custom_path_edit.text().strip():
            return self.custom_path_edit.text().strip()
        return None

    def accept(self):
        db_path = self.get_selected_db()
        username = self.username_edit.text().strip()
        language_code = self.language_code_combo.currentText().strip()
        if not db_path or not os.path.exists(db_path):
            QMessageBox.warning(self, "Erreur", "Base de données introuvable.")
            return
        if not username:
            QMessageBox.warning(
                self, "Erreur", "Le nom d'utilisateur ne peut pas être vide."
            )
            return
        if not language_code:
            QMessageBox.warning(self, "Erreur", "Le code langue ne peut pas être vide.")
            return
        # Vérifier si un changement a eu lieu
        config_path = os.path.join(self.app_dir, "config.toml")
        try:
            config = toml.load(config_path)
            current_db = config.get("database_path", "")
            current_username = config.get("username", "")
            current_language_code = config.get("language_code", "fr")
        except Exception:
            current_db = ""
            current_username = ""
            current_language_code = "fr"
        if (
            os.path.abspath(db_path) == os.path.abspath(current_db)
            and username == current_username
            and language_code == current_language_code
        ):
            QMessageBox.information(
                self, "Aucun changement", "Aucun paramètre n'a été modifié."
            )
            self.selected_db = None
            self.selected_username = None
            self.selected_language_code = None
            self.reject()
            return
        self.selected_db = db_path
        self.selected_username = username
        self.selected_language_code = language_code
        super().accept()
