from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QInputDialog,
    QCheckBox,
    QHBoxLayout,
)

import os
import json
import tempfile

from PySide6.QtGui import (
    QShortcut,
    QKeySequence,
)

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from common_methods import TimeUtils, MediaUtils
from PySide6.QtWidgets import QDialogButtonBox

from common_methods import ProgressBarHelper


class MissingResponsesDialog(QDialog):
    # Utiliser le répertoire temporaire système pour les fichiers TTS
    APP_TMP_DIR = tempfile.gettempdir()
    PROGRESS_FILE = os.path.join(
        os.path.dirname(__file__), "tmp", ".missing_responses_progress.json"
    )

    _tts_cache = {}  # Cache local pour éviter les doublons

    def __init__(
        self, parent, entries, prompt_on_load=True, db_manager=None, language_code="fr"
    ):
        super().__init__(parent)
        self.setWindowTitle("Compléter les réponses manquantes")
        self.entries = entries
        self.current_index = 0
        self.db_manager = db_manager  # Ajout de la référence à la base
        self.language_code = language_code
        self._last_deleted_entry = None  # Pour stocker l'entrée supprimée et son index
        self._init_ui()  # Toujours initialiser l'UI d'abord
        self._progress_loaded = False  # Pour savoir si on a chargé un progrès
        # Charger le progrès si disponible, seulement si demandé
        if prompt_on_load:
            self._progress_loaded = self.load_progress_if_exists()
        # Ajout du lecteur audio
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        # Ajout du raccourci pour restaurer la suppression
        self.restore_shortcut = QShortcut(QKeySequence("Alt+Z"), self)
        self.restore_shortcut.activated.connect(self.restore_last_deleted_entry)
        # Aller directement à la première entrée sans réponse
        if not self._progress_loaded:
            idx = self.find_first_missing_response_index()
            if idx is not None:
                self.current_index = idx
            else:
                self.current_index = 0
            self.update_entry()

    # --- TTS centralisé avec cache ---
    def tts(self, entry):
        """
        Génère un TTS à partir de la question/réponse de l'entrée.
        Utilise un cache local pour éviter de régénérer un audio identique.
        Retourne le chemin du fichier audio généré (dans le dossier tmp).
        """
        question = entry.get("question") or entry.get("original_question") or ""
        response = entry.get("response", "")
        if "(?)" in question and response:
            tts_text = question.replace("(?)", response, 1)
        else:
            tts_text = question
        if not tts_text.strip():
            return None
        # Utiliser le hash du texte comme clé de cache
        cache_key = f"{self.language_code}:{tts_text.strip()}"
        if cache_key in self._tts_cache:
            return self._tts_cache[cache_key]
        from gtts import gTTS

        audio_filename = f"tts_{abs(hash(cache_key))}.mp3"
        file_path = os.path.join(self.APP_TMP_DIR, audio_filename)
        if not os.path.exists(file_path):
            tts = gTTS(tts_text, lang=self.language_code)
            tts.save(file_path)
        self._tts_cache[cache_key] = file_path
        return file_path

    # --- UI ---
    def _init_ui(self):
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        # Checkbox pour sélection automatique
        self.select_checkbox = QCheckBox("Toujours sélectionner dans la question (&T)")
        self.select_checkbox.setToolTip(
            "Si coché, à chaque question, vous pourrez choisir une partie de la question comme réponse."
        )
        self.select_checkbox.stateChanged.connect(self.on_checkbox_change)
        self.layout.addWidget(self.select_checkbox)
        # Affichage de l'index de l'entrée courante
        self.index_label = QLabel()
        self.layout.addWidget(self.index_label)
        # Label et zone d'édition de la question
        self.question_label = QLabel("Question (&K)")
        self.question_edit = QLineEdit()
        self.question_label.setBuddy(self.question_edit)
        self.question_edit.setReadOnly(False)
        self.layout.addWidget(self.question_label)
        self.layout.addWidget(self.question_edit)
        # Label et zone d'édition de la réponse
        self.response_label = QLabel("Réponse (&L)")
        self.response_edit = QLineEdit()
        self.response_label.setBuddy(self.response_edit)
        self.response_edit.setPlaceholderText(
            "Saisir la réponse... ou utiliser la case à cocher ci-dessus"
        )
        self.layout.addWidget(self.response_label)
        self.layout.addWidget(self.response_edit)

        # --- Ajout des champs start_time et end_time ---
        self.time_layout = QHBoxLayout()
        self.start_time_edit = QLineEdit()
        self.start_time_edit.setPlaceholderText("Début audio (hh:mm:ss, mm:ss ou ss)")
        self.end_time_edit = QLineEdit()
        self.end_time_edit.setPlaceholderText("Fin audio (hh:mm:ss, mm:ss ou ss)")
        self.time_layout.addWidget(QLabel("Début:"))
        self.time_layout.addWidget(self.start_time_edit)
        self.time_layout.addWidget(QLabel("Fin:"))
        self.time_layout.addWidget(self.end_time_edit)
        self.layout.addLayout(self.time_layout)

        # --- Boutons de navigation ---
        self.prev_btn = QPushButton("Précédent(&P)")
        self.prev_btn.setStyleSheet("background-color: #e7e7e7; color: #333;")
        self.prev_btn.clicked.connect(self.prev_entry)
        self.layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Suivant (&N)")
        self.next_btn.setStyleSheet("background-color: #e7e7e7; color: #333;")
        self.next_btn.clicked.connect(self.next_entry)
        self.layout.addWidget(self.next_btn)

        self.goto_btn = QPushButton("Aller à... (Ctrl+G)")
        self.goto_btn.setStyleSheet("background-color: #b3e5fc; color: #01579b;")
        self.goto_btn.clicked.connect(self.goto_entry)
        self.layout.addWidget(self.goto_btn)
        self.goto_shortcut = QShortcut(QKeySequence("Ctrl+G"), self)
        self.goto_shortcut.activated.connect(self.goto_entry)
        # --- Validation et sauvegarde ---
        self.validate_btn = QPushButton("Valider et enregistrer (&S)")
        self.validate_btn.setStyleSheet(
            "font-weight: bold; background-color: #4CAF50; color: white; border: 2px solid #388e3c;"
        )
        self.validate_btn.clicked.connect(self.validate_and_accept)
        self.layout.addWidget(self.validate_btn)

        self.save_btn = QPushButton("Sauvegarder et quitter (Ctrl+W)")
        self.save_btn.setStyleSheet(
            "background-color: #f0ad4e; color: white; font-weight: bold;"
        )
        self.save_btn.clicked.connect(self.save_and_quit)
        self.layout.addWidget(self.save_btn)
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self.save_shortcut.activated.connect(self.save_and_quit)

        # --- Audio ---
        self.replay_audio_btn = QPushButton("Rejouer l'audio (&A)")
        self.replay_audio_btn.setStyleSheet("background-color: #f0f0f0; color: #333;")
        self.replay_audio_btn.setToolTip(
            "Relancer la lecture de l'audio de cette entrée (si disponible)"
        )
        self.replay_audio_btn.clicked.connect(self.play_audio_for_current_entry)
        self.layout.addWidget(self.replay_audio_btn)

        self.remove_audio_btn = QPushButton("Supprimer audio (&U)")
        self.remove_audio_btn.setStyleSheet("background-color: #f7ecb5; color: #333;")
        self.remove_audio_btn.clicked.connect(self.remove_audio_from_entry)
        self.layout.addWidget(self.remove_audio_btn)

        # --- Actions sur l'entrée courante ---
        self.reset_btn = QPushButton("Réinitialiser actuel(&R)")
        self.reset_btn.setStyleSheet("background-color: #f7ecb5; color: #333;")
        self.reset_btn.clicked.connect(self.reset_entry)
        self.layout.addWidget(self.reset_btn)

        self.delete_btn = QPushButton("Supprimer cette entrée (&D)")
        self.delete_btn.setStyleSheet(
            "background-color: #ff6666; color: white; font-weight: bold;"
        )
        self.delete_btn.clicked.connect(self.delete_entry)
        self.layout.addWidget(self.delete_btn)

        # --- Bouton Annuler la suppression ---
        self.undo_delete_btn = QPushButton("Annuler la suppression (&Z)")
        self.undo_delete_btn.setStyleSheet(
            "background-color: #81c784; color: #222; font-weight: bold;"
        )
        self.undo_delete_btn.setEnabled(False)
        self.undo_delete_btn.clicked.connect(self.restore_last_deleted_entry)
        self.layout.addWidget(self.undo_delete_btn)

        self.delete_and_quit_btn = QPushButton("Supprimer et quitter (&Q)")
        self.delete_and_quit_btn.setStyleSheet(
            "background-color: #d9534f; color: white; font-weight: bold; border: 2px solid #b52b27;"
        )
        self.delete_and_quit_btn.clicked.connect(self.delete_and_quit)
        self.layout.addWidget(self.delete_and_quit_btn)

    # --- Navigation ---
    def next_entry(self):
        entry = self.entries[self.current_index]
        if self.current_index < len(self.entries) - 1:
            self.save_current()
            self.current_index += 1
        else:
            self.current_index = 0  # Pour combattre un bug mystérieux concernant la boîte de saisie de la dernière entrée
        self.update_entry()

    def prev_entry(self):
        if self.current_index > 0:
            self.save_current()
            self.current_index -= 1
            self.update_entry()

    def goto_entry(self):
        max_index = len(self.entries)
        input_dialog = QInputDialog(self)
        input_dialog.setInputMode(QInputDialog.IntInput)
        input_dialog.setWindowTitle("Aller à une entrée")
        input_dialog.setLabelText(f"Numéro d'entrée (1 à {max_index}):")
        input_dialog.setIntRange(1, max_index)
        input_dialog.setIntValue(self.current_index + 1)

        def on_int_selected(num):
            self.save_current()
            self.current_index = num - 1
            self.update_entry()

        input_dialog.intValueSelected.connect(on_int_selected)
        input_dialog.show()  # Non bloquant

    # --- Media ---
    def play_audio_for_current_entry(self):
        entry = self.entries[self.current_index]
        # Si media_path existe, jouer ce fichier
        if entry.get("media_path"):
            MediaUtils.play_media_file_qt(self, entry["media_path"], self.media_player)
            return
        # Sinon, générer ou réutiliser un TTS temporaire via le cache
        tts_path = self.tts(entry)
        if not tts_path:
            QMessageBox.information(
                self,
                "Aucune question",
                "Impossible de générer l'audio : la question est vide.",
            ).show()
            return
        MediaUtils.play_media_file_qt(self, tts_path, self.media_player)
        # Optionnel : supprimer le fichier après lecture (à faire dans MediaUtils ou ici)

    # --- Actions principales ---
    def update_entry(self):
        entry = self.entries[self.current_index]
        # Toujours sauvegarder les originaux si pas déjà fait
        if "original_question" not in entry:
            entry["original_question"] = entry["question"]
        if "original_response" not in entry:
            entry["original_response"] = entry.get("response", "")
        if "response" not in entry:
            entry["response"] = ""
        total = len(self.entries)
        numero = self.current_index + 1
        self.index_label.setText(f"Entrée {numero}/{total}")
        # Déconnecter les signaux pour éviter la boucle
        try:
            self.question_edit.textChanged.disconnect()
        except Exception:
            pass
        try:
            self.response_edit.textChanged.disconnect()
        except Exception:
            pass
        self.question_edit.setText(entry["question"])
        self.response_edit.setText(entry["response"])
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.entries) - 1)
        self.validate_btn.setVisible(True)
        self.play_audio_for_current_entry()
        # Remplir les champs start_time et end_time si présents
        self.start_time_edit.setText(TimeUtils.ms_to_str(entry.get("start_time_ms")))
        self.end_time_edit.setText(TimeUtils.ms_to_str(entry.get("end_time_ms")))
        # Reconnecter les signaux pour la mise à jour dynamique
        self.question_edit.textChanged.connect(self._on_question_changed)
        self.response_edit.textChanged.connect(self._on_response_changed)
        if len(entry["response"]) == 0 and self.select_checkbox.isChecked():
            self.apply_select_action()

    def _on_question_changed(self, text):
        entry = self.entries[self.current_index]
        entry["question"] = text

    def _on_response_changed(self, text):
        entry = self.entries[self.current_index]
        entry["response"] = text

    def save_current(self):
        entry = self.entries[self.current_index]
        entry["question"] = self.question_edit.text().strip()
        entry["response"] = self.response_edit.text().strip()
        entry["start_time_ms"] = TimeUtils.parse_time_to_ms(self.start_time_edit.text())
        entry["end_time_ms"] = TimeUtils.parse_time_to_ms(self.end_time_edit.text())
        self.save_progress()  # Sauvegarde automatique du progrès à chaque modification

    def reset_entry(self):
        entry = self.entries[self.current_index]
        # Sauvegarder l'audio original si pas déjà fait
        if "original_audio" not in entry:
            entry["original_audio"] = entry.get("media_path", None)
        # Restaurer question et réponse originales
        if "original_question" in entry:
            entry["question"] = entry["original_question"]
        else:
            entry["original_question"] = entry["question"]
        if "original_response" in entry:
            entry["response"] = entry["original_response"]
        else:
            entry["original_response"] = entry.get("response", "")
        # Réinitialiser aussi les temps de découpage
        entry["start_time_ms"] = None
        entry["end_time_ms"] = None
        # Réinitialiser l'audio à l'original
        entry["media_path"] = entry.get("original_audio", None)
        self.update_entry()

    def apply_select_action(self):
        entry = self.entries[self.current_index]
        # Créer un QDialog personnalisé pour la sélection et la suppression

        dialog = QDialog(self)
        dialog.setWindowTitle("Sélectionner une partie de la question")
        layout = QVBoxLayout(dialog)

        info_label = QLabel(
            "Sélectionnez la partie de la question à utiliser comme réponse :"
        )
        layout.addWidget(info_label)

        text_edit = QLineEdit(entry["question"])
        text_edit.selectAll()
        layout.addWidget(text_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        delete_btn = QPushButton("Supprimer cette entrée (&D)")
        play_audio_btn = QPushButton("Jouer audio (&A)")
        remove_audio_btn = QPushButton("Supprimer audio (&U)")
        button_box.addButton(delete_btn, QDialogButtonBox.ActionRole)
        button_box.addButton(play_audio_btn, QDialogButtonBox.ActionRole)
        button_box.addButton(remove_audio_btn, QDialogButtonBox.ActionRole)
        layout.addWidget(button_box)

        delete_btn.clicked.connect(lambda: (dialog.done(2), dialog.close()))
        play_audio_btn.clicked.connect(self.play_audio_for_current_entry)
        remove_audio_btn.clicked.connect(self.remove_audio_from_entry)

        def on_accept():
            new_response = text_edit.text().strip().replace("oe", "œ")
            if new_response and new_response in entry["question"]:
                self.response_edit.setText(new_response)
                entry["response"] = new_response
                new_question = entry["question"].replace(new_response, "(?)", 1)
                self.question_edit.setText(new_question)
                entry["question"] = new_question
                self.next_entry()
                dialog.close()
            else:
                self.apply_select_action()
                dialog.close()

        button_box.accepted.connect(on_accept)
        button_box.rejected.connect(dialog.close)

        # Rendre le dialog modal pour cette fenêtre uniquement
        dialog.setModal(True)
        result = dialog.exec()
        if result == 2:
            self.delete_entry()

    def find_first_missing_response_index(self):
        """Retourne l'index de la première entrée sans réponse, ou None si toutes sont remplies."""
        for i, entry in enumerate(self.entries):
            if not entry.get("response", "").strip():
                return i
        return None

    def validate_and_accept(self):
        self.save_current()
        first_missing = self.find_first_missing_response_index()
        if first_missing is not None:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Réponse manquante")
            box.setText(
                f"Veuillez remplir la réponse de l'entrée n°{first_missing + 1} avant de valider."
            )
            box.setStandardButtons(QMessageBox.Ok)

            def on_close():
                self.current_index = first_missing
                self.update_entry()

            box.finished.connect(lambda _: on_close())
            box.show()  # Non bloquant
            return
        # Insertion automatique dans la base si db_manager fourni
        if self.db_manager is not None:
            progress = ProgressBarHelper(parent_layout=self.layout)
            progress.show(len(self.entries))
            count = 0
            for idx, entry in enumerate(self.entries, start=1):
                if entry.get("response", "").strip():
                    try:
                        self.db_manager.insert_record(
                            entry.get("media_path", ""),
                            entry.get("question", ""),
                            entry.get("response", ""),
                            entry.get("start_time_ms"),
                            entry.get("end_time_ms"),
                            entry.get("UUID"),
                            entry.get("creation_date"),
                        )
                        count += 1
                    except Exception as e:
                        print(f"Erreur lors de l'insertion manuelle: {e}")
                progress.set_value(idx)
            progress.hide()
            # Supprimer le fichier de progrès uniquement après succès
            if os.path.exists(self.PROGRESS_FILE):
                try:
                    os.remove(self.PROGRESS_FILE)
                except Exception as e:
                    print(f"Erreur lors de la suppression du fichier de progrès: {e}")
        self.accept()

    def save_and_quit(self):
        self.save_current()
        try:
            with open(self.PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": self.entries, "current_index": self.current_index},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Erreur")
            box.setText(f"Erreur lors de la sauvegarde du progrès: {e}")
            box.setStandardButtons(QMessageBox.Ok)
            box.show()  # Non bloquant
        self.reject()

    def delete_entry(self):
        """Supprime l'entrée courante de la liste et passe à la suivante."""
        if len(self.entries) > 1:
            # Plus d'avertissement, on active le bouton Annuler la suppression
            # Sauvegarder l'entrée supprimée et son index
            self._last_deleted_entry = (
                self.current_index,
                self.entries[self.current_index].copy(),
            )
            self.undo_delete_btn.setEnabled(True)
            del self.entries[self.current_index]
            if self.current_index >= len(self.entries):
                self.current_index = 0
            self.update_entry()
        else:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Suppression impossible")
            msg_box.setText("Impossible de supprimer la dernière entrée.")
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.show()  # Non bloquant
        self.save_progress()

    def restore_last_deleted_entry(self):
        """Restaure la dernière entrée supprimée si disponible."""
        if self._last_deleted_entry is not None:
            idx, entry = self._last_deleted_entry
            if idx > len(self.entries):
                idx = len(self.entries)
            self.entries.insert(idx, entry)
            self.current_index = idx
            self.update_entry()
            self._last_deleted_entry = None
            self.undo_delete_btn.setEnabled(False)
        else:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("Restauration impossible")
            box.setText("Aucune suppression récente à restaurer.")
            box.setStandardButtons(QMessageBox.Ok)
            box.show()  # Non bloquant

    def delete_and_quit(self):
        """Demande confirmation, supprime le progrès partiel et ferme la fenêtre immédiatement, même s'il ne reste qu'une seule entrée."""
        input_dialog = QInputDialog(self)
        input_dialog.setInputMode(QInputDialog.TextInput)
        input_dialog.setWindowTitle("Confirmation requise")
        input_dialog.setLabelText(
            "Pour supprimer définitivement le progrès partiel, tapez : DELETE"
        )

        def on_text_selected(text):
            if text.strip() == "DELETE":
                # Suppression du fichier de progrès partiel si présent
                if os.path.exists(self.PROGRESS_FILE):
                    try:
                        os.remove(self.PROGRESS_FILE)
                    except Exception as e:
                        box = QMessageBox(self)
                        box.setIcon(QMessageBox.Warning)
                        box.setWindowTitle("Erreur")
                        box.setText(f"Erreur lors de la suppression du progrès : {e}")
                        box.setStandardButtons(QMessageBox.Ok)
                        box.show()  # Non bloquant
                # Vider la liste des entrées
                self.entries.clear()
                self.reject()
            else:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Information)
                box.setWindowTitle("Suppression annulée")
                box.setText(
                    "Aucune suppression effectuée. Vous devez saisir DELETE pour confirmer."
                )
                box.setStandardButtons(QMessageBox.Ok)
                box.show()  # Non bloquant

        input_dialog.textValueSelected.connect(on_text_selected)
        input_dialog.show()  # Non bloquant

    # --- Sauvegarde et reprise du progrès ---
    def save_progress(self):
        """Sauvegarde automatique du progrès courant."""
        try:
            with open(self.PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": self.entries, "current_index": self.current_index},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            print(f"Erreur lors de la sauvegarde automatique du progrès: {e}")

    def closeEvent(self, event):
        # Nettoyer le cache TTS à la fermeture de la fenêtre et supprimer les fichiers audio générés
        for path in self._tts_cache.values():
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass  # On ignore les erreurs de suppression
        self._tts_cache.clear()
        super().closeEvent(event)

    def load_progress_if_exists(self):
        if os.path.exists(self.PROGRESS_FILE):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Reprendre la saisie?")
            box.setText(
                "Un progrès précédent a été détecté. Voulez-vous reprendre là où vous vous étiez arrêté?"
            )
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

            def on_finished(result):
                if result == QMessageBox.Yes:
                    try:
                        with open(self.PROGRESS_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            self.entries[:] = data["entries"]
                            self.current_index = data.get("current_index", 0)
                        self.update_entry()  # Afficher directement l'entrée sauvegardée
                        box.deleteLater()
                        return True
                    except Exception as e:
                        warn_box = QMessageBox(self)
                        warn_box.setIcon(QMessageBox.Warning)
                        warn_box.setWindowTitle("Erreur")
                        warn_box.setText(f"Erreur lors du chargement du progrès: {e}")
                        warn_box.setStandardButtons(QMessageBox.Ok)
                        warn_box.show()  # Non bloquant
                else:
                    os.remove(self.PROGRESS_FILE)
                box.deleteLater()
                return False

            box.finished.connect(on_finished)
            box.show()  # Non bloquant
            return True  # On retourne True pour bloquer la suite, la gestion se fait dans le callback
        return False

    # --- Divers ---
    def on_checkbox_change(self):
        self.update_entry()

    def remove_audio_from_entry(self):
        entry = self.entries[self.current_index]
        # Sauvegarder l'audio original si pas déjà fait
        if "original_audio" not in entry:
            entry["original_audio"] = entry.get("media_path", None)
        entry["media_path"] = None
