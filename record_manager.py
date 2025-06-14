from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
    QLineEdit,
    QHeaderView,
    QLabel,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence, QShortcut, QIcon
import csv
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from common_methods import DialogUtils, ProgressBarHelper
from logger import logger
import os


class RecordManagerApp(QWidget):
    def __init__(self, db_manager, font_size=12):
        super().__init__()
        self.setWindowTitle("Gérer les entrées")
        self.db_manager = db_manager
        self.font_size = font_size
        self.setStyleSheet(f"* {{ font-size: {self.font_size}px; }}")
        self.setStyleSheet(
            self.styleSheet()
            + "\nQToolTip { color: #fff; background-color: #222; border: 1px solid #555; font-size: 13px; }"
        )
        self.changed_lines = set()
        self.setup_ui()
        self.showMaximized()

    def resize_table_columns(self):
        """Ajuste la largeur et le mode de redimensionnement des colonnes de la table."""
        header = self.table.horizontalHeader()
        header.resizeSection(0, 60)
        header.resizeSection(1, 60)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Champ de recherche
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher... (CTRL+F)")
        self.search_input.textChanged.connect(self.search_records)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(
            lambda: (self.search_input.setFocus(), self.search_input.selectAll())
        )

        # Section "Aller à la ligne"
        goto_layout = QHBoxLayout()
        self.line_input = QLineEdit()
        self.line_input.setPlaceholderText("sauter à numéro de ligne... (CTRL+G)")
        goto_layout.addWidget(self.line_input)
        goto_button = QPushButton("Aller à la ligne")
        goto_button.clicked.connect(self.go_to_line)
        goto_layout.addWidget(goto_button)
        layout.addLayout(goto_layout)

        self.goto_shortcut = QShortcut(QKeySequence("Ctrl+G"), self)
        self.goto_shortcut.activated.connect(self.line_input.setFocus)

        # Table pour afficher les entrées
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            [
                "UUID",
                "Fichier Média",
                "Question",
                "Réponse",
                "Créé le",
                "Attribution",
                "Lire",
                "Favori",
            ]
        )
        self.table.itemChanged.connect(self.track_changes)
        layout.addWidget(self.table)

        self.resize_table_columns()

        self.progress_helper = ProgressBarHelper(layout)
        self.progress_helper.hide()

        # Boutons pour les actions (style moderne, icônes personnalisées)
        button_layout = QHBoxLayout()
        actions = [
            {
                "icon": "assets/icons/save.png",
                "tooltip": "Enregistrer/Actualiser (Alt+S)",
                "color": "#3c697d",
                "callback": self.save_changes,
                "shortcut": "Alt+S",
                "label": "&S",
                "accessible": "Enregistrer/Actualiser",
            },
            {
                "icon": "assets/icons/delete-permanent.png",
                "tooltip": "Supprimer (Alt+D)",
                "color": "#c14a6c",
                "callback": self.delete_record,
                "shortcut": "Alt+D",
                "label": "&D",
                "accessible": "Supprimer",
            },
            {
                "icon": "assets/icons/signal.png",
                "tooltip": "Afficher les entrées signalées (Alt+E)",
                "color": "#b4b92e",
                "callback": self.filter_error_records,
                "shortcut": "Alt+E",
                "label": "&E",
                "accessible": "Afficher les entrées signalées",
            },
            {
                "icon": "assets/icons/calendar.png",
                "tooltip": "Filtrer par date (Alt+T)",
                "color": "#3c3ac6",
                "callback": self.filter_by_date_range,
                "shortcut": "Alt+T",
                "label": "&T",
                "accessible": "Filtrer par date",
            },
            {
                "icon": "assets/icons/clear.png",
                "tooltip": "Effacer les signalisations d'erreurs (Alt+R)",
                "color": "#10db49",
                "callback": self.clear_error_file,
                "shortcut": "Alt+R",
                "label": "&R",
                "accessible": "Effacer les erreurs",
            },
            {
                "icon": "assets/icons/cut.png",
                "tooltip": "Déplacer records (Alt+M)",
                "color": "#1976d2",
                "callback": self.move_records,
                "shortcut": "Alt+M",
                "label": "&M",
                "accessible": "Déplacer records",
            },
        ]
        for action in actions:
            btn = QPushButton()
            btn.setIcon(QIcon(action["icon"]))
            btn.setIconSize(QSize(32, 32))
            btn.setToolTip(action["tooltip"])
            btn.setAccessibleName(action["accessible"])
            btn.clicked.connect(action["callback"])
            btn.setShortcut(QKeySequence(action["shortcut"]))
            btn.setStyleSheet(
                f"background-color: {action['color']}; border-radius: 8px; margin: 6px;"
            )
            label = QLabel(action["label"])
            label.setVisible(False)
            button_layout.addWidget(self._button_with_label(btn, label))
        layout.addLayout(button_layout)

        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_changes)

        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self.delete_record)

        edit_shortcut = QShortcut(QKeySequence("F2"), self)
        edit_shortcut.activated.connect(self.edit_selected_cell)

        close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_shortcut.activated.connect(self.close)

        # Initialiser le lecteur média
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.load_records()

    def focus_search_input(self):
        self.search_input.setFocus()

    def focus_line_input(self):
        self.line_input.setFocus()

    def track_changes(self, item):
        self.changed_lines.add(item.row())

    def closeEvent(self, event):
        if self.changed_lines:
            reply = QMessageBox.question(
                self,
                "Modifications non sauvegardées",
                "Voulez-vous sauvegarder les modifications avant de fermer?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )

            if reply == QMessageBox.Save:
                self.save_changes()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def save_changes(self):
        visible_uuids = set()
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                uuid_item = self.table.item(row, 0)
                if uuid_item:
                    visible_uuids.add(uuid_item.text())

        changed_lines_copy = list(self.changed_lines)
        total_changes = len(changed_lines_copy)
        if total_changes == 0:
            QMessageBox.information(self, "Info", "Aucune modification à enregistrer.")
            self.load_records()
            return

        self.progress_helper.show(total_changes)
        for i, row in enumerate(changed_lines_copy):
            if (
                self.table.item(row, 0) is None
                or self.table.item(row, 2) is None
                or self.table.item(row, 3) is None
            ):
                self.changed_lines.discard(row)
                continue

            record_id = self.table.item(row, 0).text()
            new_media_file = self.table.item(row, 1).text()
            new_question = self.table.item(row, 2).text()
            new_response = self.table.item(row, 3).text()
            new_attribution = (
                self.table.item(row, 5).text()
                if self.table.item(row, 5)
                else "no-attribution"
            )

            try:
                success = self.db_manager.update_record(
                    record_id,
                    new_media_file,
                    new_question,
                    new_response,
                    new_attribution,
                )
                self.changed_lines.discard(row)
                if success:
                    logger.info(
                        f"entry UUID={record_id} is successfully modified by user."
                    )
                else:
                    raise Exception(f"Échec de la mise à jour pour UUID: {record_id}")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))
                pass

            self.progress_helper.set_value(i + 1)

        self.progress_helper.hide()

        if not self.changed_lines:
            QMessageBox.information(
                self, "Succès", "Toutes les modifications ont été enregistrées."
            )
        self.table.blockSignals(True)
        self.load_records()
        self.table.blockSignals(False)

        for row in range(self.table.rowCount()):
            uuid_item = self.table.item(row, 0)
            if uuid_item and uuid_item.text() in visible_uuids:
                self.table.setRowHidden(row, False)
            else:
                self.table.setRowHidden(row, True)

        if self.search_input.text():
            self.search_records(self.search_input.text())

    def load_records(self):
        records = self.db_manager.fetch_all_records()
        self._render_table(records)

    def load_favorite_records(self):
        records = self.db_manager.fetch_favorite_records()
        self._render_table(records)

    def reload_records(self):
        """
        Recharge la table en conservant l'état de la recherche ou du filtrage actif.
        """
        if hasattr(self, "_filter_error_active") and self._filter_error_active:
            self.filter_error_records()
        elif (
            hasattr(self, "_filter_date_active")
            and self._filter_date_active
            and hasattr(self, "_last_date_range")
        ):
            # Recharge le filtrage par date avec la dernière plage utilisée
            start, end = self._last_date_range
            self._filter_date_active = False  # Pour éviter la boucle
            self.filter_by_date_range(start, end)
            self._filter_date_active = True
        elif self.search_input.text():
            self.load_records()
            self.search_records(self.search_input.text())
        else:
            self.load_records()

    def play_media_file(self, media_file):
        # Utilise la fonction centralisée MediaUtils.play_media_file_qt pour éviter la duplication de code
        from common_methods import MediaUtils

        MediaUtils.play_media_file_qt(self, media_file, self.media_player)

    def delete_record(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self,
                "Erreur",
                "Veuillez sélectionner un ou plusieurs entrées à supprimer par CLIQUER sur les NUMÉROs des lignes.",
            )
            return

        rows_to_delete = sorted([index.row() for index in selected_rows], reverse=True)
        self.table.blockSignals(True)
        for row in rows_to_delete:
            record_id = self.table.item(row, 0).text()
            success = self.db_manager.delete_record(record_id)
            if not success:
                QMessageBox.critical(
                    self,
                    "Erreur",
                    f"Échec de la suppression de l'entrée UUID: {record_id}.",
                )
                self.table.blockSignals(False)
                return
            self.changed_lines.discard(row)
            self.changed_lines = set(
                (i - 1 if i > row else i) for i in self.changed_lines
            )

        self.table.blockSignals(False)
        QMessageBox.information(self, "Succès", "entrée(s) supprimé(s) avec succès.")
        self.load_records()

    def search_records(self, keyword):
        # Affiche les lignes contenant tous les mots-clés, même dispersés dans plusieurs colonnes
        keywords = [k.strip().lower() for k in keyword.split() if k.strip()]
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            row_texts = []
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                if item:
                    row_texts.append(item.text().lower())
            # Pour chaque mot-clé, il doit être présent dans au moins une colonne
            match = all(any(kw in cell for cell in row_texts) for kw in keywords)
            self.table.setRowHidden(row, not match)
        self.table.blockSignals(False)

    def go_to_line(self):
        line_number_str = self.line_input.text()
        if not line_number_str.isdigit():
            QMessageBox.warning(
                self, "Erreur", "Veuillez entrer un numéro de ligne valide."
            )
            return

        line_number = int(line_number_str)
        if line_number < 1 or line_number > self.table.rowCount():
            QMessageBox.warning(
                self,
                "Erreur",
                f"Le numéro de ligne doit être entre 1 et {self.table.rowCount()}.",
            )
            return

        row_index = line_number - 1
        self.table.scrollToItem(self.table.item(row_index, 0))
        self.table.selectRow(row_index)
        self.line_input.clear()

    def filter_error_records(self):
        try:
            with open("entry_error.csv", "r", encoding="utf-8") as file:
                reader = csv.reader(file)
                error_uuids = {row[0] for row in reader}
            self.table.blockSignals(True)
            for row in range(self.table.rowCount()):
                uuid_item = self.table.item(row, 0)
                if uuid_item and uuid_item.text() in error_uuids:
                    self.table.setRowHidden(row, False)
                else:
                    self.table.setRowHidden(row, True)
            self.table.blockSignals(False)
            self._filter_error_active = True
            QMessageBox.information(self, "Info", "Filtrage des erreurs terminé.")
        except FileNotFoundError:
            QMessageBox.warning(
                self, "Erreur", "Le fichier entry_error.csv est introuvable."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Une erreur s'est produite: {e}")

    def clear_error_file(self):
        try:
            with open("entry_error.csv", "w", encoding="utf-8") as file:
                pass
            QMessageBox.information(
                self, "Succès", "les signals ont été effacé avec succès."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Une erreur s'est produite: {e}")
        self._filter_error_active = False
        self.reload_records()

    def edit_selected_cell(self):
        selected_items = self.table.selectedItems()
        if selected_items:
            self.table.editItem(selected_items[0])

    def filter_by_date_range(self, start=None, end=None):
        if start is None or end is None:
            result = DialogUtils.select_date_range(self)
            if not result:
                self._filter_date_active = False
                return
            start, end = result
        records = self.db_manager.fetch_record_by_creation_date(start, end)
        if not records:
            QMessageBox.information(
                self, "Info", "Aucune entrée trouvée pour cette plage de dates."
            )
            self._filter_date_active = False
            return
        self._render_table(records)
        self._filter_date_active = True
        self._last_date_range = (start, end)

    def handle_favorite_toggle(self, uuid, is_fav):
        # Met à jour le statut favori en base
        if is_fav:
            self.db_manager.set_favorite(uuid, False)
        else:
            self.db_manager.set_favorite(uuid, True)
        # Met à jour uniquement le bouton favori de la ligne concernée
        for row in range(self.table.rowCount()):
            uuid_item = self.table.item(row, 0)
            if uuid_item and uuid_item.text() == uuid:
                # On doit reconstruire le record minimal pour _create_fav_button
                record = {
                    "UUID": uuid,
                    "media_file": (
                        self.table.item(row, 1).text()
                        if self.table.item(row, 1)
                        else ""
                    ),
                    "question": (
                        self.table.item(row, 2).text()
                        if self.table.item(row, 2)
                        else ""
                    ),
                    "response": (
                        self.table.item(row, 3).text()
                        if self.table.item(row, 3)
                        else ""
                    ),
                    "creation_date": (
                        self.table.item(row, 4).text()
                        if self.table.item(row, 4)
                        else ""
                    ),
                    "attribution": (
                        self.table.item(row, 5).text()
                        if self.table.item(row, 5)
                        else "no-attribution"
                    ),
                }
                self.table.setCellWidget(row, 7, self._create_fav_button(record))
                break

    def move_records(self):
        from PySide6.QtWidgets import QFileDialog

        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self,
                "Erreur",
                "Veuillez sélectionner un ou plusieurs entrées à déplacer par CLIQUER sur les NUMÉROs des lignes.",
            )
            return

        # Boîte de dialogue non bloquante pour choisir la base cible
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setNameFilter("Base de données (*.db)")
        file_dialog.setWindowTitle("Sélectionner la base de destination")
        file_dialog.fileSelected.connect(
            lambda path: self._move_records_to_db(path, selected_rows)
        )
        file_dialog.show()

    def _move_records_to_db(self, target_db_path, selected_rows):
        if not target_db_path:
            return
        from db import DatabaseManager

        moved = 0
        # Créer une connexion temporaire à la base cible
        target_db = DatabaseManager(target_db_path)
        for index in selected_rows:
            row = index.row()
            record = {
                "UUID": self.table.item(row, 0).text(),
                "media_file": self.table.item(row, 1).text(),
                "question": self.table.item(row, 2).text(),
                "response": self.table.item(row, 3).text(),
                "creation_date": self.table.item(row, 4).text(),
                "attribution": (
                    self.table.item(row, 5).text()
                    if self.table.item(row, 5)
                    else "no-attribution"
                ),
            }
            try:
                # Utiliser DatabaseManager pour insérer dans la base cible (il gère le chemin audio)
                target_db.insert_record(
                    media_file=record["media_file"],
                    question=record["question"],
                    response=record["response"],
                    UUID=record["UUID"],
                    creation_date=record["creation_date"],
                    attribution=record["attribution"],
                )
                # Supprimer de la base courante
                self.db_manager.delete_record(record["UUID"])
                moved += 1
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Erreur",
                    f"Erreur lors du déplacement de l'entrée UUID: {record['UUID']}\n{e}",
                )
        if moved:
            QMessageBox.information(
                self,
                "Succès",
                f"{moved} entrée(s) déplacée(s) avec succès. Les fichiers audio ont été déplacés automatiquement.",
            )
        self.load_records()

    def _button_with_label(self, button, label):
        # Retourne un widget horizontal avec le bouton et un QLabel transparent pour accessibilité Alt+()
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(button)
        layout.addWidget(label)
        return container

    def _create_fav_button(self, record):
        """Crée un bouton favori configuré selon l'état favori du record."""

        def safe_icon(path):
            if not os.path.exists(path):
                logger.error(f"Icône non trouvée: {path}")
            return QIcon(path)

        is_fav = self.db_manager.is_favorite(record["UUID"])
        fav_btn = QPushButton()
        fav_btn.setIconSize(QSize(32, 32))
        if is_fav:
            fav_btn.setIcon(safe_icon("assets/icons/favorite-cancel.png"))
            fav_btn.setToolTip("Annuler favori (Alt+F)")
            fav_btn.setAccessibleName("Annuler favori")
            fav_btn.setStyleSheet(
                "background-color: #b5197e; color: #333; font-weight: bold; border: 2px solid #c14a6c;"
            )
            fav_btn.clicked.connect(
                lambda checked, uuid=record["UUID"]: self.handle_favorite_toggle(
                    uuid, True
                )
            )
        else:
            fav_btn.setIcon(safe_icon("assets/icons/favorite.png"))
            fav_btn.setToolTip("Marquer comme favori (Alt+F)")
            fav_btn.setAccessibleName("Favori")
            fav_btn.setStyleSheet(
                "background-color: #504d4f; color: #333; font-weight: bold;"
            )
            fav_btn.clicked.connect(
                lambda checked, uuid=record["UUID"]: self.handle_favorite_toggle(
                    uuid, False
                )
            )
        fav_btn.setShortcut(QKeySequence("Alt+F"))
        fav_label = QLabel("&F")
        fav_label.setVisible(False)
        return self._button_with_label(fav_btn, fav_label)

    def _render_table(self, records):
        """Affiche la table avec la liste d'enregistrements fournie."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            uuid_item = QTableWidgetItem(record["UUID"])
            uuid_item.setFlags(uuid_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, uuid_item)
            self.table.setItem(row, 1, QTableWidgetItem(record["media_file"]))
            self.table.setItem(row, 2, QTableWidgetItem(record["question"]))
            self.table.setItem(row, 3, QTableWidgetItem(record["response"]))
            creation_date_item = QTableWidgetItem(record["creation_date"])
            creation_date_item.setFlags(creation_date_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, creation_date_item)
            self.table.setItem(
                row, 5, QTableWidgetItem(record.get("attribution", "no-attribution"))
            )
            # Bouton Lire
            play_btn = QPushButton()
            play_btn.setIcon(QIcon("assets/icons/play.png"))
            play_btn.setIconSize(QSize(32, 32))
            play_btn.setToolTip("Lire le média (Alt+A)")
            play_btn.setAccessibleName("Lire le média")
            play_btn.clicked.connect(
                lambda checked, media_file=record["media_file"]: self.play_media_file(
                    media_file
                )
            )
            play_btn.setShortcut(QKeySequence("Alt+A"))
            play_btn.setStyleSheet(
                "background-color: #3c697d; border-radius: 8px; margin: 2px;"
            )
            play_label = QLabel("&A")
            play_label.setVisible(False)
            self.table.setCellWidget(
                row, 6, self._button_with_label(play_btn, play_label)
            )
            # Bouton Favori
            self.table.setCellWidget(row, 7, self._create_fav_button(record))
        self.resize_table_columns()
        self.table.blockSignals(False)
