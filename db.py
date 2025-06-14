from __future__ import annotations

import re
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from datetime import date, datetime
import uuid
from gtts import gTTS  # Importer gTTS pour générer des fichiers audio
import os
from logger import logger  # Remplacer l'import de logging par le logger centralisé
from common_methods import MediaUtils


class DatabaseManager:

    def __init__(self, db_path: str, language_code: str = "fr"):
        try:
            # Créer le dossier parent si nécessaire
            self.db_path = db_path
            self.db_dir = os.path.dirname(db_path)
            self.db_name = os.path.basename(db_path)
            if self.db_dir and not os.path.exists(self.db_dir):
                os.makedirs(self.db_dir, exist_ok=True)
            self.language_code = language_code
            self.connection_name = (
                f"connection_{uuid.uuid4()}"  # Utiliser une connexion unique
            )
            base_name = self.db_name.replace(".db", "-audio")
            self.audio_dir = f"assets/audio/{base_name}"
            os.makedirs(self.audio_dir, exist_ok=True)
            self.db = QSqlDatabase.addDatabase("QSQLITE", self.connection_name)
            self.db.setDatabaseName(db_path)
            if not self.db.open():
                raise Exception("Failed to open database")
            logger.info(f"{self.db_name} opened.")
            logger.info(f"databased located in {self.db_dir}.")
            self.create_tables()
        except Exception:
            raise

    def create_tables(self):
        query = QSqlQuery(self.db)
        query.exec_(
            """
            CREATE TABLE IF NOT EXISTS records (
                UUID TEXT PRIMARY KEY,
                media_file TEXT NOT NULL,
                question TEXT NOT NULL,
                response TEXT NOT NULL,
                creation_date TEXT NOT NULL,
                custom_media INTEGER DEFAULT 0,
                attribution TEXT NOT NULL DEFAULT 'no-attribution',
                is_favorite INTEGER DEFAULT 0
            )
            """
        )

    def auto_generate_audio(
        self, question: str, response: str, language_code: str
    ) -> str:
        """Génère un fichier audio basé sur la question et toutes les réponses séparées par ';'.
        Tous les (?) de la question sont remplacés dans l'ordre par les réponses.
        Retourne le chemin du fichier généré.
        """
        responses = [r.strip() for r in response.split(";") if r.strip()]
        if not responses:
            raise Exception("Aucune réponse fournie pour la génération audio.")
        q = question

        def replace_nth(match):
            replace_nth.idx += 1
            return (
                responses[replace_nth.idx - 1]
                if replace_nth.idx <= len(responses)
                else match.group(0)
            )

        replace_nth.idx = 0
        audio_text = re.sub(r"\(\?\)", replace_nth, q)

        from common_methods import TextUtils

        # Utiliser toute la chaîne si elle fait moins de 20 caractères
        base_name = TextUtils.clean_filename(
            responses[0][:20] if len(responses[0]) > 20 else responses[0]
        )
        file_name = f"{base_name}.mp3"
        media_file_path = os.path.join(self.audio_dir, file_name)
        tts = gTTS(text=audio_text, lang=language_code)
        try:
            tts.save(media_file_path)
        except Exception as e:
            raise Exception(f"Échec de la génération de l'audio : {e}")
        return media_file_path

    def insert_record(
        self,
        media_file: str,
        question: str,
        response: str,
        start_time_ms: int = None,
        end_time_ms: int = None,
        UUID: str = None,
        creation_date: str = None,
        attribution: str = "no-attribution",
    ):
        try:
            # Vérification du nombre de (?) et de réponses
            nb_placeholders = question.count("(?)")
            nb_reponses = len([r for r in response.split(";") if r.strip()])
            if nb_placeholders != nb_reponses:
                raise Exception(
                    f"Le nombre de '(?)' dans la question ({nb_placeholders}) ne correspond pas au nombre de réponses fournies ({nb_reponses})."
                )

            # Vérifier si un entrée avec la même question et réponse existe déjà (AVANT toute opération)
            query = QSqlQuery(self.db)
            query.prepare(
                """
                SELECT COUNT(*) FROM records
                WHERE question = ? AND response = ?
                """
            )
            query.addBindValue(question)
            query.addBindValue(response)
            if not query.exec_():
                raise Exception(
                    f"Failed to check for duplicate record: {query.lastError().text()}"
                )
            query.next()
            if query.value(0) > 0:
                return 1

            UUID = UUID or str(uuid.uuid4())
            if creation_date:
                try:
                    datetime.strptime(creation_date, "%Y-%m-%d")
                except ValueError:
                    raise Exception("Le format de la date doit être 'YYYY-MM-DD'")
            else:
                creation_date = datetime.now().strftime("%Y-%m-%d")

            if not media_file:
                media_file = self.auto_generate_audio(
                    question, response, self.language_code
                )
                custom_media = 0
            else:
                try:
                    media_file = MediaUtils.MediaFileProcessing.process_media_file(
                        media_file, self.audio_dir, start_time_ms, end_time_ms
                    )
                except Exception as e:
                    raise Exception(f"Erreur lors du traitement du média : {e}")
                custom_media = 1

            query.prepare(
                """
                INSERT INTO records (UUID, media_file, question, response, creation_date, custom_media, attribution)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            )
            query.addBindValue(UUID)
            query.addBindValue(media_file)
            from common_methods import TextUtils

            query.addBindValue(TextUtils.normalize_special_characters(question))
            query.addBindValue(TextUtils.normalize_special_characters(response))
            query.addBindValue(creation_date)
            query.addBindValue(custom_media)
            query.addBindValue(attribution or "no-attribution")
            if not query.exec_():
                return 1
                raise Exception(f"Failed to insert record: {query.lastError().text()}")
            else:
                return 0
        except Exception:
            raise

    def _fetch_records(self, query_text: str, params: list = None) -> list:
        """Méthode générique pour exécuter une requête SELECT et récupérer les résultats."""
        try:
            query = QSqlQuery(self.db)
            query.prepare(query_text)
            if params:
                for param in params:
                    query.addBindValue(param)
            if not query.exec_():
                raise Exception(f"Failed to execute query: {query.lastError().text()}")

            records = []
            while query.next():
                records.append(
                    {
                        "UUID": query.value(0),
                        "media_file": query.value(1),
                        "question": query.value(2),
                        "response": query.value(3),
                        "creation_date": query.value(4),
                        "attribution": (
                            query.value(6)
                            if query.record().count() > 6
                            else "no-attribution"
                        ),
                    }
                )
            return records
        except Exception:
            return []

    def fetch_all_records(self):
        """Récupère tous les enregistrements de la base de données."""
        query_text = """
            SELECT UUID, media_file, question, response, creation_date, custom_media, attribution
            FROM records
        """
        return self._fetch_records(query_text)

    def fetch_record_by_creation_date(self, start: date, finish: date):
        """Récupère les enregistrements entre deux dates."""
        query_text = """
            SELECT UUID, media_file, question, response, creation_date, custom_media, attribution
            FROM records
            WHERE creation_date BETWEEN ? AND ?
        """
        params = [start.isoformat(), finish.isoformat()]
        return self._fetch_records(query_text, params)

    def fetch_record_by_uuid(self, uuid):
        """Récupère un ou plusieurs enregistrements depuis la base de données par UUID ou liste d'UUIDs (optimisé)."""
        if isinstance(uuid, list):
            if not uuid:
                return []
            # Une seule requête SQL avec IN (?, ?, ...)
            placeholders = ",".join(["?"] * len(uuid))
            query_text = f"""
                SELECT UUID, media_file, question, response, creation_date, custom_media, attribution
                FROM records
                WHERE UUID IN ({placeholders})
            """
            records = self._fetch_records(query_text, uuid)
            # Trie les résultats selon l'ordre de uuid
            uuid_to_record = {rec["UUID"]: rec for rec in records}
            return [uuid_to_record[u] for u in uuid if u in uuid_to_record]
        # Cas unique (str)
        query_text = """
            SELECT UUID, media_file, question, response, creation_date, custom_media, attribution
            FROM records
            WHERE UUID = ?
        """
        records = self._fetch_records(query_text, [uuid])
        return records[0] if records else None

    def update_record(
        self,
        record_id: str,
        new_media_file: str,
        new_question: str,
        new_response: str,
        new_attribution: str = None,
    ) -> bool:
        try:
            """Met à jour un entrée existant dans la base de données."""
            # Récupérer l'entrée existante
            query = QSqlQuery(self.db)
            query.prepare(
                """
                SELECT media_file, question, response, custom_media FROM records WHERE UUID = ?
                """
            )
            query.addBindValue(record_id)
            if not query.exec_():
                raise Exception(f"Failed to fetch record: {query.lastError().text()}")

            if not query.next():
                raise Exception("Record not found")

            old_media_file = query.value(0)
            old_question = query.value(1)
            old_response = query.value(2)
            custom_media = query.value(3)
            custom_deleted = False
            if (
                len(new_media_file) <= 2
            ):  # en cas quelques espaces sont entrées par hasard
                custom_media = 0
                custom_deleted = True
                logger.info(
                    f"custom media for {record_id} is deleted. An automated audio file will be generated."
                )
            else:
                if new_media_file != old_media_file:
                    try:
                        new_media_file = (
                            MediaUtils.MediaFileProcessing.process_media_file(
                                new_media_file, self.audio_dir
                            )
                        )
                    except Exception as e:
                        raise Exception(
                            f"Erreur lors du traitement du nouveau média : {e}"
                        )
                    custom_media = 1

            # Vérifier si le média doit être régénéré
            if custom_media != 1 and (
                new_response != old_response
                or new_question != old_question
                or custom_deleted == True
            ):
                if os.path.exists(old_media_file):
                    try:
                        os.remove(old_media_file)  # Supprimer l'ancien fichier média
                    except Exception as e:
                        raise Exception(
                            f"Échec de la suppression de l'ancien média : {e}"
                        )
                from common_methods import TextUtils

                new_question = TextUtils.normalize_special_characters(new_question)
                new_response = TextUtils.normalize_special_characters(new_response)
                new_media_file = self.auto_generate_audio(
                    new_question,
                    new_response,
                    self.language_code,
                )

            # Mettre à jour l'entrée
            query.prepare(
                """
                UPDATE records
                SET media_file = ?, question = ?, response = ?, custom_media = ?, attribution = ?
                WHERE UUID = ?
                """
            )
            query.addBindValue(new_media_file)
            query.addBindValue(new_question)
            query.addBindValue(new_response)
            query.addBindValue(custom_media)
            query.addBindValue(new_attribution or "no-attribution")
            query.addBindValue(record_id)
            if not query.exec_():
                raise Exception(f"Failed to update record: {query.lastError().text()}")
            return True
        except Exception:
            return False

    def delete_record(self, record_id: str) -> bool:
        try:
            """Supprime un entrée de la base de données."""
            # D'abord récupérer le chemin du fichier média
            query = QSqlQuery(self.db)
            query.prepare("SELECT media_file FROM records WHERE UUID = ?")
            query.addBindValue(record_id)

            if not query.exec_():
                raise Exception(
                    f"Échec de la récupération du fichier média: {query.lastError().text()}"
                )

            media_file_path = None
            if query.next():
                media_file_path = query.value(0)

            # Ensuite supprimer l'entrée de la base de données
            query = QSqlQuery(self.db)
            query.prepare("DELETE FROM records WHERE UUID = ?")
            query.addBindValue(record_id)
            if not query.exec_():
                raise Exception(f"Failed to delete record: {query.lastError().text()}")
            self.db.commit()  # Valider les modifications

            # Vérifier s'il reste d'autres entrées qui utilisent le même fichier média
            if media_file_path:
                query = QSqlQuery(self.db)
                query.prepare("SELECT COUNT(*) FROM records WHERE media_file = ?")
                query.addBindValue(media_file_path)
                if not query.exec_():
                    raise Exception(
                        f"Échec de la vérification des références du média: {query.lastError().text()}"
                    )
                if query.next() and query.value(0) == 0:
                    # Personne d'autre ne référence ce fichier, on peut le supprimer
                    if os.path.exists(media_file_path):
                        try:
                            os.remove(media_file_path)
                            print(f"Fichier média supprimé: {media_file_path}")
                        except Exception as e:
                            print(f"Échec de la suppression du fichier média: {e}")
            return True
        except Exception:
            return False

    def set_favorite(self, entry_uuid, is_fav: bool):
        """Marque ou démarque une entrée comme favorite dans la base."""
        query = QSqlQuery(self.db)
        query.prepare("UPDATE records SET is_favorite=? WHERE UUID=?")
        query.addBindValue(1 if is_fav else 0)
        query.addBindValue(entry_uuid)
        if not query.exec_():
            raise Exception(
                f"Erreur lors de la mise à jour du favori: {query.lastError().text()}"
            )
        self.db.commit()

    def is_favorite(self, entry_uuid):
        """Retourne True si l'entrée est favorite."""
        query = QSqlQuery(self.db)
        query.prepare("SELECT is_favorite FROM records WHERE UUID=?")
        query.addBindValue(entry_uuid)
        if not query.exec_():
            return False
        if query.next():
            return bool(query.value(0))
        return False

    def fetch_favorite_records(self):
        """Retourne tous les enregistrements favoris sous forme de liste de dicts."""
        query_text = """
            SELECT UUID, media_file, question, response, creation_date, custom_media, attribution
            FROM records
            WHERE is_favorite=1
        """
        return self._fetch_records(query_text)

    def close_connection(self):
        """Ferme la connexion à la base de données."""
        # Attendre que toutes les requêtes soient terminées avant de fermer la base
        QSqlDatabase.database(self.connection_name).transaction()
        QSqlDatabase.database(self.connection_name).commit()

        if self.db.isOpen():
            self.db.close()  # Fermer la connexion

        # Nettoyer explicitement les requêtes actives
        QSqlQuery(self.db).clear()

        # S'assurer que la connexion est supprimée proprement
        if QSqlDatabase.contains(self.connection_name):
            try:
                QSqlDatabase.removeDatabase(self.connection_name)
                logger.info(f"{self.db_name} closed.")
            except RuntimeError as e:
                logger.warning(
                    f"Erreur lors de la suppression de la connexion avec {self.db_path} : {e}"
                )
