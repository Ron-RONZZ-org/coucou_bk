main_window = None  # Doit être global et déclaré tout en haut pour la persistance

import sys
import toml
import os
import json
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,  # Ajout de QHBoxLayout pour placer des éléments côte à côte
    QPushButton,
    QWidget,
    QSlider,  # Importer QSlider pour ajuster la taille de police
    QLabel,  # Importer QLabel pour afficher la taille actuelle
    QSplashScreen,  # Importer QSplashScreen pour le SplashScreen
)
from PySide6.QtCore import Qt  # Importer Qt pour l'orientation du slider
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,  # Déplacé ici depuis PySide6.QtWidgets
    QPixmap,  # Importer QPixmap pour le SplashScreen
)
from retrieval import RetrievalApp  # Importer RetrievalApp
from record_manager import RecordManagerApp  # Importer RecordManagerApp
from massImporter import MassImporter  # Importer MassImporter
# from massExporter import massExporter  # Importer massExporter
from db import DatabaseManager  # Importer DatabaseManager
from conjugator import ConjugatorApp  # Importer ConjugatorApp
from logger import logger  # Importer le logger centralisé
from usage_statistics import StatisticsApp  # Importer la fenêtre de statistiques
from common_methods import DialogUtils


class MainApp(QMainWindow):
    def __init__(self, selected_db_path=None):
        print(f"[DEBUG] MainApp.__init__ called, selected_db_path={selected_db_path}")
        super().__init__()
        self.setWindowTitle("Coucou")
        self.font_size, self.username, self.language_code, self.database_path = (
            self.load_config()
        )
        # Si un chemin de base de données a été sélectionné, on l'utilise en priorité
        if selected_db_path:
            self.database_path = selected_db_path
        print(f"[DEBUG] MainApp: database_path={self.database_path}")
        self.db_manager = DatabaseManager(self.database_path, self.language_code)
        logger.info("Application démarrée")
        self.show_resume_manual_button = False
        self.resume_manual_button = None  # Référence au bouton
        self._pending_manual_entries = None
        # Import local pour éviter les effets de bord
        from missing_responses_dialog import MissingResponsesDialog

        self.progress_file = getattr(
            MissingResponsesDialog, "PROGRESS_FILE", ".missing_responses_progress.json"
        )
        if os.path.exists(self.progress_file):
            from PySide6.QtWidgets import QMessageBox

            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    entries = data.get("entries", [])
                self._pending_manual_entries = entries
                reply = QMessageBox.question(
                    self,
                    "Reprendre la saisie manuelle?",
                    "Un progrès précédent de saisie manuelle a été détecté. Voulez-vous reprendre là où vous vous étiez arrêté?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self.show_resume_manual_button = False
                else:
                    self.show_resume_manual_button = True
            except Exception as e:
                logger.error(f"Erreur lors de la lecture du fichier de progrès: {e}")
                self._pending_manual_entries = None
                self.show_resume_manual_button = False

        # Vérifier s'il y a des entrées en attente dans la file d'attente d'addition
        self._check_addition_queue_on_startup()

        self.setStyleSheet(f"* {{ font-size: {self.font_size}px; }}")
        self.setup_ui()
        self.showMaximized()
        # Si l'utilisateur a dit Oui, ouvrir la fenêtre d'addition pour reprendre le dialog
        if self._pending_manual_entries and not self.show_resume_manual_button:
            self.open_addition_window_with_resume()

    def load_config(self):
        """Charge la taille de police depuis le fichier config.toml."""
        try:
            config = toml.load("config.toml")
            logger.info("Configuration chargée avec succès")
            return (
                config.get("font_size", 12),
                config.get("username", ""),
                config.get("language_code", "fr"),
                config.get("database_path", "data.db"),
            )
            # 12, "" sont les valeurs par défaut si non trouvée
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la configuration: {e}")
            return 12, ""  # Valeur par défaut en cas d'erreur

    def save_font_size_to_config(self, font_size):
        """Sauvegarde la taille de police dans le fichier config.toml."""
        try:
            config = toml.load("config.toml")  # Charger la configuration existante
            config["font_size"] = font_size  # Mettre à jour la taille de police
            with open("config.toml", "w") as f:
                toml.dump(config, f)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")

    def setup_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()

        # Slider pour ajuster la taille de police
        welcome_label = QLabel(f"Bienvenue, {self.username}!\nRavis de te revoir😃!")
        font_slider_label = QLabel(f"Taille de police: {self.font_size}")
        font_slider = QSlider(Qt.Horizontal)
        font_slider.setMinimum(8)
        font_slider.setMaximum(24)
        font_slider.setValue(self.font_size)
        font_slider.valueChanged.connect(
            lambda value: self.adjust_font_size(value, font_slider_label)
        )

        # Créer un layout horizontal pour le label et le slider
        font_layout = QHBoxLayout()
        font_layout.addWidget(font_slider_label)
        font_layout.addWidget(font_slider)

        layout.addWidget(welcome_label)
        layout.addLayout(font_layout)

        # Bouton pour ouvrir la fonctionnalité de récupération
        retrieve_button = QPushButton(
            "Parcours les éléments (&R)"
        )  # Affiche le raccourci Alt+R
        retrieve_button.clicked.connect(self.open_retrieval_window)
        layout.addWidget(retrieve_button)

        # Bouton pour ouvrir la fonctionnalité de revue automatique
        review_button = QPushButton("Mode revue (&V)")  # Affiche le raccourci Alt+V
        review_button.clicked.connect(self.open_review_window)
        layout.addWidget(review_button)
        # Bouton pour ouvrir la gestion des enregistrements
        manage_button = QPushButton(
            "Gérer les enregistrements (&G)"
        )  # Affiche le raccourci Alt+G
        manage_button.clicked.connect(self.open_record_manager_window)
        layout.addWidget(manage_button)

        # Bouton pour ouvrir la fonctionnalité d'importation en masse
        bulk_import_button = QPushButton(
            "Importer en masse (&I)"
        )  # Affiche le raccourci Alt+I
        bulk_import_button.clicked.connect(self.open_bulk_import_window)
        layout.addWidget(bulk_import_button)

        # # Bouton pour ouvrir la fonctionnalité d'exportation en masse
        # bulk_export_button = QPushButton(
        #     "Exporter en masse (&E)"
        # )  # Affiche le raccourci Alt+E
        # bulk_export_button.clicked.connect(self.open_bulk_export_window)
        # layout.addWidget(bulk_export_button)

        # Bouton pour ouvrir la fenêtre de conjugaison française
        conjugator_button = QPushButton(
            "Conjugateur Français (&C)"
        )  # Affiche le raccourci Alt+C
        conjugator_button.clicked.connect(self.open_conjugator_window)
        layout.addWidget(conjugator_button)

        # Bouton pour ouvrir la fenêtre d'ajout d'élément
        addition_button = QPushButton(
            "Ajouter un élément (&A)"
        )  # Affiche le raccourci Alt+A
        addition_button.clicked.connect(self.open_addition_window)
        layout.addWidget(addition_button)

        # Bouton pour ouvrir la fenêtre de statistiques
        stats_button = QPushButton("Statistiques (&S)")  # Affiche le raccourci Alt+S
        stats_button.clicked.connect(self.open_statistics_window)
        layout.addWidget(stats_button)

        # Bouton pour ouvrir la fenêtre de paramètres
        settings_button = QPushButton("Paramètres (&P)")
        settings_button.clicked.connect(self.open_settings_dialog)
        layout.addWidget(settings_button)

        # Ajout du bouton de reprise de saisie manuelle si nécessaire
        if self.show_resume_manual_button:
            self.resume_manual_button = QPushButton("Reprendre saisir manuel (&M)")
            self.resume_manual_button.setToolTip(
                "Reprendre la saisie manuelle là où vous vous étiez arrêté."
            )
            self.resume_manual_button.clicked.connect(self.open_resume_manual_dialog)
            layout.addWidget(self.resume_manual_button)

        # Ajout du raccourci clavier pour fermer la fenêtre
        close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_shortcut.activated.connect(self.close)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def adjust_font_size(self, value, label):
        """Ajuste la taille de police dans l'application."""
        self.font_size = value
        label.setText(f"Taille de police: {self.font_size}")
        self.setStyleSheet(f"* {{ font-size: {self.font_size}px; }}")
        self.save_font_size_to_config(self.font_size)  # Sauvegarde dans config.toml

    def open_addition_window(self):
        if not hasattr(self, "addition_window") or self.addition_window is None:
            from addition import AudioSaverApp

            self.addition_window = AudioSaverApp(self.db_manager, self.font_size)
        self.addition_window.initialize_ui()
        self.addition_window.show()
        logger.info("Ouverture de la fenêtre d'addition")

    def open_addition_window_with_resume(self):
        """Ouvre la fenêtre d'addition et démarre automatiquement le dialog de reprise."""
        if not hasattr(self, "addition_window") or self.addition_window is None:
            from addition import AudioSaverApp

            self.addition_window = AudioSaverApp(self.db_manager, self.font_size)
        self.addition_window.initialize_ui()
        self.addition_window.show()
        # Demander à la fenêtre d'addition de démarrer le dialog de reprise
        self.addition_window.open_resume_manual_dialog()
        logger.info("Ouverture de la fenêtre d'addition avec reprise du dialog")

    def open_retrieval_window(self):
        """Ouvre la fenêtre RetrievalApp."""
        self.retrieval_window = RetrievalApp(
            self.db_manager, self.font_size
        )  # Passer font_size
        self.retrieval_window.show()
        logger.info("Ouverture de la fenêtre de récupération")

    def open_record_manager_window(self):
        # Vérifiez si la fenêtre existe déjà, sinon créez-la
        if (
            not hasattr(self, "record_manager_window")
            or self.record_manager_window is None
        ):
            self.record_manager_window = RecordManagerApp(
                self.db_manager, self.font_size
            )  # Passer font_size
        self.record_manager_window.show()
        logger.info("Ouverture de la fenêtre de gestion des enregistrements")

    def open_bulk_import_window(self):
        if not hasattr(self, "bulk_import_window") or self.bulk_import_window is None:
            self.bulk_import_window = MassImporter(
                self.db_manager, self.font_size
            )  # Passer font_size
        self.bulk_import_window.show()
        logger.info("Ouverture de la fenêtre d'importation en masse")

    # def open_bulk_export_window(self):
    #     if not hasattr(self, "bulk_export_window") or self.bulk_export_window is None:
    #         self.bulk_export_window = massExporter(
    #             self.db_manager, self.font_size
    #         )  # Passer font_size
    #     self.bulk_export_window.show()
    #     logger.info("Ouverture de la fenêtre d'exportation en masse")

    def open_conjugator_window(self):
        """Ouvre la fenêtre ConjugatorApp."""
        if not hasattr(self, "conjugator_window") or self.conjugator_window is None:
            self.conjugator_window = ConjugatorApp(self.font_size)  # Passer font_size
        self.conjugator_window.show()
        logger.info("Ouverture de la fenêtre du conjugateur")

    def open_review_window(self):
        """Ouvre la fenêtre RetrievalApp en mode revue (auto-remplissage)."""
        self.retrieval_window = RetrievalApp(
            self.db_manager, self.font_size, review_mode=True
        )
        self.retrieval_window.show()
        logger.info("Ouverture de la fenêtre de revue auto")

    def open_statistics_window(self):
        """Ouvre la fenêtre des statistiques d'utilisation."""
        self.statistics_window = StatisticsApp(self.font_size, self)
        self.statistics_window.show()
        logger.info("Ouverture de la fenêtre de statistiques")

    def open_settings_dialog(self):
        from settings_dialog import SettingsDialog
        import toml

        # Utiliser les imports globaux pour os et sys
        app_dir = os.path.dirname(os.path.abspath(__file__))
        dlg = SettingsDialog(self, app_dir=app_dir, current_db=self.database_path)

        # Utilisation non-bloquante : show() + connexion au signal accepted
        def on_settings_accepted():
            if dlg.selected_db and dlg.selected_username and dlg.selected_language_code:
                try:
                    config = toml.load("config.toml")
                    config["database_path"] = dlg.selected_db
                    config["username"] = dlg.selected_username
                    config["language_code"] = dlg.selected_language_code
                    with open("config.toml", "w") as f:
                        toml.dump(config, f)
                except Exception as e:
                    from PySide6.QtWidgets import QMessageBox

                    QMessageBox.warning(
                        self, "Erreur", f"Impossible de sauvegarder la config : {e}"
                    )
                    return
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self,
                    "Redémarrage",
                    "L'application va redémarrer avec les nouveaux paramètres (base, utilisateur, langue).",
                )
                self.close_all_windows()
                self.close()
                os.execl(sys.executable, sys.executable, *sys.argv)

        dlg.accepted.connect(on_settings_accepted)
        dlg.show()

    def open_resume_manual_dialog(self):
        # Ouvre la boîte de dialogue de saisie manuelle directement sur la fenêtre principale
        DialogUtils.open_or_resume_missing_responses_dialog(
            self,
            False,
            self._on_manual_dialog_finished,
            self.db_manager,
            self.language_code,
        )

    def _on_manual_dialog_finished(self):
        from missing_responses_dialog import MissingResponsesDialog

        progress_file = getattr(
            MissingResponsesDialog, "PROGRESS_FILE", ".missing_responses_progress.json"
        )
        # Si le fichier de progrès n'existe plus, masquer le bouton
        if not os.path.exists(progress_file):
            if self.resume_manual_button:
                self.resume_manual_button.hide()

    def _check_addition_queue_on_startup(self):
        """Vérifie s'il y a des entrées en attente dans la file d'attente d'addition et informe l'utilisateur."""
        queue_file = os.path.join(
            os.path.dirname(__file__), "tmp", ".addition_queue.json"
        )

        if os.path.exists(queue_file):
            try:
                with open(queue_file, "r", encoding="utf-8") as f:
                    queue_data = json.load(f)

                # Compter les entrées en attente et en erreur
                pending_count = sum(
                    1 for entry in queue_data if entry.get("status") == "pending"
                )
                error_count = sum(
                    1 for entry in queue_data if entry.get("status") == "error"
                )

                if pending_count > 0 or error_count > 0:
                    from PySide6.QtWidgets import QMessageBox

                    message = "File d'attente d'ajout détectée :\n"
                    if pending_count > 0:
                        message += (
                            f"• {pending_count} entrée(s) en attente de traitement\n"
                        )
                    if error_count > 0:
                        message += f"• {error_count} entrée(s) en erreur\n"
                    message += (
                        "\nLe traitement reprendra automatiquement en arrière-plan."
                    )

                    QMessageBox.information(self, "Reprise du traitement", message)

                    logger.info(
                        f"File d'attente d'addition trouvée : {pending_count} en attente, {error_count} en erreur"
                    )

            except Exception as e:
                logger.error(
                    f"Erreur lors de la vérification de la file d'attente d'addition : {e}"
                )

    def close_all_windows(self):
        """Ferme et détruit toutes les fenêtres secondaires ouvertes."""
        windows = [
            "retrieval_window",
            "record_manager_window",
            "bulk_import_window",
            "bulk_export_window",
            "conjugator_window",
            "addition_window",
            "statistics_window",
        ]
        for window_name in windows:
            if hasattr(self, window_name):
                window = getattr(self, window_name)
                if window is not None:
                    try:
                        window.close()
                        window.deleteLater()
                    except Exception:
                        pass
                setattr(self, window_name, None)

    def closeEvent(self, event):
        """Fermer proprement l'application et toutes les fenêtres secondaires."""
        logger.info("Fermeture de l'application")
        self.close_all_windows()  # Fermer toutes les fenêtres secondaires
        if hasattr(self, "db_manager"):
            self.db_manager.close_connection()  # Fermer la base de données
        event.accept()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)

    # Afficher un SplashScreen pendant le chargement
    splash_pix = QPixmap(400, 200)
    splash_pix.fill(Qt.white)
    splash = QSplashScreen(splash_pix)
    splash.setFont(QLabel().font())
    splash.showMessage(
        "<h2 style='color:#2d89ef;'>Coucou, The Word Bank !</h2>"
        "<p style='color:#444;'>par <b>Ron Chou</b><br>"
        "<span style='font-size:10pt;'>AGPL 3.0</span></p>"
        "<p style='color:#888;'>Coucou, en chargement, patientez...</p>",
        Qt.AlignCenter | Qt.AlignBottom,
        Qt.black,
    )
    splash.show()
    app.processEvents()  # Force l'affichage du splash

    global main_window
    main_window = MainApp()
    main_window.show()
    splash.finish(main_window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
