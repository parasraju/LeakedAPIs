import time

import pytest
import requests

from ApiInstructor import Scanner, TokenConfig
from api.db import Database


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json


@pytest.fixture
def no_network_validators(monkeypatch):
    monkeypatch.setattr("ApiInstructor.VALIDATORS", {})


def two_token_config():
    return TokenConfig(tokens=["token-a", "token-b"])


def test_search_returns_json_on_success(monkeypatch):
    scanner = Scanner(two_token_config())

    def fake_get(url, headers, params, timeout):
        assert headers["Authorization"] == "token token-a"
        return FakeResponse(status_code=200, json_data={"items": []})

    monkeypatch.setattr(scanner._session, "get", fake_get)
    assert scanner.search_github("query") == {"items": []}


def test_search_rotates_token_on_rate_limit(monkeypatch):
    config = two_token_config()
    scanner = Scanner(config)
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(headers)
        if len(calls) == 1:
            return FakeResponse(status_code=403)
        return FakeResponse(status_code=200, json_data={"items": []})

    monkeypatch.setattr(scanner._session, "get", fake_get)
    assert scanner.search_github("query") == {"items": []}
    assert config.current_idx == 1
    assert calls[1]["Authorization"] == "token token-b"


def test_search_backs_off_when_all_tokens_exhausted(monkeypatch):
    import threading

    stop_event = threading.Event()
    scanner = Scanner(TokenConfig(tokens=["token-a"]), stop_event=stop_event)
    sleeps = []

    def fake_get(url, headers, params, timeout):
        return FakeResponse(status_code=403)

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 5:
            stop_event.set()

    monkeypatch.setattr(scanner._session, "get", fake_get)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    assert scanner.search_github("query") is None
    assert len(sleeps) == 5


def test_search_returns_none_on_network_error(monkeypatch):
    scanner = Scanner(two_token_config())

    def fake_get(url, headers, params, timeout):
        raise requests.Timeout("boom")

    monkeypatch.setattr(scanner._session, "get", fake_get)
    assert scanner.search_github("query") is None


def test_search_stops_when_stop_event_set(monkeypatch):
    import threading

    scanner = Scanner(two_token_config(), stop_event=threading.Event())
    scanner.stop_event.set()

    def fake_get(url, headers, params, timeout):
        raise AssertionError("should not be called")

    monkeypatch.setattr(scanner._session, "get", fake_get)
    assert scanner.search_github("query") is None


def test_get_file_content_falls_back_to_default_branch(monkeypatch):
    scanner = Scanner(two_token_config())
    item = {
        "repository": {"full_name": "owner/repo", "default_branch": "main"},
        "html_url": "https://github.com/owner/repo/blob/abc123/file.env",
        "path": "file.env",
    }
    responses = iter([FakeResponse(status_code=404), FakeResponse(status_code=200, text="SECRET")])

    def fake_get(url, timeout):
        return next(responses)

    monkeypatch.setattr(scanner._session, "get", fake_get)
    assert scanner.get_file_content(item) == "SECRET"


def test_scan_results_stores_found_keys(tmp_path, monkeypatch, no_network_validators):
    config = two_token_config()
    db = Database(str(tmp_path / "scan.db"))
    db.initialize()
    scanner = Scanner(config, db=db, result_file=str(tmp_path / "out.json"))
    item = {
        "html_url": "https://github.com/owner/repo/blob/main/.env",
        "repository": {
            "full_name": "owner/repo",
            "owner": {"login": "owner"},
            "html_url": "https://github.com/owner/repo",
            "default_branch": "main",
        },
        "path": ".env",
    }
    scanner.get_file_content = lambda item: "export const KEY='sk-12345678901234567890abcdefABCD';"
    results = {"items": [item]}

    found = scanner.scan_results(results)

    assert len(found) == 1
    assert found[0]["type"] == "OpenAI"
    assert db.key_exists(found[0]["key"])


def test_scan_results_skips_example_files(tmp_path):
    config = two_token_config()
    db = Database(str(tmp_path / "scan.db"))
    db.initialize()
    scanner = Scanner(config, db=db, result_file=str(tmp_path / "out.json"))
    scanner.get_file_content = lambda item: "sk-12345678901234567890abcdefABCD"
    results = {
        "items": [
            {
                "html_url": "https://github.com/o/r/blob/main/.env.example",
                "repository": {
                    "full_name": "o/r",
                    "owner": {"login": "o"},
                    "html_url": "https://github.com/o/r",
                },
                "path": ".env.example",
            }
        ]
    }

    assert scanner.scan_results(results) == []


def test_scan_text_results_finds_issue_keys(tmp_path, no_network_validators):
    config = two_token_config()
    db = Database(str(tmp_path / "scan.db"))
    db.initialize()
    scanner = Scanner(config, db=db, result_file=str(tmp_path / "out.json"))
    results = {
        "items": [
            {
                "title": "Found a key",
                "body": "The token is ghp_1234567890abcdef1234567890abcdef1234567890",
                "repository_url": "https://api.github.com/repos/owner/repo",
                "html_url": "https://github.com/owner/repo/issues/1",
            }
        ]
    }

    found = scanner.scan_text_results(results, "issue")

    assert len(found) == 1
    assert found[0]["repo"] == "owner/repo"
    assert db.key_exists(found[0]["key"])


def test_save_results_writes_json_and_db(tmp_path):
    config = two_token_config()
    db = Database(str(tmp_path / "scan.db"))
    db.initialize()
    out = tmp_path / "out.json"
    scanner = Scanner(config, db=db, result_file=str(out))

    scanner.save_results([{"key": "sk-found", "type": "OpenAI", "valid": True}])

    assert out.exists()
    assert db.key_exists("sk-found")


def test_save_results_swallows_serialization_error(tmp_path):
    config = two_token_config()
    db = Database(str(tmp_path / "scan.db"))
    db.initialize()
    scanner = Scanner(config, db=db, result_file=str(tmp_path / "out.json"))

    class Unserializable:
        pass

    scanner.save_results(
        [{"key": "sk-x", "type": "OpenAI", "valid": True, "extra": Unserializable()}]
    )
    assert db.key_exists("sk-x")


def test_run_loads_previous_results(tmp_path):
    config = two_token_config()
    db = Database(str(tmp_path / "scan.db"))
    db.initialize()
    out = tmp_path / "out.json"
    out.write_text('[{"key": "sk-1", "type": "OpenAI", "valid": true}]', encoding="utf-8")

    scanner = Scanner(config, db=db, result_file=str(out))

    assert scanner._load_previous_results() == [{"key": "sk-1", "type": "OpenAI", "valid": True}]
    assert scanner.existing_keys == {"sk-1"}


def test_run_tolerates_corrupt_progress_file(tmp_path):
    config = two_token_config()
    out = tmp_path / "out.json"
    out.write_text("{not valid json", encoding="utf-8")

    scanner = Scanner(config, result_file=str(out))

    assert scanner._load_previous_results() == []
