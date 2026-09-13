import logging
import sys
import threading
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(
    __name__,
    template_folder=Path(__file__).parent / "templates",
    static_folder=Path(__file__).parent / "static",
)
_db = None
_scanner_thread = None
_scanner_status = {
    "running": False,
    "progress": "",
    "query": "",
    "page": 0,
    "tokens_remaining": "",
}
_stop_event = None
_scan_tokens = None
_rate_cache = {"core": {}, "search": {}, "updated": 0}


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/stats")
def stats():
    return jsonify(_db.get_stats())


@app.route("/api/keys")
def keys():
    return jsonify(_db.get_keys(limit=500))


@app.route("/api/keys/revalidate", methods=["POST"])
def revalidate():
    if _scanner_status.get("running"):
        return jsonify({"error": "Scan is running — stop scan first, then re-check"}), 409
    from api.validators import VALIDATORS

    # fetch all keys (covers both valid and invalid, all services)
    keys = _db.get_keys(limit=10000)
    count = 0
    for k in keys:
        validator = VALIDATORS.get(k["service"])
        if not validator:
            logger.warning("No validator for service %s, skipping %s", k["service"], k["key"][:12])
            continue
        try:
            valid = validator(k["key"])
        except Exception as e:
            logger.exception("Validator crashed for %s: %s", k["service"], e)
            valid = False
        # always update DB so invalid -> valid and valid -> invalid both persist
        _db.add_key(
            key=k["key"],
            service=k["service"],
            valid=valid,
            file_url=k.get("file_url", ""),
            repo=k.get("repo", ""),
            owner=k.get("owner", ""),
            repo_url=k.get("repo_url", ""),
            path=k.get("path", ""),
        )
        status = "Valid" if valid else "Invalid"
        _db.add_activity(f"{k['service']}: {status} (re-check) {k['key'][:12]}...", "info" if valid else "warning")
        count += 1
    _db.add_activity(f"Re-checked {count} keys", "info")
    return jsonify({"rechecked": count})


@app.route("/api/keys/clear-invalid", methods=["POST"])
def clear_invalid():
    try:
        count = _db.clear_invalid_keys()
        _db.add_activity(f"Cleared {count} invalid keys", "warning")
        return jsonify({"cleared": count})
    except Exception as e:
        logger.exception("clear_invalid failed: %s", e)
        return jsonify({"error": f"Clear failed: {e}"}), 500


@app.route("/api/activity")
def activity():
    return jsonify(_db.get_activity(limit=200))


@app.route("/api/providers")
def providers():
    from api.providers import list_providers
    from api.providers.keys import all_credentials

    creds = all_credentials()
    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "env_var": p.env_var,
                "base_url": p.base_url,
                "auth_method": p.auth_method,
                "openai_compatible": p.openai_compatible,
                "supports_streaming": p.supports_streaming,
                "supports_model_discovery": p.supports_model_discovery,
                "status": p.status,
                "doc_url": p.doc_url,
                # masked key config (never the raw key)
                "key_status": creds.get(p.id, {}).get("status", "not_configured"),
                "key_masked": creds.get(p.id, {}).get("masked", "not configured"),
            }
            for p in list_providers()
        ]
    )


@app.route("/api/services")
def services():
    from api.patterns import SERVICES

    return jsonify([{"service": s} for s in SERVICES])


@app.route("/api/models")
def models():
    from api.providers.models import get_model_registry

    provider = request.args.get("provider")
    return jsonify(get_model_registry().to_dict(provider))


@app.route("/api/keys/status")
def keys_status():
    from api.providers.keys import all_credentials

    return jsonify(all_credentials())


@app.route("/api/health")
def health():
    from api.providers.validation import health_all

    return jsonify(health_all())


@app.route("/api/validate/<provider>", methods=["POST"])
def validate_provider(provider):
    from api.providers.validation import validate

    data = request.get_json(silent=True) or {}
    key = data.get("key")
    result = validate(provider, key or None)
    return jsonify(result)


@app.route("/api/models/discover", methods=["POST"])
def models_discover():
    from api.providers.keys import get_api_key
    from api.providers.models import get_model_registry

    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "").strip()
    if not provider:
        return jsonify({"error": "provider required"}), 400
    key = data.get("key") or get_api_key(provider)
    if not key:
        return jsonify({"error": f"No API key for '{provider}' (set env var or pass key)"}), 400
    count, err = get_model_registry().discover(provider, key)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"provider": provider, "discovered": count})


@app.route("/api/scan/status")
def scan_status():
    return jsonify(_scanner_status)


@app.route("/api/github/rate_limit")
def rate_limit():
    now = time.time()

    if now - _rate_cache["updated"] < 60 and _rate_cache.get("core"):
        return jsonify(_rate_cache)

    token = _scan_tokens[0] if _scan_tokens else None

    if not token:
        return jsonify({"core": {}, "search": {}})

    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={"Authorization": f"token {token}"},
            timeout=5,
        )

        if r.status_code == 200:
            resources = r.json().get("resources") or {}
            c, s = resources.get("core") or {}, resources.get("search") or {}

            _rate_cache.update(
                core={
                    "remaining": c.get("remaining"),
                    "limit": c.get("limit"),
                },
                search={
                    "remaining": s.get("remaining"),
                    "limit": s.get("limit"),
                },
                updated=now,
            )

    except requests.RequestException:
        logger.exception("Failed to fetch GitHub rate limit")

    return jsonify(_rate_cache)


def _start_scan(tokens, max_pages=0):
    global _scanner_thread, _scanner_status, _stop_event, _scan_tokens

    progress = _db.load_progress()
    if progress:
        _db.add_activity(
            f"Loaded saved progress: query_idx={progress['query_index']} page={progress['page']} text='{progress['query_text'][:60]}'",
            "info",
        )

    _scan_tokens = tokens
    _stop_event = threading.Event()
    _scanner_status = {
        "running": True,
        "progress": "Starting...",
        "query": "",
        "page": 0,
        "tokens_remaining": "",
    }

    def run_scan():
        try:
            from ApiInstructor import Scanner, TokenConfig

            config = TokenConfig(tokens=tokens)
            scanner = Scanner(
                config=config,
                result_file="found_keys.json",
                db=_db,
                stop_event=_stop_event,
                max_pages=max_pages,
            )
            original_search = scanner.search_github

            def search_with_status(query, page):
                _scanner_status["query"] = query
                _scanner_status["page"] = page
                _scanner_status["progress"] = f"Query: {query[:60]}"
                result = original_search(query, page)
                remaining = getattr(scanner, "_rate_limit_remaining", None)
                if remaining is not None:
                    _scanner_status["tokens_remaining"] = f"Search: {remaining}"
                return result

            def fetch_rate_limit():
                while not (_stop_event and _stop_event.is_set()):
                    try:
                        r = requests.get(
                            "https://api.github.com/rate_limit",
                            headers={"Authorization": f"token {tokens[0]}"},
                            timeout=5,
                        )

                        if r.status_code == 200:
                            resources = r.json().get("resources") or {}
                            c = resources.get("core") or {}
                            s = resources.get("search") or {}

                            _scanner_status["tokens_remaining"] = (
                                f"Core: {c.get('remaining', '?')}/{c.get('limit', '?')}  "
                                f"Search: {s.get('remaining', '?')}/{s.get('limit', '?')}"
                            )

                    except requests.RequestException:
                        logger.exception("Failed to fetch GitHub rate limit")

                    for _ in range(60):
                        if _stop_event and _stop_event.is_set():
                            return
                        time.sleep(1)

            t = threading.Thread(target=fetch_rate_limit, daemon=True)
            t.start()
            try:
                scanner.search_github = search_with_status
                scanner.run()
            except (requests.RequestException, OSError) as e:
                _db.add_activity(f"Scan error: {e}", "error")
                _scanner_status["running"] = False
                _scanner_status["progress"] = "Error"
            else:
                _scanner_status["running"] = False
                _scanner_status["progress"] = "Idle"
        except Exception:
            logger.exception("Scan thread crashed")
            _db.add_activity("Scan thread crashed", "error")
            _scanner_status["running"] = False
            _scanner_status["progress"] = "Error"

    _scanner_thread = threading.Thread(target=run_scan, daemon=True)
    _scanner_thread.start()
    _db.add_activity("Scan started", "info")


@app.route("/api/scan/start", methods=["POST"])
def scan_start():
    if _scanner_status["running"]:
        return jsonify({"error": "Scan already running"}), 409

    data = request.get_json(silent=True) or {}
    tokens = [t.strip() for t in data.get("tokens", []) if t and t.strip()]
    if not tokens:
        return jsonify({"error": "At least one GitHub token required"}), 400
    for t in tokens:
        if len(t) < 10:
            return jsonify({"error": "Invalid token format"}), 400

    start_page = data.get("start_page", 1)
    if not isinstance(start_page, int) or start_page < 1:
        start_page = 1
    if start_page > 1:
        _db.save_progress(0, start_page, "")

    pages = data.get("pages", 0)
    if not isinstance(pages, int) or pages < 1:
        pages = 0

    _start_scan(tokens, max_pages=pages)
    return jsonify({"status": "started"})


@app.route("/api/scan/stop", methods=["POST"])
def scan_stop():
    if _stop_event and _scanner_status["running"]:
        _stop_event.set()
        # immediate UI feedback — don't wait for thread to notice
        _scanner_status["running"] = False
        _scanner_status["progress"] = "Idle"
        _scanner_status["query"] = ""
        _db.add_activity("Scan stopped by user", "warning")
        _db.add_activity("Stopping scan...", "warning")
        return jsonify({"status": "stopped"})
    return jsonify({"error": "No scan running"}), 400


@app.route("/api/keys/report", methods=["POST"])
def report_key():
    data = request.get_json(silent=True) or {}
    owner = (data.get("owner", "") or "").strip()
    repo = (data.get("repo", "") or "").strip()
    key = (data.get("key", "") or "").strip()
    service = (data.get("service", "") or "").strip()
    file_url = (data.get("file_url", "") or "").strip()
    path = (data.get("path", "") or "").strip()
    token = (data.get("token", "") or "").strip()

    if not all([owner, repo, key, token]):
        return jsonify({"error": "Missing required fields (owner, repo, key, token)"}), 400

    if "/" in owner or ".." in owner or "/" in repo or ".." in repo:
        return jsonify({"error": "Invalid owner or repo"}), 400

    repo_full = f"{owner}/{repo}"
    title = f"Exposed {service} API key found in repository"
    body = (
        f"A **{service}** API key was found exposed in this repository.\n\n"
        f"- **File:** `{path or 'unknown'}`\n"
        f"- **File URL:** {file_url or 'N/A'}\n"
        f"- **Key (masked):** `{key[:12]}...{key[-6:]}`\n"
        f"\n---\n*This issue was automatically created by API Instructor scanner.*\n"
        f"*Please rotate/revoke the exposed key immediately.*"
    )

    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo_full}/issues",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "body": body},
            timeout=15,
        )
        if r.status_code in (200, 201):
            issue_url = r.json().get("html_url", "")
            _db.add_activity(f"Reported {service} key in {repo_full}: {issue_url}", "warning")
            return jsonify({"status": "created", "url": issue_url})
        else:
            return jsonify({"error": f"GitHub API error: {r.status_code} {r.text[:200]}"}), 500
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


@app.errorhandler(500)
def handle_internal_error(e):
    return jsonify({"error": "Internal server error: " + str(e)}), 500


@app.errorhandler(Exception)
def handle_uncaught(e):
    if isinstance(e, HTTPException):
        return e
    return jsonify({"error": "Unhandled exception: " + str(e)}), 500


def start_dashboard(db, host="127.0.0.1", port=5000, tokens=None):
    global _db
    _db = db
    _scanner_status["progress"] = "Idle"
    logger.info("Dashboard: http://%s:%s", host, port)
    if tokens:
        _start_scan(tokens)
        logger.info("Auto-starting scan from last saved position...")
    logger.info("Press Ctrl+C to stop.")
    app.run(host=host, port=port, debug=False, use_reloader=False)
