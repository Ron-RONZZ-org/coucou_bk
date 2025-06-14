import sqlite3

csv_path = "favourites-tatoeba-fr.csv"
db_path = "tatoeba-fr.db"

# 1. Lire tous les UUID du fichier CSV
with open(csv_path, "r", encoding="utf-8") as f:
    uuids = [line.strip() for line in f if line.strip()]

print(f"{len(uuids)} UUIDs à migrer.")

# 2. Connexion à la base SQLite
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 3. Vérifier que la colonne existe (sinon, l'ajouter)
cur.execute("PRAGMA table_info(records)")
columns = [row[1] for row in cur.fetchall()]
if "is_favorite" not in columns:
    print("Ajout de la colonne is_favorite...")
    cur.execute("ALTER TABLE records ADD COLUMN is_favorite INTEGER DEFAULT 0")
    conn.commit()

# 4. Mettre à jour chaque UUID
updated = 0
for uuid in uuids:
    cur.execute("UPDATE records SET is_favorite=1 WHERE UUID=?", (uuid,))
    if cur.rowcount > 0:
        updated += 1

conn.commit()
conn.close()

print(f"Migration terminée : {updated} favoris mis à jour dans la base {db_path}.")
