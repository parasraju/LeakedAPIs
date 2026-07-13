import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path: str = "found_keys.db"):
        self.db_path = Path(db_path)
        self._local = threading.local()

    @property
    def conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def initialize(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT NOT NULL UNIQUE,
                service     TEXT NOT NULL,
                file_url    TEXT,
                repo        TEXT,
                owner       TEXT,
                repo_url    TEXT,
                path        TEXT,
                valid       INTEGER NOT NULL DEFAULT 0,
                checked_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                query           TEXT,
                page            INTEGER,
                items_returned  INTEGER DEFAULT 0,
                keys_found      INTEGER DEFAULT 0,
                scanned_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message     TEXT,
                level       TEXT DEFAULT 'info',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_keys_service  ON keys(service);
            CREATE INDEX IF NOT EXISTS idx_keys_valid    ON keys(valid);
            CREATE INDEX IF NOT EXISTS idx_keys_key      ON keys(key);
            CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(created_at);
        """)
        self.conn.commit()

    def add_key(self, key: str, service: str, valid: bool,
                file_url: str = "", repo: str = "", owner: str = "",
                repo_url: str = "", path: str = "") -> bool:
        now = datetime.utcnow().isoformat()
        try:
            self.conn.execute("""
                INSERT INTO keys (key, service, file_url, repo, owner, repo_url, path,
                                  valid, first_seen, last_seen, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (key, service, file_url, repo, owner, repo_url, path,
                  int(valid), now, now, now))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.conn.execute("""
                UPDATE keys SET last_seen=?, checked_at=?, valid=?, file_url=?, repo=?,
                                owner=?, repo_url=?, path=?
                WHERE key=?
            """, (now, now, int(valid), file_url, repo, owner, repo_url, path, key))
            self.conn.commit()
            return False

    def key_exists(self, key: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM keys WHERE key=?", (key,)).fetchone()
        return row is not None

    def get_keys(self, service: Optional[str] = None,
                 valid_only: bool = False, limit: int = 200) -> List[Dict]:
        sql = "SELECT * FROM keys WHERE 1=1"
        params = []
        if service:
            sql += " AND service=?"
            params.append(service)
        if valid_only:
            sql += " AND valid=1"
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def log_scan(self, query: str, page: int, items_returned: int, keys_found: int):
        self.conn.execute(
            "INSERT INTO scan_log (query, page, items_returned, keys_found) VALUES (?, ?, ?, ?)",
            (query, page, items_returned, keys_found)
        )
        self.conn.commit()

    def add_activity(self, message: str, level: str = "info"):
        self.conn.execute(
            "INSERT INTO activity_log (message, level) VALUES (?, ?)",
            (message, level)
        )
        self.conn.commit()

    def get_activity(self, limit: int = 100) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> Dict:
        total = self.conn.execute("SELECT COUNT(*) FROM keys").fetchone()[0]
        valid = self.conn.execute("SELECT COUNT(*) FROM keys WHERE valid=1").fetchone()[0]
        invalid = self.conn.execute("SELECT COUNT(*) FROM keys WHERE valid=0").fetchone()[0]
        services = self.conn.execute(
            "SELECT service, COUNT(*) as cnt FROM keys GROUP BY service ORDER BY cnt DESC"
        ).fetchall()
        recent = self.conn.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "services": [dict(s) for s in services],
            "recent_activity": [dict(r) for r in recent],
        }

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
