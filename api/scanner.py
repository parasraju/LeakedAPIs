"""GitHub code-scanning implementation used by the ``api-instructor scan`` CLI."""

import logging
import time

import requests

from .db import Database
from .patterns import ALL_QUERIES, PATTERNS, is_placeholder
from .validators import VALIDATORS

logger = logging.getLogger(__name__)

GITHUB_SEARCH_CODE_URL = "https://api.github.com/search/code"
RATE_LIMIT_BACKOFF_SECONDS = 300


class Scanner:
    def __init__(
        self,
        tokens: list[str],
        db: Database,
        services: list[str] | None = None,
        max_pages: int = 50,
        delay: float = 3.0,
        stop_event=None,
    ):
        self.tokens = tokens
        self.token_idx = 0
        self.db = db
        self.services = services or list(PATTERNS.keys())
        self.max_pages = max_pages
        self.delay = delay
        self.per_page = 50
        self.stop_event = stop_event

    @property
    def current_token(self) -> str:
        return self.tokens[self.token_idx % len(self.tokens)]

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.current_token}"}

    def _handle_rate_limit(self) -> bool:
        """Rotate to the next token, backing off when all are exhausted.

        Returns True when the caller should retry the request and False when
        the scan should stop.
        """
        self.token_idx += 1
        if self.token_idx >= len(self.tokens):
            logger.warning(
                "All tokens exhausted; sleeping %d seconds...", RATE_LIMIT_BACKOFF_SECONDS
            )
            self.token_idx = 0
            for _ in range(RATE_LIMIT_BACKOFF_SECONDS):
                if self.stop_event and self.stop_event.is_set():
                    return False
                time.sleep(1)
        return True

    def search_github(self, query: str, page: int = 1) -> dict | None:
        while True:
            if self.stop_event and self.stop_event.is_set():
                return None
            logger.info(
                "[Token %d/%d] Searching page %d: %s",
                self.token_idx + 1,
                len(self.tokens),
                page,
                query,
            )
            try:
                r = requests.get(
                    GITHUB_SEARCH_CODE_URL,
                    headers=self.get_headers(),
                    params={"q": query, "page": page, "per_page": self.per_page},
                    timeout=15,
                )
            except requests.RequestException as e:
                logger.warning("Network error during GitHub search: %s", e)
                return None

            if r.status_code == 200:
                return r.json()
            if r.status_code == 403:
                logger.warning("Rate limit hit; switching token...")
                if not self._handle_rate_limit():
                    return None
                continue
            logger.warning("GitHub API error: %s %s", r.status_code, r.text[:200])
            return None

    def get_file_content(self, item: dict) -> str:
        repo = item["repository"]["full_name"]
        html_url = item.get("html_url", "")
        sha = ""
        if "/blob/" in html_url:
            sha = html_url.split("/blob/", 1)[1].split("/", 1)[0]
        path = item["path"]

        repository = item["repository"]
        urls = []
        if sha:
            urls.append(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}")
        default_branch = repository.get("default_branch", "main")
        urls.append(f"https://raw.githubusercontent.com/{repo}/{default_branch}/{path}")

        for url in urls:
            if self.stop_event and self.stop_event.is_set():
                return ""
            try:
                r = requests.get(url, timeout=10)
            except requests.RequestException as e:
                logger.warning("Failed to fetch %s: %s", url, e)
                continue
            if r.status_code == 200:
                return r.text
        return ""

    def validate_key(self, api_key: str, service: str) -> bool:
        validator = VALIDATORS.get(service)
        if validator:
            return validator(api_key)
        return True

    def scan_file(self, content: str) -> list[tuple]:
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

    def scan_results(self, results: dict) -> int:
        keys_found = 0
        for item in results.get("items", []):
            repository = item.get("repository") or {}
            file_url = item.get("html_url", "")
            repo = repository.get("full_name", "")
            owner = repository.get("owner", {}).get("login", "")
            repo_url = repository.get("html_url", "")
            path = item.get("path", "")

            content = self.get_file_content(item)
            if not content:
                continue

            matches = self.scan_file(content)
            for service, key in matches:
                if self.db.key_exists(key):
                    continue

                logger.info("Found %s key: %s...%s", service, key[:12], key[-6:])
                self.db.add_activity(f"Found {service} key in {repo}", "info")

                valid = self.validate_key(key, service)
                self.db.add_key(key, service, valid, file_url, repo, owner, repo_url, path)

                if valid:
                    keys_found += 1
                    self.db.add_activity(
                        f"VALID {service} key: {key[:12]}...{key[-6:]} in {repo}",
                        "success",
                    )
                else:
                    self.db.add_activity(f"Invalid {service} key in {repo}", "warning")

        return keys_found

    def run(self):
        self.db.add_activity("Scanner started", "info")
        self.db.initialize()

        for query in ALL_QUERIES:
            if self.stop_event and self.stop_event.is_set():
                logger.info("Scan stopped by user.")
                return
            self._scan_query(query)

        self.db.add_activity("Scanner finished", "info")
        logger.info("All queries complete.")

    def _scan_query(self, query: str) -> None:
        for page in range(1, self.max_pages + 1):
            if self.stop_event and self.stop_event.is_set():
                logger.info("Scan stopped by user.")
                return
            results = self.search_github(query, page)
            if not results or "items" not in results or len(results["items"]) == 0:
                logger.info("No more results for: %s", query)
                self.db.log_scan(query, page, 0, 0)
                return

            items_count = len(results["items"])
            keys_found = self.scan_results(results)
            self.db.log_scan(query, page, items_count, keys_found)
            logger.info("Page %d: %d items, %d new valid keys", page, items_count, keys_found)

            time.sleep(self.delay)
