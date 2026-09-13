"""Command-line entry point for the API Instructor scanner and dashboard."""

import argparse
import json
import logging
import sys

from .db import Database
from .patterns import SERVICES

logger = logging.getLogger(__name__)


def _out(*parts) -> None:
    """CLI output (print is intentional for a command-line tool)."""
    print(*parts)  # noqa: T201


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="api-instructor",
        description="Scan GitHub for exposed API keys with a live dashboard",
    )

    sub = parser.add_subparsers(dest="mode", help="Mode: scan or dashboard")

    scan = sub.add_parser("scan", help="Run scanner (CLI mode)")
    scan.add_argument(
        "-t", "--tokens", nargs="+", required=True, help="GitHub personal access tokens"
    )
    scan.add_argument(
        "-o",
        "--output",
        default="found_keys.db",
        help="SQLite database path (default: found_keys.db)",
    )
    scan.add_argument(
        "-s",
        "--services",
        nargs="+",
        default=SERVICES,
        help="Services to scan for (default: all)",
    )
    scan.add_argument("--max-pages", type=int, default=50, help="Max pages per query (default: 50)")
    scan.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay between requests in seconds (default: 3.0)",
    )

    dash = sub.add_parser("dashboard", help="Start the web dashboard")
    dash.add_argument(
        "-o",
        "--output",
        default="found_keys.db",
        help="SQLite database path (default: found_keys.db)",
    )
    dash.add_argument("--port", type=int, default=5000, help="Dashboard port (default: 5000)")
    dash.add_argument("--host", default="127.0.0.1", help="Dashboard host (default: 127.0.0.1)")
    dash.add_argument(
        "-t",
        "--tokens",
        nargs="+",
        help="GitHub tokens to run scanner alongside dashboard",
    )
    dash.add_argument("-s", "--services", nargs="+", default=SERVICES, help="Services to scan for")
    dash.add_argument("--max-pages", type=int, default=20, help="Max pages per query (default: 20)")
    dash.add_argument(
        "--delay", type=float, default=5.0, help="Delay between requests (default: 5.0)"
    )

    providers = sub.add_parser("providers", help="List all configured providers")
    providers.add_argument("--json", action="store_true", help="Output as JSON")

    services = sub.add_parser("services", help="List services scanned by the GitHub scanner")
    services.add_argument("--json", action="store_true", help="Output as JSON")

    models = sub.add_parser("models", help="List supported models")
    models.add_argument("--provider", default=None, help="Filter by provider (e.g. openai)")
    models.add_argument("--alias", default=None, help="Resolve `provider:alias` to a model")
    models.add_argument(
        "--discover",
        default=None,
        help="Fetch live models from provider (requires its API key in env)",
    )
    models.add_argument("--json", action="store_true", help="Output as JSON")

    keys = sub.add_parser("keys", help="Show configured API keys (masked)")
    keys.add_argument("--json", action="store_true", help="Output as JSON")

    validate = sub.add_parser("validate", help="Validate a provider's API key")
    validate.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="Provider id (e.g. openai). Omit to validate all configured providers.",
    )
    validate.add_argument(
        "--key", default=None, help="API key to validate (falls back to env var)"
    )
    validate.add_argument("--json", action="store_true", help="Output as JSON")

    return parser.parse_args(argv)


def run_scanner(args, db):
    from .scanner import Scanner

    services = args.services if args.services and args.services != SERVICES else None
    scanner = Scanner(
        tokens=args.tokens,
        db=db,
        services=services,
        max_pages=args.max_pages,
        delay=args.delay,
    )
    try:
        scanner.run()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        db.add_activity("Scanner stopped by user", "warning")


def _emit(data, as_json: bool):
    if as_json:
        _out(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    _out("  ".join(f"{k}={v}" for k, v in item.items()))
                else:
                    _out(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                _out(f"{k}: {v}")
        else:
            _out(data)


def run_providers(as_json: bool):
    from .providers import list_providers

    provs = list_providers()
    if as_json:
        _emit(
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
                }
                for p in provs
            ],
            as_json,
        )
    else:
        for p in provs:
            _out(f"{p.id:<14} {p.name:<24} {p.base_url}")


def run_services(as_json: bool):
    _emit([{"service": s} for s in SERVICES], as_json)


def run_models(args):
    from .providers.models import get_model_registry, resolve_model

    if args.alias:
        m = resolve_model(args.alias)
        if not m:
            sys.exit(f"Unknown alias: {args.alias}")
        _emit(m, args.json)
        return
    if args.discover:
        from .providers.keys import get_api_key

        key = get_api_key(args.discover)
        if not key:
            sys.exit(f"No API key configured for provider '{args.discover}' (set its env var)")
        count, err = get_model_registry().discover(args.discover, key)
        if err:
            sys.exit(f"Discovery failed: {err.get('message', err.get('error_type', 'unknown'))}")
        _out(f"Discovered {count} live models for {args.discover}")
        # fall through to showing merged list
    models = get_model_registry().to_dict(args.provider)
    if args.json:
        _emit(models, True)
    else:
        for m in models:
            _out(f"{m['provider']:<12} {m['id']:<48} {m['type']:<10} {m['status']}")


def run_keys(as_json: bool):
    from .providers.keys import all_credentials

    creds = [v for v in all_credentials().values()]
    if as_json:
        _emit(creds, True)
    else:
        for c in creds:
            _out(f"{c['provider']:<14} {c['status']:<20} {c['masked']}  ({c['env_var']})")


def run_validate(args):
    from .providers.validation import health_of, validate

    if args.provider:
        if args.key:
            result = validate(args.provider, args.key)
        else:
            result = validate(args.provider)
        _emit(result, args.json)
        if not args.json:
            status = "valid" if result.get("valid") else "invalid"
            _out(f"\nProvider {args.provider}: {status}")
        return

    # no provider -> show health of all
    from .providers.registry import list_providers

    ids = [p.id for p in list_providers()]
    results = {pid: health_of(pid) for pid in ids}
    if args.json:
        _emit(results, True)
    else:
        for pid, h in results.items():
            _out(f"{pid:<14} {h['status']:<22} {h.get('message', '')}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()

    if args.mode == "scan":
        db = Database(args.output)
        db.initialize()
        run_scanner(args, db)

    elif args.mode == "dashboard":
        db = Database(args.output)
        db.initialize()

        if args.tokens:
            import threading

            scan_args = args
            t = threading.Thread(target=run_scanner, args=(scan_args, db), daemon=True)
            t.start()

        from api.dashboard.app import start_dashboard

        start_dashboard(db, host=args.host, port=args.port)

    elif args.mode == "providers":
        run_providers(args.json)

    elif args.mode == "services":
        run_services(args.json)

    elif args.mode == "models":
        run_models(args)

    elif args.mode == "keys":
        run_keys(args.json)

    elif args.mode == "validate":
        run_validate(args)

    else:
        logger.error(
            "Use: api-instructor scan ...  |  dashboard ...  |  providers  |  models  |  keys  |  validate <provider>"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
