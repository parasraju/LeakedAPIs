import time
import requests
from typing import Dict, List, Optional, Set

from .db import Database
from .patterns import PATTERNS, ALL_QUERIES, is_placeholder
from .validators import VALIDATORS


class Scanner:
    def __init__(self, tokens: List[str], db: Database,
                 services: Optional[List[str]] = None,
                 max_pages: int = 50, delay: float = 3.0):
        self.tokens = tokens
        self.token_idx = 0
        self.db = db
        self.services = services or list(PATTERNS.keys())
        self.max_pages = max_pages
        self.delay = delay
        self.per_page = 50

    @property
    def current_token(self) -> str:
        return self.tokens[self.token_idx % len(self.tokens)]

    def get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"token {self.current_token}"}

    def search_github(self, query: str, page: int = 1) -> Optional[Dict]:
        while True:
            url = "https://api.github.com/search/code"
            params = {"q": query, "page": page, "per_page": self.per_page}
            print(f"\n[Token {self.token_idx+1}/{len(self.tokens)}] "
                  f"Searching page {page}: {query}")

            try:
                r = requests.get(url, headers=self.get_headers(), params=params, timeout=15)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 403:
                    print("  Rate limit hit! Switching token...")
                    self.token_idx += 1
                    if self.token_idx >= len(self.tokens):
                        print("  All tokens exhausted. Sleeping 5 min...")
                        self.token_idx = 0
                        time.sleep(300)
                    continue
                else:
                    print(f"  GitHub API error: {r.status_code} {r.text[:200]}")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"  Network error: {e}")
                return None

    def get_file_content(self, item: Dict) -> str:
        repo = item["repository"]["full_name"]
        html_url = item.get("html_url", "")
        sha = ""
        if "/blob/" in html_url:
            sha = html_url.split("/blob/", 1)[1].split("/", 1)[0]
        path = item["path"]

        urls = []
        if sha:
            urls.append(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}")
        branch = item["repository"].get("default_branch", "main")
        urls.append(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")

        for url in urls:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    return r.text
            except Exception:
                continue
        return ""

    def validate_key(self, api_key: str, service: str) -> bool:
        validator = VALIDATORS.get(service)
        if validator:
            return validator(api_key)
        return True

    def scan_file(self, content: str) -> List[tuple]:
        found = []
        for name in self.services:
            pattern = PATTERNS.get(name)
            if not pattern:
                continue
            for key in pattern.findall(content):
                if is_placeholder(key):
                    continue
                found.append((name, key))
        return found

    def scan_results(self, results: Dict) -> int:
        keys_found = 0
        for item in results.get("items", []):
            file_url = item.get("html_url", "")
            repo = item.get("repository", {}).get("full_name", "")
            owner = item.get("repository", {}).get("owner", {}).get("login", "")
            repo_url = item.get("repository", {}).get("html_url", "")
            path = item.get("path", "")

            content = self.get_file_content(item)
            if not content:
                continue

            matches = self.scan_file(content)
            for service, key in matches:
                if self.db.key_exists(key):
                    continue

                print(f"\n  Found {service} key: {key[:12]}...{key[-6:]}")
                self.db.add_activity(f"Found {service} key in {repo}", "info")

                valid = self.validate_key(key, service)
                self.db.add_key(key, service, valid, file_url, repo,
                                owner, repo_url, path)

                if valid:
                    keys_found += 1
                    self.db.add_activity(f"VALID {service} key: {key[:12]}...{key[-6:]} in {repo}", "success")
                else:
                    self.db.add_activity(f"Invalid {service} key in {repo}", "warning")

        return keys_found

    def run(self):
        self.db.add_activity("Scanner started", "info")
        self.db.initialize()

        for query in ALL_QUERIES:
            for page in range(1, self.max_pages + 1):
                results = self.search_github(query, page)
                if not results or "items" not in results or len(results["items"]) == 0:
                    print(f"  No more results for: {query}")
                    self.db.log_scan(query, page, 0, 0)
                    break

                items_count = len(results["items"])
                keys_found = self.scan_results(results)
                self.db.log_scan(query, page, items_count, keys_found)
                print(f"  Page {page}: {items_count} items, {keys_found} new valid keys")

                time.sleep(self.delay)

        self.db.add_activity("Scanner finished", "info")
        print("\nAll queries complete.")
