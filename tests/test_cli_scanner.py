import api.scanner as scanner_module
from api.db import Database
from api.scanner import Scanner


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


def make_scanner(tmp_path, tokens):
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return db, Scanner(tokens=tokens, db=db, max_pages=2, delay=0)


def test_cli_search_returns_json(monkeypatch, tmp_path):
    db, scanner = make_scanner(tmp_path, ["token-a"])

    def fake_get(url, headers, params, timeout):
        assert headers["Authorization"] == "token token-a"
        return FakeResponse(status_code=200, json_data={"items": []})

    monkeypatch.setattr(scanner_module.requests, "get", fake_get)
    assert scanner.search_github("query") == {"items": []}
    db.close()


def test_cli_search_rotates_token(monkeypatch, tmp_path):
    db, scanner = make_scanner(tmp_path, ["token-a", "token-b"])
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(headers)
        if len(calls) == 1:
            return FakeResponse(status_code=403)
        return FakeResponse(status_code=200, json_data={"items": []})

    monkeypatch.setattr(scanner_module.requests, "get", fake_get)
    assert scanner.search_github("query") == {"items": []}
    assert scanner.token_idx == 1
    assert calls[1]["Authorization"] == "token token-b"
    db.close()


def test_cli_search_returns_none_on_network_error(monkeypatch, tmp_path):
    db, scanner = make_scanner(tmp_path, ["token-a"])

    def fake_get(url, headers, params, timeout):
        raise scanner_module.requests.Timeout("slow")

    monkeypatch.setattr(scanner_module.requests, "get", fake_get)
    assert scanner.search_github("query") is None
    db.close()


def test_scan_file_ignores_placeholders(tmp_path):
    db, scanner = make_scanner(tmp_path, ["token-a"])
    matches = scanner.scan_file(
        "MY_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\nREAL_KEY=sk-12345678901234567890abcdefABCD\n"
    )
    assert ("OpenAI", "sk-12345678901234567890abcdefABCD") in matches
    db.close()


def test_run_stops_when_event_set(tmp_path):
    import threading

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    event = threading.Event()
    event.set()
    scanner = Scanner(tokens=["token-a"], db=db, stop_event=event, max_pages=2, delay=0)

    scanner.run()
    assert db._conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0] == 0
    db.close()
