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


def test_scan_file_checks_every_service(tmp_path):
    db, scanner = make_scanner(tmp_path, ["token-a"])
    stripe_key = "sk" + "_live_" + "0aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV1w"
    content = "\n".join(
        [
            "OPENAI_API_KEY=sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
            "HUGGINGFACE_TOKEN=hf_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefgh",
            "ANTHROPIC_API_KEY=sk-ant-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefgh",
            f"STRIPE_SECRET_KEY={stripe_key}",
            "GITHUB_TOKEN=ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGh",
            "GOOGLE_API_KEY=AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345678",
            "TELEGRAM_BOT_TOKEN=1234567890:AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
            "DISCORD_BOT_TOKEN=M0AbCdEfGhIjKlMnOpQrStUvWx.123456.abcdefghijklmnopqrstuvwxyz0123456",
            "SENDGRID_API_KEY=SG.ABcDeFgHiJkLmNoPqRsTuVwXyZ01233.ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrst",
            "GITLAB_TOKEN=glpat-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
            "NOTION_TOKEN=secret_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefghij",
            "LINEAR_API_KEY=lin_api_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcde",
            "MAILGUN_API_KEY=key-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdef",
            "MAPBOX_TOKEN=pk.Abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz123.1",
            "SLACK_BOT_TOKEN=xoxb-1234567890-AbCdEfGhIj-1234AbCdEfGhIjKlMnOpQrStUv08",
            "AWS_ACCESS_KEY_ID=AKIA0B11CD22EF33GH44",
            "PINECONE_API_KEY=pcsk_0B11CD22EF33GH44IJ55KL66MN77OP88QQ99",
            "SUPABASE_SERVICE_ROLE=sbp_0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u",
            "FIREBASE_API_KEY=AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz012345678",
            "CLOUDFLARE_API_TOKEN=a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
            "SENTRY_DSN=sntrys_0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u",
            "TWILIO_AUTH_TOKEN=SK0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6",
            "OPENROUTER_API_KEY=sk-or-v1-0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0uV1w2XY3z4",
            "XAI_API_KEY=xai-0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
            "DEEPSEEK_API_KEY=sk-0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u",
            "GROQ_API_KEY=gsk_0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
            "TOGETHER_API_KEY=tgp_v1_0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1v2w3x4y5Z6",
            "CEREBRAS_API_KEY=csk-0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
            "REPLICATE_API_TOKEN=r8_0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u",
            "PERPLEXITY_API_KEY=pplx-0a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u",
        ]
    )
    services = {s for s, _ in scanner.scan_file(content)}
    expected = {
        "OpenAI", "HuggingFace", "Anthropic", "Stripe", "GitHub", "GoogleGemini",
        "TelegramBot", "DiscordBot", "SendGrid", "GitLab", "Notion", "Linear",
        "Mailgun", "Mapbox", "SlackBot", "AWSKey", "Pinecone", "Supabase",
        "Firebase", "Cloudflare", "Sentry", "Twilio", "OpenRouter", "xAI",
        "DeepSeek", "Groq", "TogetherAI", "Cerebras", "Replicate", "Perplexity",
    }
    assert expected <= services, sorted(expected - services)
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
