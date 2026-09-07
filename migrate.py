"""One-off migration of the legacy ``found_keys.json`` into SQLite."""

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
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
"""


def migrate(db_path: str = "found_keys.db", json_path: str = "found_keys.json") -> None:
    db = sqlite3.connect(db_path)
    try:
        with db:
            db.executescript(SCHEMA)

        json_file = Path(json_path)
        if not json_file.exists():
            logger.info("No %s found - starting fresh", json_path)
            return
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        with db:
            for entry in data:
                try:
                    db.execute(
                        """INSERT OR IGNORE INTO keys
                        (key, service, file_url, repo, owner, repo_url, path, valid)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            entry.get("key", ""),
                            entry.get("type", "?"),
                            entry.get("file_url", ""),
                            entry.get("repo", ""),
                            entry.get("owner", ""),
                            entry.get("repo_url", ""),
                            entry.get("path", ""),
                            1 if entry.get("valid") else 0,
                        ),
                    )
                except sqlite3.Error as e:
                    logger.warning("Skipping malformed entry %r: %s", entry.get("key"), e)
                    continue
                count += 1
            db.execute(
                "INSERT INTO activity_log (message, level) VALUES (?, ?)",
                (f"Migrated {count} keys from {json_path}", "info"),
            )
        logger.info("Migrated %d keys", count)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    migrate()
