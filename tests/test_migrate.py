import json

from migrate import migrate


def test_migrate_imports_keys(tmp_path):
    json_path = tmp_path / "found_keys.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "key": "sk-12345678901234567890",
                    "type": "OpenAI",
                    "file_url": "https://github.com/o/r",
                    "repo": "o/r",
                    "valid": True,
                },
                {"key": "sk-bad"},
            ]
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "migrated.db"

    migrate(str(db_path), str(json_path))

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT key, service, valid FROM keys ORDER BY key").fetchall()
    assert rows == [
        ("sk-12345678901234567890", "OpenAI", 1),
        ("sk-bad", "?", 0),
    ]
    activity = conn.execute("SELECT message FROM activity_log").fetchall()
    assert "Migrated 2 keys" in activity[0][0]
    conn.close()


def test_migrate_tolerates_missing_json(tmp_path):
    db_path = tmp_path / "migrated.db"
    migrate(str(db_path), str(tmp_path / "does-not-exist.json"))

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='keys'"
    ).fetchall()
    assert tables
    conn.close()
