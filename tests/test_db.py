from api.db import Database


def make_db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return db


def test_add_and_retrieve_keys(tmp_path):
    db = make_db(tmp_path)
    db.add_key("sk-test-123", "OpenAI", True, repo="owner/repo")
    db.add_key("sk-test-456", "OpenAI", False, repo="owner/repo")

    keys = db.get_keys()
    assert {k["key"] for k in keys} == {"sk-test-123", "sk-test-456"}

    valid = db.get_keys(valid_only=True)
    assert [k["key"] for k in valid] == ["sk-test-123"]

    filtered = db.get_keys(service="OpenAI")
    assert len(filtered) == 2


def test_add_key_is_idempotent_by_key(tmp_path):
    db = make_db(tmp_path)
    db.add_key("sk-same", "OpenAI", True)
    db.add_key("sk-same", "OpenAI", False)

    rows = db.get_keys(service="OpenAI")
    assert len(rows) == 1
    assert rows[0]["valid"] == 0


def test_key_exists(tmp_path):
    db = make_db(tmp_path)
    assert not db.key_exists("sk-nope")
    db.add_key("sk-yep", "GitHub", True)
    assert db.key_exists("sk-yep")


def test_progress_round_trip(tmp_path):
    db = make_db(tmp_path)
    assert db.load_progress() is None

    db.save_progress(3, 7, "ghp_ extension:env")
    progress = db.load_progress()
    assert progress["query_index"] == 3
    assert progress["page"] == 7
    assert progress["query_text"] == "ghp_ extension:env"

    db.save_progress(0, 1, "")
    assert db.load_progress()["query_index"] == 0

    db.clear_progress()
    assert db.load_progress() is None


def test_activity_log(tmp_path):
    db = make_db(tmp_path)
    db.add_activity("hello world", "info")
    rows = db.get_activity()
    assert len(rows) == 1
    assert rows[0]["message"] == "hello world"
    assert rows[0]["level"] == "info"


def test_stats(tmp_path):
    db = make_db(tmp_path)
    db.add_key("sk-a", "OpenAI", True)
    db.add_key("sk-b", "OpenAI", False)

    stats = db.get_stats()
    assert stats["total"] == 2
    assert stats["valid"] == 1
    assert stats["invalid"] == 1


def test_scan_log(tmp_path):
    db = make_db(tmp_path)
    db.log_scan("query", 1, 10, 3)
    rows = db._conn.execute("SELECT * FROM scan_log").fetchall()
    assert len(rows) == 1
    assert rows[0]["items_returned"] == 10
