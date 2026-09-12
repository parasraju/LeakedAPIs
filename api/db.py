import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class Database:
    def __init__(self, db_path: str = "found_keys.db"):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._lock = threading.Lock()

    def initialize(self):
        with self._lock:
            self._conn.executescript("""
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
            CREATE TABLE IF NOT EXISTS scan_progress (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                query_index     INTEGER NOT NULL DEFAULT 0,
                page            INTEGER NOT NULL DEFAULT 1,
                query_text      TEXT,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(created_at);
            CREATE TABLE IF NOT EXISTS blocked_keys (
                key         TEXT PRIMARY KEY,
                blocked_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            -- severity and cluster for Phase 3/4, add column if missing (idempotent)
            CREATE TABLE IF NOT EXISTS _migrate_check (id INTEGER);
            """)
            self._conn.commit()
            # add severity column if not exists (for existing DBs)
            try:
                self._conn.execute("ALTER TABLE keys ADD COLUMN severity TEXT DEFAULT 'low'")
            except Exception:
                pass
            try:
                self._conn.execute("ALTER TABLE keys ADD COLUMN cluster_id TEXT")
            except Exception:
                pass
            try:
                self._conn.execute("ALTER TABLE keys ADD COLUMN content_hash TEXT")
            except Exception:
                pass
            self._conn.commit()

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM blocked_keys WHERE key=?", (key,)).fetchone()
            return row is not None

    def _severity(self, service: str, valid: bool, path: str) -> str:
        if not valid:
            return "low"
        critical = {"OpenAI", "Stripe", "AWSKey", "GitHub", "SlackBot", "Pinecone", "Supabase", "Firebase"}
        high = {"Anthropic", "GoogleGemini", "SendGrid", "GitLab", "Cloudflare", "Twilio"}
        pl = path.lower()
        is_env = ".env" in pl or "credentials" in pl or "secret" in pl
        if service in critical and is_env:
            return "critical"
        if service in critical:
            return "high"
        if service in high and is_env:
            return "high"
        return "medium"

    def _cluster_id(self, key: str) -> str:
        # SimHash lite: hash of normalized key prefix + service
        return hashlib.md5(key[:16].encode()).hexdigest()[:8]

    def add_key(
        self,
        key: str,
        service: str,
        valid: bool,
        file_url: str = "",
        repo: str = "",
        owner: str = "",
        repo_url: str = "",
        path: str = "",
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        severity = self._severity(service, valid, path)
        cluster = self._cluster_id(key)
        content_h = hashlib.md5(f"{repo}:{path}".encode()).hexdigest()[:12] if repo else ""
        with self._lock:
            # check inside lock to avoid race with clear_invalid_keys
            row = self._conn.execute("SELECT 1 FROM blocked_keys WHERE key=?", (key,)).fetchone()
            if row is not None:
                return False
            self._conn.execute(
                """
                INSERT OR IGNORE INTO keys
                (key, service, file_url, repo, owner, repo_url, path,
                 valid, severity, cluster_id, content_hash, first_seen, last_seen, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    key,
                    service,
                    file_url,
                    repo,
                    owner,
                    repo_url,
                    path,
                    int(valid),
                    severity,
                    cluster,
                    content_h,
                    now,
                    now,
                    now,
                ),
            )
            self._conn.execute(
                """
                UPDATE keys SET last_seen=?, checked_at=?, valid=?, severity=?, cluster_id=?, content_hash=?, file_url=?, repo=?,
                                owner=?, repo_url=?, path=?
                WHERE key=?
            """,
                (now, now, int(valid), severity, cluster, content_h, file_url, repo, owner, repo_url, path, key),
            )
            self._conn.commit()
            return True

    def key_exists(self, key: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM keys WHERE key=?", (key,)).fetchone()
            return row is not None

    def get_keys(
        self, service: str | None = None, valid_only: bool = False, limit: int = 200
    ) -> list[dict]:
        with self._lock:
            sql = "SELECT * FROM keys WHERE 1=1"
            params = []
            if service:
                sql += " AND service=?"
                params.append(service)
            if valid_only:
                sql += " AND valid=1"
            sql += " ORDER BY last_seen DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def log_scan(self, query: str, page: int, items_returned: int, keys_found: int):
        with self._lock:
            self._conn.execute(
                "INSERT INTO scan_log (query, page, items_returned, keys_found) VALUES (?, ?, ?, ?)",
                (query, page, items_returned, keys_found),
            )
            self._conn.commit()

    def add_activity(self, message: str, level: str = "info"):
        with self._lock:
            self._conn.execute(
                "INSERT INTO activity_log (message, level) VALUES (?, ?)",
                (message, level),
            )
            self._conn.commit()

    def get_activity(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM keys").fetchone()[0]
            valid = self._conn.execute("SELECT COUNT(*) FROM keys WHERE valid=1").fetchone()[0]
            invalid = self._conn.execute("SELECT COUNT(*) FROM keys WHERE valid=0").fetchone()[0]
            services = self._conn.execute(
                "SELECT service, COUNT(*) as cnt FROM keys GROUP BY service ORDER BY cnt DESC"
            ).fetchall()
            recent = self._conn.execute(
                "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            return {
                "total": total,
                "valid": valid,
                "invalid": invalid,
                "services": [dict(s) for s in services],
                "recent_activity": [dict(r) for r in recent],
            }

    def save_progress(self, query_index: int, page: int, query_text: str = ""):
        with self._lock:
            self._conn.execute("DELETE FROM scan_progress")
            self._conn.execute(
                "INSERT INTO scan_progress (query_index, page, query_text) VALUES (?, ?, ?)",
                (query_index, page, query_text),
            )
            self._conn.commit()

    def load_progress(self):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scan_progress ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                return {
                    "query_index": row["query_index"],
                    "page": row["page"],
                    "query_text": row["query_text"],
                }
            return None

    def clear_progress(self):
        with self._lock:
            self._conn.execute("DELETE FROM scan_progress")
            self._conn.commit()

    def clear_invalid_keys(self) -> int:
        with self._lock:
            rows = self._conn.execute("SELECT key FROM keys WHERE valid=0").fetchall()
            keys = [r["key"] for r in rows]
            if keys:
                self._conn.executemany(
                    "INSERT OR IGNORE INTO blocked_keys (key) VALUES (?)",
                    [(k,) for k in keys],
                )
            cur = self._conn.execute("DELETE FROM keys WHERE valid=0")
            count = cur.rowcount
            self._conn.commit()
            return count

    def close(self):
        with self._lock:
            self._conn.close()
