import pytest
import requests

import api.validators as validators


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


@pytest.fixture
def fake_get(monkeypatch):
    calls = []

    def install(response_chain):
        responses = iter(response_chain)

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return next(responses)

        monkeypatch.setattr(validators.requests, "get", fake_get)
        return calls

    return install


def test_openai_valid_key(fake_get):
    fake_get([FakeResponse(status_code=200)])
    assert validators.check_openai_key("sk-test-123") is True


def test_openai_invalid_key(fake_get):
    fake_get([FakeResponse(status_code=401)])
    assert validators.check_openai_key("sk-test-123") is False


def test_openai_network_error(monkeypatch):
    def raise_error(url, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(validators.requests, "get", raise_error)
    assert validators.check_openai_key("sk-test-123") is False


def test_huggingface_rejects_wrong_prefix(monkeypatch):
    assert validators.check_huggingface_key("sk-not-hf") is False


def test_telegram_valid_bot(fake_get):
    fake_get(
        [FakeResponse(status_code=200, json_data={"ok": True, "result": {"username": "my_bot"}})]
    )
    assert validators.check_telegram_bot_key("1234567890:ABCdef") is True


def test_telegram_invalid_bot(fake_get):
    fake_get([FakeResponse(status_code=200, json_data={"ok": False})])
    assert validators.check_telegram_bot_key("1234567890:ABCdef") is False


def test_telegram_non_json_error(fake_get):
    fake_get([FakeResponse(status_code=502, text="<html>bad gateway</html>")])
    assert validators.check_telegram_bot_key("1234567890:ABCdef") is False


def test_slack_valid_token(fake_get):
    fake_get([FakeResponse(status_code=200, json_data={"ok": True, "team": "acme"})])
    assert validators.check_slack_key("xoxb-token") is True


def test_slack_returns_error_field(fake_get):
    fake_get([FakeResponse(status_code=200, json_data={"ok": False, "error": "invalid_auth"})])
    assert validators.check_slack_key("xoxb-token") is False


def test_notion_valid_key(fake_get):
    fake_get(
        [
            FakeResponse(
                status_code=200,
                json_data={"bot": {"owner": {"workspace_name": "acme"}}},
            )
        ]
    )
    assert validators.check_notion_key("secret_abcdefghijklmnopqrstuvwxyz1234567890") is True


def test_validators_maps_every_supported_service():
    from api.patterns import SERVICES

    assert set(validators.VALIDATORS.keys()).issubset(set(SERVICES))
