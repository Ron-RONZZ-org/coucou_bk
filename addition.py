import multiprocessing
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPushButton,
    QWidget,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,
)
from common_methods import (
    PlainPasteTextEdit,
    ProgressBarHelper,
    TimeUtils,
)
import os
import json
import toml
import time


class QueueProcessorThread(QThread):
    """Thread séparé pour traiter les entrées de la file d'attente sans bloquer l'UI."""

    # Signaux pour communiquer avec l'UI principale
    entry_processed = Signal(dict, bool, str)  # entry, success, message
    queue_updated = Signal()  # Signal pour indiquer que la file doit être rechargée
    entry_cancelled = Signal(dict)  # Signal pour indiquer qu'une entrée a été annulée

    def __init__(self, queue_file, db_manager):
        super().__init__()
        self.queue_file = queue_file
        self.db_manager = db_manager
        self._should_stop = False
        self._current_processing_entry = (
            None  # Entrée actuellement en cours de traitement
        )
        self._cancelled_entries = set()  # Set des timestamps des entrées annulées

    def cancel_entry(self, entry_timestamp):
        """Marque une entrée comme annulée pour arrêter son traitement."""
        self._cancelled_entries.add(entry_timestamp)
        print(f"🚫 Entrée marquée pour annulation : timestamp {entry_timestamp}")

    def _is_entry_cancelled(self, entry):
        """Vérifie si une entrée a été annulée."""
        timestamp = entry.get("timestamp")
        return timestamp in self._cancelled_entries

    def stop(self):
        """Arrête proprement le thread."""
        print("🛑 Demande d'arrêt du thread de traitement...")
        self._should_stop = True
        self.quit()
        self.wait()

    def run(self):
        """Boucle principale du thread de traitement."""
        while not self._should_stop:
            try:
                # Vérifier s'il y a des entrées à traiter
                if not os.path.exists(self.queue_file):
                    self.msleep(5000)  # Attendre 5 secondes si pas de file
                    continue

                with open(self.queue_file, "r", encoding="utf-8") as f:
                    queue_data = json.load(f)

                # Chercher la première entrée en attente
                entry_to_process = None
                for entry in queue_data:
                    if entry.get("status") == "pending":
                        entry_to_process = entry
                        break

                if entry_to_process is None:
                    self.msleep(5000)  # Pas d'entrée en attente, attendre 5 secondes
                    continue

                # Vérifier si l'entrée a été annulée avant de commencer le traitement
                if self._is_entry_cancelled(entry_to_process):
                    print(
                        f"🚫 Entrée annulée, suppression de la file : {entry_to_process.get('question_data', '')[:50]}..."
                    )
                    # Supprimer l'entrée annulée de la file
                    queue_data = [
                        e
                        for e in queue_data
                        if e.get("timestamp") != entry_to_process.get("timestamp")
                    ]
                    with open(self.queue_file, "w", encoding="utf-8") as f:
                        json.dump(queue_data, f, ensure_ascii=False, indent=2)
                    # Émettre signal d'annulation
                    self.entry_cancelled.emit(entry_to_process)
                    continue

                # Marquer l'entrée comme en cours de traitement et sauvegarder la référence
                self._current_processing_entry = entry_to_process
                entry_to_process["status"] = "processing"
                entry_to_process["processing_start"] = time.time()

                # Sauvegarder immédiatement le statut
                with open(self.queue_file, "w", encoding="utf-8") as f:
                    json.dump(queue_data, f, ensure_ascii=False, indent=2)

                print(
                    f"🔄 Thread: Début traitement : {entry_to_process.get('question_data', '')[:50]}..."
                )

                try:
                    # Vérifier une dernière fois si l'entrée a été annulée pendant le traitement
                    if self._is_entry_cancelled(entry_to_process):
                        print(
                            f"🚫 Traitement annulé en cours : {entry_to_process.get('question_data', '')[:50]}..."
                        )
                        # Marquer comme annulée et supprimer de la file
                        queue_data = [
                            e
                            for e in queue_data
                            if e.get("timestamp") != entry_to_process.get("timestamp")
                        ]
                        with open(self.queue_file, "w", encoding="utf-8") as f:
                            json.dump(queue_data, f, ensure_ascii=False, indent=2)
                        self.entry_cancelled.emit(entry_to_process)
                        self._current_processing_entry = None
                        continue

                    # Traitement dans le thread séparé - opérations lourdes
                    # Vérifier à nouveau si on doit s'arrêter avant le traitement DB
                    if self._should_stop:
                        print("🛑 Arrêt demandé pendant le traitement")
                        break

                    self.db_manager.insert_record(
                        entry_to_process.get("file_path", ""),
                        entry_to_process.get("question_data", ""),
                        entry_to_process.get("response_data", ""),
                        entry_to_process.get("start_time"),
                        entry_to_process.get("end_time"),
                        attribution=entry_to_process.get(
                            "attribution", "no-attribution"
                        ),
                    )

                    # Marquer comme complété
                    entry_to_process["status"] = "completed"
                    entry_to_process["completed_at"] = time.time()
                    processing_time = (
                        entry_to_process["completed_at"]
                        - entry_to_process["processing_start"]
                    )

                    # Émettre le signal de succès
                    self.entry_processed.emit(
                        entry_to_process, True, f"Traité en {processing_time:.1f}s"
                    )

                except Exception as e:
                    # Marquer comme erreur
                    entry_to_process["status"] = "error"
                    entry_to_process["error_message"] = str(e)
                    entry_to_process["error_at"] = time.time()

                    # Émettre le signal d'erreur
                    self.entry_processed.emit(entry_to_process, False, str(e))

                # Nettoyer la référence à l'entrée en cours de traitement
                self._current_processing_entry = None

                # Sauvegarder l'état final
                with open(self.queue_file, "w", encoding="utf-8") as f:
                    json.dump(queue_data, f, ensure_ascii=False, indent=2)

                # Émettre signal de mise à jour de la file
                self.queue_updated.emit()

                # Courte pause avant de traiter la suivante
                self.msleep(1000)

            except Exception as e:
                print(f"Erreur dans le thread de traitement : {e}")
                # Nettoyer la référence en cas d'erreur
                self._current_processing_entry = None

                # Vérifier si on doit s'arrêter même en cas d'erreur
                if self._should_stop:
                    print("🛑 Arrêt demandé après erreur")
                    break

                self.msleep(5000)

        print("🏁 Thread de traitement terminé")


class ProcessInputsWorker(multiprocessing.Process):
    def __init__(
        self,
        db_manager,
        file_path,
        question_data,
        response_data,
        start_time,
        end_time,
        queue,
        attribution="no-attribution",
    ):
        super().__init__()
        self.db_manager = db_manager
        self.file_path = file_path
        self.question_data = question_data
        self.response_data = response_data
        self.start_time = start_time
        self.end_time = end_time
        self.attribution = attribution
        self.queue = queue

    def run(self):
        try:
            self.db_manager.insert_record(
                self.file_path,
                self.question_data,
                self.response_data,
                self.start_time,
                self.end_time,
                attribution=self.attribution,
            )
            self.queue.put((True, "Entrée enregistrée avec succès !"))
        except Exception as e:
            self.queue.put((False, f"Échec de l'enregistrement : {e}"))


class AudioSaverApp(QWidget):
    AUTOSAVE_FILE = os.path.join(
        os.path.dirname(__file__), "tmp", ".addition_autosave.json"
    )
    QUEUE_FILE = os.path.join(os.path.dirname(__file__), "tmp", ".addition_queue.json")

    def __init__(self, db_manager, font_size=12):  # Ajout de font_size
        super().__init__()
        self.setWindowTitle("Ajouter un élément")
        self.db_manager = db_manager  # Utiliser l'instance partagée de DatabaseManager
        self.font_size = font_size  # Stocker la taille de police
        self.setStyleSheet(
            f"* {{ font-size: {self.font_size}px; }}"
        )  # Appliquer la taille de police
        # Ajout du raccourci clavier Ctrl+W pour fermer la fenêtre
        close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_shortcut.activated.connect(self.close)
        # S'assurer que le dossier tmp existe
        tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        # Variable pour éviter les traitements simultanés
        self._is_processing = False

        # Variable pour stocker la dernière entrée ajoutée (pour annulation)
        self._last_added_entry = None

        # Créer et démarrer le thread de traitement
        self._processor_thread = QueueProcessorThread(self.QUEUE_FILE, self.db_manager)
        self._processor_thread.entry_processed.connect(self._on_entry_processed)
        self._processor_thread.queue_updated.connect(self._on_queue_updated)
        self._processor_thread.entry_cancelled.connect(self._on_entry_cancelled)
        self._processor_thread.start()

        # Timer pour vérification périodique de la file d'attente
        self._queue_timer = QTimer()
        self._queue_timer.timeout.connect(self._check_queue_status)
        self._queue_timer.start(10000)  # Vérifie toutes les 10 secondes

        # Vérifier et reprendre le traitement de la file d'attente existante au démarrage
        self._resume_existing_queue()

        # Récupère l'info sur la base de données courante
        try:
            config = toml.load(os.path.join(os.path.dirname(__file__), "config.toml"))
            self.current_db_path = config.get("database_path", "?")
        except Exception:
            self.current_db_path = "?"

        self.initialize_ui()

    def _on_entry_processed(self, entry, success, message):
        """Callback appelé quand une entrée est traitée dans le thread."""
        if success:
            print(f"✓ Thread: {message}")
        else:
            print(f"✗ Thread: Erreur - {message}")
            # Notifier l'utilisateur des erreurs persistantes
            question_preview = (
                entry.get("question_data", "")[:50] + "..."
                if len(entry.get("question_data", "")) > 50
                else entry.get("question_data", "")
            )
            QTimer.singleShot(
                100, lambda: self._notify_user_error(message, question_preview)
            )

    def _on_entry_cancelled(self, entry):
        """Callback appelé quand une entrée est annulée dans le thread."""
        print(f"🚫 Entrée annulée : {entry.get('question_data', '')[:50]}...")

    def _on_queue_updated(self):
        """Callback appelé quand la file d'attente est mise à jour."""
        # Cette méthode peut être utilisée pour rafraîchir l'UI si nécessaire
        pass

    def _check_queue_status(self):
        """Vérifie périodiquement le statut de la file d'attente."""
        try:
            if not os.path.exists(self.QUEUE_FILE):
                return

            with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                queue_data = json.load(f)

            # Nettoyer les entrées très anciennes et timeout les traitements bloqués
            current_time = time.time()
            updated = False

            for entry in queue_data:
                # Timeout pour les traitements trop longs (>15 minutes)
                if entry.get("status") == "processing":
                    processing_start = entry.get("processing_start", 0)
                    if current_time - processing_start > 900:  # 15 minutes
                        entry["status"] = "error"
                        entry["error_message"] = (
                            "Timeout - traitement trop long (>15min)"
                        )
                        entry["error_at"] = current_time
                        print(
                            f"⏰ Timeout sur entrée : {entry.get('question_data', '')[:50]}..."
                        )
                        updated = True

                        # Notifier immédiatement l'utilisateur du timeout
                        question_preview = (
                            entry.get("question_data", "")[:50] + "..."
                            if len(entry.get("question_data", "")) > 50
                            else entry.get("question_data", "")
                        )

                        # Déclencher la notification dans le thread principal
                        def show_timeout_notification():
                            self._notify_user_error(
                                "Timeout - traitement trop long (>15min)",
                                question_preview,
                            )

                        QTimer.singleShot(100, show_timeout_notification)

            if updated:
                with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(queue_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"Erreur lors de la vérification périodique : {e}")

    def closeEvent(self, event):
        """Fermeture propre avec arrêt du thread."""
        try:
            # Arrêter le timer de vérification
            if hasattr(self, "_queue_timer") and self._queue_timer:
                self._queue_timer.stop()

            # Arrêter proprement le thread de traitement
            if hasattr(self, "_processor_thread") and self._processor_thread:
                print("🛑 Arrêt du thread de traitement...")
                self._processor_thread.stop()

                # Attendre que le thread se termine (maximum 3 secondes)
                if not self._processor_thread.wait(3000):
                    print("⚠️ Thread non terminé dans les 3 secondes, forçage...")
                    self._processor_thread.terminate()
                    self._processor_thread.wait(1000)

                print("✓ Thread arrêté")

        except Exception as e:
            print(f"Erreur lors de la fermeture : {e}")
        finally:
            super().closeEvent(event)

    def _resume_existing_queue(self):
        """Vérifie s'il y a une file d'attente existante et reprend le traitement."""
        if os.path.exists(self.QUEUE_FILE):
            try:
                with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                    queue_data = json.load(f)

                # Compter les entrées en attente
                pending_count = sum(
                    1 for entry in queue_data if entry.get("status") == "pending"
                )
                processing_count = sum(
                    1 for entry in queue_data if entry.get("status") == "processing"
                )
                error_count = sum(
                    1 for entry in queue_data if entry.get("status") == "error"
                )

                if pending_count > 0 or processing_count > 0 or error_count > 0:
                    print(
                        f"File d'attente trouvée : {pending_count} entrées en attente, {processing_count} en cours, {error_count} en erreur"
                    )
                    if error_count > 0:
                        print(
                            f"⚠️ {error_count} entrée(s) en erreur - vérifiez les notifications"
                        )
                    print("Reprise du traitement en arrière-plan via thread...")

                    # Le thread se chargera automatiquement du traitement

            except Exception as e:
                print(f"Erreur lors de la lecture de la file d'attente existante : {e}")

    def _add_to_queue(self, entry_data):
        """Ajoute une entrée à la file d'attente JSON."""
        try:
            # Charger la file existante ou créer une nouvelle
            queue_data = []
            if os.path.exists(self.QUEUE_FILE):
                with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                    queue_data = json.load(f)

            # Vérifier s'il n'y a pas déjà une entrée identique récente
            current_time = time.time()
            for existing_entry in queue_data:
                if (
                    existing_entry.get("status") in ["pending", "processing"]
                    and existing_entry.get("question_data")
                    == entry_data.get("question_data")
                    and existing_entry.get("response_data")
                    == entry_data.get("response_data")
                    and abs(current_time - existing_entry.get("timestamp", 0)) < 5
                ):  # 5 secondes de protection
                    print("⚠️ Entrée identique déjà en file d'attente, ignorée")
                    return False

            # Ajouter la nouvelle entrée avec timestamp
            entry_data["timestamp"] = current_time
            entry_data["status"] = "pending"
            queue_data.append(entry_data)

            # Sauvegarder la file mise à jour
            with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)

            print("✓ Entrée ajoutée à la file d'attente")
            return True
        except Exception as e:
            print(f"Erreur lors de l'ajout à la file d'attente : {e}")
            return False

    def _notify_user_error(self, error_message, question_preview):
        """Notifie l'utilisateur d'une erreur persistante."""
        try:
            # Notification non-bloquante pour l'utilisateur
            QTimer.singleShot(
                0,
                lambda: self._show_error_notification(error_message, question_preview),
            )
        except Exception as e:
            print(f"Erreur lors de la notification utilisateur : {e}")

    def _show_error_notification(self, error_message, question_preview):
        """Affiche une notification d'erreur à l'utilisateur."""
        try:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("⚠️ Erreur de traitement")
            msg_box.setText("Échec du traitement d'une entrée :")
            msg_box.setDetailedText(
                f"Entrée : {question_preview}\nErreur : {error_message}"
            )
            msg_box.setInformativeText("Vérifiez les logs pour plus de détails.")

            # Boutons pour les actions
            retry_button = msg_box.addButton("Réessayer", QMessageBox.ActionRole)
            ignore_button = msg_box.addButton("Ignorer", QMessageBox.RejectRole)
            msg_box.setDefaultButton(retry_button)

            # Affichage non-bloquant
            msg_box.setWindowModality(Qt.NonModal)
            msg_box.show()

            # Gestion des réponses
            msg_box.finished.connect(
                lambda result: self._handle_error_response(
                    result, msg_box, question_preview
                )
            )

        except Exception as e:
            print(f"Erreur lors de l'affichage de la notification : {e}")

    def _handle_error_response(self, result, msg_box, question_preview):
        """Gère la réponse de l'utilisateur à une notification d'erreur."""
        try:
            clicked_button = msg_box.clickedButton()
            button_text = clicked_button.text() if clicked_button else ""

            if "Réessayer" in button_text:
                self._retry_failed_entry(question_preview)
            elif "Ignorer" in button_text:
                self._remove_failed_entry(question_preview)

        except Exception as e:
            print(f"Erreur lors de la gestion de la réponse : {e}")

    def _retry_failed_entry(self, question_preview):
        """Remet une entrée échouée en statut 'pending' pour retry."""
        try:
            if not os.path.exists(self.QUEUE_FILE):
                return

            with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                queue_data = json.load(f)

            # Trouver et remettre en pending
            for entry in queue_data:
                if entry.get("status") == "error" and question_preview in entry.get(
                    "question_data", ""
                ):
                    entry["status"] = "pending"
                    entry.pop("error_message", None)
                    entry.pop("error_at", None)
                    entry.pop("error_reported", None)
                    print(f"↻ Remise en file d'attente : {question_preview}")
                    break

            # Sauvegarder
            with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)

            # Le thread reprendra automatiquement le traitement

        except Exception as e:
            print(f"Erreur lors du retry : {e}")

    def _remove_failed_entry(self, question_preview):
        """Supprime définitivement une entrée échouée de la file."""
        try:
            if not os.path.exists(self.QUEUE_FILE):
                return

            with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                queue_data = json.load(f)

            # Filtrer l'entrée échouée
            original_count = len(queue_data)
            queue_data = [
                entry
                for entry in queue_data
                if not (
                    entry.get("status") == "error"
                    and question_preview in entry.get("question_data", "")
                )
            ]

            if len(queue_data) < original_count:
                print(f"🗑️ Entrée supprimée de la file : {question_preview}")

                # Sauvegarder
                with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(queue_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"Erreur lors de la suppression : {e}")

    def auto_save(self):
        """Sauvegarde automatique de l'état du formulaire dans le dossier tmp."""
        state = {
            "file_path": self.file_path_input.text(),
            "start_time": self.start_time_input.text(),
            "end_time": self.end_time_input.text(),
            "questions": self.questions_input.toPlainText(),
            "responses": self.responses_input.toPlainText(),
            "attribution": self.attribution_input.text(),
        }
        try:
            with open(self.AUTOSAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erreur lors de l'auto-sauvegarde : {e}")

    def try_restore_autosave(self):
        """Propose de restaurer l'état si une sauvegarde existe."""
        if os.path.exists(self.AUTOSAVE_FILE):
            reply = QMessageBox.question(
                self,
                "Restaurer le brouillon ?",
                "Une sauvegarde automatique a été trouvée. Voulez-vous restaurer le formulaire précédent ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                try:
                    with open(self.AUTOSAVE_FILE, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    self.file_path_input.setText(state.get("file_path", ""))
                    self.start_time_input.setText(state.get("start_time", ""))
                    self.end_time_input.setText(state.get("end_time", ""))
                    self.questions_input.setPlainText(state.get("questions", ""))
                    self.responses_input.setPlainText(state.get("responses", ""))
                    self.attribution_input.setText(state.get("attribution", ""))
                except Exception as e:
                    QMessageBox.warning(
                        self, "Erreur", f"Impossible de restaurer la sauvegarde : {e}"
                    )
                # On ne supprime pas la sauvegarde ici, seulement après succès

    def clear_autosave(self):
        try:
            if os.path.exists(self.AUTOSAVE_FILE):
                os.remove(self.AUTOSAVE_FILE)
        except Exception as e:
            print(f"Erreur lors de la suppression de l'auto-sauvegarde : {e}")

    def initialize_ui(self):
        # Supprimer le layout existant s'il y en a un (pour éviter les doublons et erreurs)
        old_layout = self.layout()
        if old_layout is not None:
            QWidget().setLayout(old_layout)
        self.setLayout(QVBoxLayout())  # Toujours repartir d'un layout propre

        self.showMaximized()  # Ouvre la fenêtre principale en mode maximisé
        self.main_form()

    def open_resume_manual_dialog(self):
        """Ouvre la boîte de dialogue de saisie manuelle directement dans cette fenêtre d'addition."""
        from common_methods import DialogUtils

        # Utiliser la main app pour récupérer ses données
        main_app = None
        try:
            # Essayer de récupérer l'instance MainApp depuis le parent ou d'autres moyens
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, "_pending_manual_entries") and hasattr(
                    widget, "db_manager"
                ):
                    main_app = widget
                    break
        except:
            pass

        if (
            main_app
            and hasattr(main_app, "db_manager")
            and hasattr(main_app, "language_code")
        ):
            DialogUtils.open_or_resume_missing_responses_dialog(
                self,  # Utiliser cette fenêtre d'addition comme parent
                False,
                self._on_manual_dialog_finished,
                main_app.db_manager,
                main_app.language_code,
            )
        else:
            print("Impossible de récupérer les paramètres de l'application principale")

    def _on_manual_dialog_finished(self):
        """Callback appelé quand le dialog de réponses manquantes se ferme."""
        from missing_responses_dialog import MissingResponsesDialog

        progress_file = getattr(
            MissingResponsesDialog, "PROGRESS_FILE", ".missing_responses_progress.json"
        )
        print(f"Dialog de saisie manuelle terminé. Fichier de progrès: {progress_file}")
        # Optionnel : fermer cette fenêtre d'addition si souhaité
        # self.close()

    def main_form(self):
        # Nettoyer le layout existant (pour éviter doublons si réouverture)
        if self.layout() is not None:
            while self.layout().count():
                item = self.layout().takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        else:
            self.setLayout(QVBoxLayout())

        form_layout = QFormLayout()

        # --- Sélection de fichier média ---
        self.file_path_input = QLineEdit()
        file_button = QPushButton("Sélectionner un fichier média")
        file_button.clicked.connect(lambda: self.select_file(self.file_path_input))
        form_layout.addRow("", file_button)
        form_layout.addRow("Fichier média: (&M)", self.file_path_input)

        # --- Saisie des timestamps ---
        self.start_time_input = QLineEdit()
        self.end_time_input = QLineEdit()
        self.start_time_input.setPlaceholderText(
            "Début (hh:mm:ss ou mm:ss ou ss, ex: 1:01:01 ou 1:23 ou 45)"
        )
        self.end_time_input.setPlaceholderText(
            "Fin (hh:mm:ss ou mm:ss ou ss, ex: 1:22:04 ou 2:10 ou 75)"
        )
        form_layout.addRow("Début (&D) :", self.start_time_input)
        form_layout.addRow("Fin (&F):", self.end_time_input)

        # --- Saisie des questions/réponses (multiligne) ---
        self.questions_input = PlainPasteTextEdit()
        self.questions_input.setPlaceholderText(
            "Séparez par ; pour plusieurs questions"
        )
        form_layout.addRow("Questions (&Q) :", self.questions_input)
        self.responses_input = PlainPasteTextEdit()
        self.responses_input.setPlaceholderText("Séparez par ; pour plusieurs réponses")
        form_layout.addRow("Réponses (&R) :", self.responses_input)

        # --- Saisie de l'attribution ---
        self.attribution_input = QLineEdit()
        self.attribution_input.setPlaceholderText(
            "Attribution (optionnel, défaut: no-attribution)"
        )
        form_layout.addRow("Attribution (&A) :", self.attribution_input)

        # --- Boutons principaux en ligne ---
        button_row = QHBoxLayout()

        # Bouton interroger ça
        interrogate_button = QPushButton("interroger ça (&C)")
        interrogate_button.setToolTip(
            "Sélectionnez un morceau de texte dans la question, puis cliquez ici : il sera remplacé par (?) dans la question et ajouté comme nouvelle réponse."
        )
        interrogate_button.setStyleSheet(
            "background-color: #b3e5fc; color: #01579b; font-weight: bold; border-radius: 6px;"
        )
        button_row.addWidget(interrogate_button)

        # Bouton annuler interroger
        cancel_interrogate_button = QPushButton("Annuler interroger (&Z)")
        cancel_interrogate_button.setToolTip(
            "Annule la dernière opération d'interrogation (Ctrl+Z)."
        )
        cancel_interrogate_button.setStyleSheet(
            "background-color: #f7ecb5; color: #333; font-weight: bold; border-radius: 6px;"
        )
        button_row.addWidget(cancel_interrogate_button)

        # Bouton mode rapide
        quick_button = QPushButton("mode rapide (&E)")
        quick_button.setToolTip(
            "Ajouter rapidement plusieurs entrées : chaque ligne saisie sera une entrée avec (?) comme question et la ligne comme réponse."
        )
        quick_button.setStyleSheet(
            "background-color: #3bb67d; color: white; font-weight: bold; border-radius: 6px;"
        )
        button_row.addWidget(quick_button)

        # Bouton de soumission
        self.submit_button = QPushButton("Soumettre (&S)")
        self.submit_button.setStyleSheet(
            "background-color: #1976d2; color: white; font-weight: bold; border-radius: 6px; border: 2px solid #388e3c;"
        )
        button_row.addWidget(self.submit_button)

        form_layout.addRow(button_row)

        # Ajout d'une variable d'état pour annulation interrogation
        self._last_interrogation_state = None

        def handle_interrogation():
            """
            handle_interrogation() vise à permettre à l'utilisateur de créer un 'filling the blanks' question par sélection de mots dans question_input, les remplacer par un filler "(?) " et les ajouter dans response._input.
            Correction : gère plusieurs blanks dans une même question, chaque blank correspond à la bonne réponse dans l'ordre global, et insère la réponse à la bonne position sans écraser les autres.
            """
            # Déterminer le champ actif et la position du curseur
            if self.questions_input.hasFocus():
                active_field = "questions"
                cursor_pos = self.questions_input.textCursor().position()
            elif self.responses_input.hasFocus():
                active_field = "responses"
                cursor_pos = self.responses_input.textCursor().position()
            else:
                active_field = None
                cursor_pos = None
            cursor = self.questions_input.textCursor()
            selected_text = cursor.selectedText()
            if not selected_text:
                QMessageBox.information(
                    self,
                    "Sélection requise",
                    "Veuillez sélectionner un texte dans la zone 'Questions' à interroger.",
                )
                return
            # Sauvegarder l'état précédent pour annulation, y compris champ actif et position
            self._last_interrogation_state = {
                "questions_text": self.questions_input.toPlainText(),
                "responses_text": self.responses_input.toPlainText(),
                "selection_start": cursor.selectionStart(),
                "selection_end": cursor.selectionEnd(),
                "selected_text": selected_text,
                "active_field": active_field,
                "cursor_pos": cursor_pos,
            }
            # Texte complet et position de la sélection
            question_text = self.questions_input.toPlainText()
            start = cursor.selectionStart()
            # Découper les questions
            questions = [q.strip() for q in question_text.split(";")]
            # Trouver la question contenant la sélection et la position locale
            pos = 0
            question_idx = 0
            local_start = start
            for idx, q in enumerate(questions):
                q_len = len(q)
                if start <= pos + q_len + idx:  # idx pour le ';' séparateur
                    question_idx = idx
                    local_start = start - pos - idx  # position dans la question locale
                    break
                pos += q_len
            # Compter le nombre de blanks (?) déjà présents dans toutes les questions avant celle-ci
            blanks_before = sum(q.count("(?)") for q in questions[:question_idx])
            # Dans la question courante, compter le nombre de (?) avant la sélection
            q_current = questions[question_idx]
            before_sel = q_current[:local_start]
            blanks_in_current_before = before_sel.count("(?)")
            # L'index global du blank à insérer
            blank_global_idx = blanks_before + blanks_in_current_before
            # Remplacer la sélection par (?) dans la question
            cursor.insertText("(?) ")
            self.questions_input.setTextCursor(cursor)
            # Mettre à jour la liste des réponses à la bonne position globale
            resp = self.responses_input.toPlainText().strip()
            responses = [r.strip() for r in resp.split(";")] if resp else []
            # Compléter avec des vides si besoin
            while len(responses) < blank_global_idx:
                responses.append("")
            # Insérer la réponse à la bonne position (sans écraser)
            responses.insert(blank_global_idx, selected_text)
            self.responses_input.setPlainText("; ".join(responses))

        def cancel_interrogation():
            """
            Annule la dernière opération d'interrogation (remet le texte sélectionné à la place du dernier (?) inséré et retire la réponse correspondante).
            Restaure aussi le focus et la position du curseur dans le champ qui était actif.
            """
            state = self._last_interrogation_state
            if not state:
                QMessageBox.information(
                    self,
                    "Annulation impossible",
                    "Aucune opération d'interrogation à annuler.",
                )
                return
            # Restaurer le texte des questions et réponses
            self.questions_input.setPlainText(state["questions_text"])
            self.responses_input.setPlainText(state["responses_text"])
            # Restaurer le focus et la position du curseur
            if state.get("active_field") == "questions":
                self.questions_input.setFocus()
                cursor = self.questions_input.textCursor()
                pos = state.get("cursor_pos", 0)
                cursor.setPosition(pos)
                self.questions_input.setTextCursor(cursor)
            elif state.get("active_field") == "responses":
                self.responses_input.setFocus()
                cursor = self.responses_input.textCursor()
                pos = state.get("cursor_pos", 0)
                cursor.setPosition(pos)
                self.responses_input.setTextCursor(cursor)
            # Effacer l'état pour éviter annulation multiple
            self._last_interrogation_state = None

        interrogate_button.clicked.connect(handle_interrogation)
        cancel_interrogate_button.clicked.connect(cancel_interrogation)
        # Raccourci clavier Ctrl+Z pour annuler interrogation
        cancel_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        cancel_shortcut.activated.connect(cancel_interrogation)

        def open_quick_dialog():
            quick_dialog = self._create_quick_dialog()
            quick_dialog.show()

        quick_button.clicked.connect(open_quick_dialog)

        self.submit_button.clicked.connect(
            lambda: self.process_inputs(
                self.file_path_input,
                self.start_time_input,
                self.end_time_input,
                self.questions_input,
                self.responses_input,
                self.attribution_input,
            )
        )

        # Ajout du formulaire au layout principal
        self.layout().addLayout(form_layout)

        # Afficher le nom du fichier de base de données et le chemin complet en bas
        db_filename = os.path.basename(self.current_db_path)
        db_name_label = QLabel(f"<b>{db_filename}</b>")
        db_name_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #1976d2; margin-top: 18px;"
        )
        db_name_label.setAlignment(Qt.AlignCenter)
        self.layout().addWidget(db_name_label)
        db_label = QLabel(f"\n{self.current_db_path}")
        db_label.setStyleSheet(
            "color: #1976d2; font-weight: bold; font-size: 18px; padding: 8px;"
        )
        db_label.setAlignment(Qt.AlignCenter)
        self.layout().addWidget(db_label)

        # Connecter auto_save sur modification des champs principaux
        self.file_path_input.textChanged.connect(self.auto_save)
        self.start_time_input.textChanged.connect(self.auto_save)
        self.questions_input.textChanged.connect(self.auto_save)
        self.responses_input.textChanged.connect(self.auto_save)
        self.attribution_input.textChanged.connect(self.auto_save)
        self.end_time_input.textChanged.connect(self.auto_save)

        self.showMaximized()  # Afficher la fenêtre principale en mode maximisé
        self.try_restore_autosave()

    def _create_quick_dialog(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel

        quick_dialog = QDialog(self)
        quick_dialog.setWindowTitle("Mode rapide : saisie de plusieurs réponses")
        layout = QVBoxLayout(quick_dialog)
        layout.addWidget(QLabel("Saisissez une phrase par ligne :"))
        text_edit = PlainPasteTextEdit()
        layout.addWidget(text_edit)
        submit_btn = QPushButton("Ajouter toutes les entrées (&S)")
        layout.addWidget(submit_btn)

        # Ajout de la barre de progrès centralisée
        progress_helper = ProgressBarHelper(layout)

        submit_btn.clicked.connect(
            lambda: self._handle_quick_submit(text_edit, progress_helper, quick_dialog)
        )
        return quick_dialog

    def _handle_quick_submit(self, text_edit, progress_helper, quick_dialog):
        lines = [l.strip() for l in text_edit.toPlainText().splitlines() if l.strip()]
        if not lines:
            QMessageBox.warning(self, "Erreur", "Aucune phrase saisie.")
            return
        count = 0
        progress_helper.show(len(lines))
        for idx, word in enumerate(lines, start=1):
            try:
                self.db_manager.insert_record(
                    media_file="",
                    question="(?)",
                    response=word,
                    attribution="no-attribution",
                )
                count += 1
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur sur '{word}': {e}")
            progress_helper.set_value(idx)
        progress_helper.hide()
        QMessageBox.information(self, "Succès", f"{count} entrées ajoutées.")
        quick_dialog.accept()

    def safe_close(self):
        """Ferme l'application en toute sécurité si l'objet n'est pas supprimé."""
        if not self.isVisible():
            return
        self.close()

    def select_file(self, file_path_input):
        # Ouvre une boîte de dialogue pour sélectionner un fichier média (audio ou vidéo)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier média",
            "",
            "Fichiers média (*.mp3 *.wav *.ogg *.mp4 *.avi *.mov *.mkv)",
        )
        if file_path:
            file_path_input.setText(file_path)

    def process_inputs(
        self,
        file_path_input,
        start_time_input,
        end_time_input,
        questions_input,
        responses_input,
        attribution_input,
    ):
        file_path = file_path_input.text()
        start_time_raw = start_time_input.text().strip()
        end_time_raw = end_time_input.text().strip()

        questions = [
            q.strip() for q in questions_input.toPlainText().split(";") if q.strip()
        ]
        responses = [
            r.strip() for r in responses_input.toPlainText().split(";") if r.strip()
        ]

        # --- Vérification explicite de l'existence du fichier média ---
        if file_path:
            if not os.path.exists(file_path):
                QMessageBox.critical(
                    self,
                    "Erreur",
                    f"Le fichier média spécifié n'existe pas : {file_path}",
                )
                return

        # --- Vérification de la validité des timestamps ---
        start_time = TimeUtils.parse_time_to_ms(start_time_raw)
        end_time = TimeUtils.parse_time_to_ms(end_time_raw)
        if start_time_raw and start_time is None:
            QMessageBox.warning(
                self,
                "Avertissement",
                f"Le format du timestamp de début est invalide. Saisie : {start_time_raw}",
            )
            return
        if end_time_raw and end_time is None:
            QMessageBox.warning(
                self,
                "Avertissement",
                f"Le format du timestamp de fin est invalide. Saisie : {end_time_raw}",
            )
            return

        question_data = "; ".join(questions) if questions else ""
        response_data = "; ".join(responses) if responses else ""
        attribution = attribution_input.text().strip() or "no-attribution"

        if not questions:
            QMessageBox.warning(
                self, "Avertissement", "Au moins une question est requise !"
            )
            return
        if not responses:
            QMessageBox.warning(
                self, "Avertissement", "Au moins une réponse est requise !"
            )
            return

        # Vérification du nombre de (?) dans les questions et du nombre de réponses
        nb_blanks = questions_input.toPlainText().count("(?)")
        nb_responses = len(responses)
        if nb_blanks != nb_responses:
            QMessageBox.warning(
                self,
                "Avertissement",
                f"Le nombre de '(?)' dans les questions ({nb_blanks}) ne correspond pas au nombre de réponses ({nb_responses}) !",
            )
            return

        # Préparer les données pour la file d'attente
        entry_data = {
            "file_path": file_path,
            "question_data": question_data,
            "response_data": response_data,
            "start_time": start_time,
            "end_time": end_time,
            "attribution": attribution,
        }

        # Ajouter à la file d'attente
        if self._add_to_queue(entry_data):
            # Jouer le son de succès
            from common_methods import MediaUtils

            MediaUtils.play_media_file_qt(self, "assets/audio_effects/correct.ogg")

            # Sauvegarder les données de la dernière entrée ajoutée pour annulation
            self._last_added_entry = {
                "question_data": question_data,
                "response_data": response_data,
                "timestamp": time.time(),
            }

            # Afficher message de succès avec bouton d'annulation
            self._show_success_notification_with_cancel()

            # Rafraîchir l'interface après 1 seconde
            QTimer.singleShot(1000, self._refresh_ui)
        else:
            QMessageBox.critical(
                self, "Erreur", "Impossible d'ajouter l'entrée à la file d'attente."
            )

    def _refresh_ui(self):
        """Rafraîchit l'interface après traitement."""
        # Vider les champs du formulaire
        self.start_time_input.clear()
        self.end_time_input.clear()
        self.questions_input.clear()
        self.responses_input.clear()
        self.clear_autosave()  # Suppression de la sauvegarde après succès

    def on_process_inputs_finished(self, success, message):
        def handle_result():
            self.submit_button.setEnabled(True)
            self.submit_button.setText("Soumettre (&S)")
            if success:
                # Jouer le son de succès
                from common_methods import MediaUtils

                MediaUtils.play_media_file_qt(self, "assets/audio_effects/correct.ogg")

                self.start_time_input.clear()
                self.end_time_input.clear()
                self.questions_input.clear()
                self.responses_input.clear()
                self.clear_autosave()  # Suppression de la sauvegarde après succès
            else:
                QMessageBox.critical(self, "Erreur", message)

        QTimer.singleShot(0, handle_result)

    def _show_success_notification_with_cancel(self):
        """Affiche une notification de succès avec un bouton d'annulation."""
        try:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("✓ Ajouté à la file d'attente")
            msg_box.setText(
                "L'entrée a été ajoutée à la file d'attente et sera traitée en arrière-plan."
            )
            msg_box.setInformativeText(
                "Vous pouvez annuler cet ajout dans les 10 prochaines secondes."
            )

            # Boutons personnalisés
            cancel_button = msg_box.addButton("Annuler l'ajout", QMessageBox.ActionRole)
            ok_button = msg_box.addButton("OK", QMessageBox.AcceptRole)
            msg_box.setDefaultButton(ok_button)

            # Timer pour fermer automatiquement après 10 secondes
            auto_close_timer = QTimer()
            auto_close_timer.setSingleShot(True)
            auto_close_timer.timeout.connect(msg_box.accept)
            auto_close_timer.start(10000)  # 10 secondes

            # Affichage non-bloquant
            msg_box.setWindowModality(Qt.NonModal)
            msg_box.show()

            # Gestion des réponses
            msg_box.finished.connect(
                lambda result: self._handle_success_response(
                    result, msg_box, cancel_button, auto_close_timer
                )
            )

        except Exception as e:
            print(f"Erreur lors de l'affichage de la notification de succès : {e}")

    def _handle_success_response(
        self, result, msg_box, cancel_button, auto_close_timer
    ):
        """Gère la réponse de l'utilisateur à la notification de succès."""
        try:
            # Arrêter le timer auto-close
            auto_close_timer.stop()

            clicked_button = msg_box.clickedButton()
            if clicked_button == cancel_button:
                self._cancel_last_addition()

        except Exception as e:
            print(f"Erreur lors de la gestion de la réponse de succès : {e}")

    def _cancel_last_addition(self):
        """Annule le dernier ajout à la file d'attente."""
        try:
            if not hasattr(self, "_last_added_entry") or not self._last_added_entry:
                QMessageBox.warning(
                    self, "Annulation impossible", "Aucun ajout récent à annuler."
                )
                return

            if not os.path.exists(self.QUEUE_FILE):
                QMessageBox.warning(
                    self, "Annulation impossible", "La file d'attente n'existe plus."
                )
                return

            last_entry = self._last_added_entry
            entry_timestamp = last_entry.get("timestamp")

            # Signaler au thread que cette entrée doit être annulée
            if hasattr(self, "_processor_thread") and self._processor_thread:
                self._processor_thread.cancel_entry(entry_timestamp)

            with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                queue_data = json.load(f)

            # Chercher l'entrée correspondante
            target_entry = None
            for entry in queue_data:
                if (
                    entry.get("question_data") == last_entry.get("question_data")
                    and entry.get("response_data") == last_entry.get("response_data")
                    and abs(entry.get("timestamp", 0) - entry_timestamp)
                    < 2  # Tolérance de 2 secondes
                ):
                    target_entry = entry
                    break

            if not target_entry:
                QMessageBox.warning(
                    self,
                    "Annulation échouée",
                    "L'entrée n'a pas pu être trouvée dans la file d'attente.",
                )
                return

            # Vérifier le statut de l'entrée
            entry_status = target_entry.get("status", "unknown")

            if entry_status == "pending":
                # Entrée en attente : suppression directe de la file
                queue_data = [
                    e for e in queue_data if e.get("timestamp") != entry_timestamp
                ]
                with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(queue_data, f, ensure_ascii=False, indent=2)

                print("🗑️ Entrée en attente annulée et supprimée")
                QMessageBox.information(
                    self,
                    "Annulation réussie",
                    "L'entrée en attente a été annulée avec succès.",
                )

            elif entry_status == "processing":
                # Entrée en cours de traitement : le thread l'arrêtera
                print("🚫 Demande d'arrêt pour l'entrée en cours de traitement")
                QMessageBox.information(
                    self,
                    "Annulation en cours",
                    "L'entrée est en cours de traitement.\nL'annulation va être appliquée dès que possible.",
                )

            elif entry_status == "completed":
                QMessageBox.warning(
                    self,
                    "Annulation impossible",
                    "L'entrée a déjà été traitée avec succès.\nImpossible d'annuler.",
                )
                return

            elif entry_status == "error":
                # Entrée en erreur : suppression directe
                queue_data = [
                    e for e in queue_data if e.get("timestamp") != entry_timestamp
                ]
                with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(queue_data, f, ensure_ascii=False, indent=2)

                print("🗑️ Entrée en erreur supprimée")
                QMessageBox.information(
                    self,
                    "Annulation réussie",
                    "L'entrée en erreur a été supprimée de la file d'attente.",
                )

            # Réinitialiser la référence dans tous les cas
            self._last_added_entry = None

        except Exception as e:
            print(f"Erreur lors de l'annulation : {e}")
            QMessageBox.critical(
                self,
                "Erreur d'annulation",
                f"Une erreur s'est produite lors de l'annulation : {e}",
            )
