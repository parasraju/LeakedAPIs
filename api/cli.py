import argparse
import sys
from .db import Database
from .patterns import SERVICES


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="api-instructor",
        description="Scan GitHub for exposed API keys with a live dashboard",
    )

    sub = parser.add_subparsers(dest="mode", help="Mode: scan or dashboard")

    # --- scan ---
    scan = sub.add_parser("scan", help="Run scanner (CLI mode)")
    scan.add_argument("-t", "--tokens", nargs="+", required=True,
                      help="GitHub personal access tokens")
    scan.add_argument("-o", "--output", default="found_keys.db",
                      help="SQLite database path (default: found_keys.db)")
    scan.add_argument("-s", "--services", nargs="+",
                      default=SERVICES,
                      help=f"Services to scan for (default: all)")
    scan.add_argument("--max-pages", type=int, default=50,
                      help="Max pages per query (default: 50)")
    scan.add_argument("--delay", type=float, default=3.0,
                      help="Delay between requests in seconds (default: 3.0)")

    # --- dashboard ---
    dash = sub.add_parser("dashboard", help="Start the web dashboard")
    dash.add_argument("-o", "--output", default="found_keys.db",
                      help="SQLite database path (default: found_keys.db)")
    dash.add_argument("--port", type=int, default=5000,
                      help="Dashboard port (default: 5000)")
    dash.add_argument("--host", default="127.0.0.1",
                      help="Dashboard host (default: 127.0.0.1)")
    dash.add_argument("-t", "--tokens", nargs="+",
                      help="GitHub tokens to run scanner alongside dashboard")
    dash.add_argument("-s", "--services", nargs="+",
                      default=SERVICES,
                      help=f"Services to scan for")
    dash.add_argument("--max-pages", type=int, default=20,
                      help="Max pages per query (default: 20)")
    dash.add_argument("--delay", type=float, default=5.0,
                      help="Delay between requests (default: 5.0)")

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
        print("\nStopped by user.")
        db.add_activity("Scanner stopped by user", "warning")


def main():
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

        from dashboard.app import start_dashboard
        start_dashboard(db, host=args.host, port=args.port)

    else:
        print("Use: api-instructor scan ...  or  api-instructor dashboard ...")
        sys.exit(1)


if __name__ == "__main__":
    main()
