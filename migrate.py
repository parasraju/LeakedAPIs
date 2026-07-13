import json, sqlite3

db = sqlite3.connect("found_keys.db")
db.execute("PRAGMA journal_mode=WAL")
db.executescript("""
    CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE,
        service TEXT NOT NULL, file_url TEXT, repo TEXT, owner TEXT,
        repo_url TEXT, path TEXT, valid INTEGER NOT NULL DEFAULT 0,
        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS scan_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, page INTEGER,
        items_returned INTEGER DEFAULT 0, keys_found INTEGER DEFAULT 0,
        scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT,
        level TEXT DEFAULT 'info', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")

try:
    with open("../found_keys.json", encoding="utf-8") as f:
        data = json.load(f)
    count = 0
    for entry in data:
        try:
            db.execute("""INSERT OR IGNORE INTO keys
                (key, service, file_url, repo, owner, repo_url, path, valid)
                VALUES (?,?,?,?,?,?,?,?)""",
                (entry.get("key", ""), entry.get("type", "?"), entry.get("file_url", ""),
                 entry.get("repo", ""), entry.get("owner", ""), entry.get("repo_url", ""),
                 entry.get("path", ""), 1 if entry.get("valid") else 0))
            count += 1
        except Exception:
            pass
    db.commit()
    db.execute("INSERT INTO activity_log (message, level) VALUES (?, ?)",
               (f"Migrated {count} keys from found_keys.json", "info"))
    db.commit()
    print(f"Migrated {count} keys")
except FileNotFoundError:
    print("No ../found_keys.json found - starting fresh")
db.close()
