import threading
import sys
from pathlib import Path
import requests
from flask import Flask, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__, template_folder=Path(__file__).parent / "templates",
            static_folder=Path(__file__).parent / "static")
_db = None
_scanner_thread = None
_scanner_status = {"running": False, "progress": "", "query": "", "page": 0, "tokens_remaining": ""}
_stop_event = None


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
    keys = _db.get_keys(limit=5000)
    count = 0
    for k in keys:
        from ApiInstructor import Scanner
        from api.validators import VALIDATORS
        validator = VALIDATORS.get(k["service"])
        if validator:
            valid = validator(k["key"])
            _db.add_key(key=k["key"], service=k["service"], valid=valid,
                        file_url=k.get("file_url", ""), repo=k.get("repo", ""),
                        owner=k.get("owner", ""), repo_url=k.get("repo_url", ""),
                        path=k.get("path", ""))
            status = "Valid" if valid else "Not Valid"
            _db.add_activity(f"{k['service']}: {status} (re-check)", "info")
            count += 1
    _db.add_activity(f"Re-checked {count} keys", "info")
    return jsonify({"rechecked": count})


@app.route("/api/activity")
def activity():
    return jsonify(_db.get_activity(limit=200))


@app.route("/api/scan/status")
def scan_status():
    return jsonify(_scanner_status)


@app.route("/api/scan/start", methods=["POST"])
def scan_start():
    global _scanner_thread, _scanner_status, _stop_event

    if _scanner_status["running"]:
        return jsonify({"error": "Scan already running"}), 409

    data = request.get_json(silent=True) or {}
    tokens = data.get("tokens", [])
    if not tokens:
        return jsonify({"error": "At least one GitHub token required"}), 400

    _stop_event = threading.Event()
    _scanner_status = {"running": True, "progress": "Starting...",
                       "query": "", "page": 0, "tokens_remaining": ""}

    def run_scan():
        global _scanner_status
        try:
            from ApiInstructor import Scanner, TokenConfig
            config = TokenConfig(tokens=tokens)
            scanner = Scanner(config=config, result_file="found_keys.json",
                              db=_db, stop_event=_stop_event)
            original_search = scanner.search_github

            def search_with_status(query, page):
                _scanner_status["query"] = query
                _scanner_status["page"] = page
                _scanner_status["progress"] = f"Query: {query[:60]}"
                result = original_search(query, page)
                remaining = getattr(scanner, '_rate_limit_remaining', None)
                if remaining is not None:
                    _scanner_status["tokens_remaining"] = str(remaining)
                return result

            scanner.search_github = search_with_status
            scanner.run()
        except Exception as e:
            _db.add_activity(f"Scan error: {e}", "error")
        finally:
            _scanner_status["running"] = False
            _scanner_status["progress"] = "Idle"

    _scanner_thread = threading.Thread(target=run_scan, daemon=True)
    _scanner_thread.start()
    _db.add_activity("Scan started", "info")
    return jsonify({"status": "started"})


@app.route("/api/scan/stop", methods=["POST"])
def scan_stop():
    global _stop_event, _scanner_status
    if _stop_event and _scanner_status["running"]:
        _stop_event.set()
        _db.add_activity("Stopping scan...", "warning")
        return jsonify({"status": "stopping"})
    return jsonify({"error": "No scan running"}), 400


@app.route("/api/keys/report", methods=["POST"])
def report_key():
    data = request.get_json(silent=True) or {}
    owner = data.get("owner", "")
    repo = data.get("repo", "")
    key = data.get("key", "")
    service = data.get("service", "")
    file_url = data.get("file_url", "")
    path = data.get("path", "")
    token = data.get("token", "")

    if not all([owner, repo, key, token]):
        return jsonify({"error": "Missing required fields (owner, repo, key, token)"}), 400

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
                "Accept": "application/vnd.github+json"
            },
            json={"title": title, "body": body},
            timeout=15
        )
        if r.status_code in (200, 201):
            issue_url = r.json().get("html_url", "")
            _db.add_activity(f"Reported {service} key in {repo_full}: {issue_url}", "warning")
            return jsonify({"status": "created", "url": issue_url})
        else:
            return jsonify({"error": f"GitHub API error: {r.status_code} {r.text[:200]}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": "Internal server error: " + str(e)}), 500


@app.errorhandler(Exception)
def handle_uncaught(e):
    return jsonify({"error": "Unhandled exception: " + str(e)}), 500


def start_dashboard(db, host="127.0.0.1", port=5000):
    global _db
    _db = db
    _scanner_status["progress"] = "Idle"
    print(f"\nDashboard: http://{host}:{port}")
    print("Press Ctrl+C to stop.\n")
    app.run(host=host, port=port, debug=False, use_reloader=False)
