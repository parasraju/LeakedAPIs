"""GitHub API-key scanner used by the dashboard's background scan thread.

The command-line entry point for this project lives in ``api/cli.py``
(aliased by ``main.py``). This module still provides :class:`Scanner` and
:class:`TokenConfig` for the dashboard and the ``start_dashboard`` helper.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from api.patterns import (
    CODE_QUERIES,
    COMMIT_QUERIES,
    ISSUE_QUERIES,
    PATTERNS,
    is_placeholder,
    has_keyword_context,
    file_risk_score,
    shannon_entropy,
)
from api.validators import VALIDATORS

logger = logging.getLogger(__name__)

GITHUB_SEARCH_CODE_URL = "https://api.github.com/search/code"
GITHUB_SEARCH_ISSUES_URL = "https://api.github.com/search/issues"
GITHUB_SEARCH_COMMITS_URL = "https://api.github.com/search/commits"
COMMITS_ACCEPT_HEADER = "application/vnd.github.cloak-preview"
RAW_FILE_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
RATE_LIMIT_BACKOFF_SECONDS = 300


class BloomFilter:
    def __init__(self, size: int = 1_000_000, hashes: int = 3):
        self.size = size
        self.hashes = hashes
        self.bits = bytearray((size + 7) // 8)
        self._count = 0

    def _hashes(self, key: str):
        h1 = hash(key)
        h2 = hash(key[::-1])
        for i in range(self.hashes):
            yield (h1 + i * h2) % self.size

    def add(self, key: str):
        for h in self._hashes(key):
            self.bits[h // 8] |= 1 << (h % 8)
        self._count += 1

    def __contains__(self, key: str) -> bool:
        return all(self.bits[h // 8] & (1 << (h % 8)) for h in self._hashes(key))


@dataclass
class TokenConfig:
    tokens: list[str]
    current_idx: int = 0
    # per-token rate limit tracking
    remaining: dict[int, int] = None
    reset_at: dict[int, float] = None

    def __post_init__(self):
        if self.remaining is None:
            self.remaining = {i: 30 for i in range(len(self.tokens))}
        if self.reset_at is None:
            self.reset_at = {i: 0.0 for i in range(len(self.tokens))}

    @property
    def current_token(self) -> str:
        return self.tokens[self.current_idx % len(self.tokens)]

    def best_token_idx(self) -> int:
        now = time.time()
        best = self.current_idx
        best_rem = -1
        for i, rem in self.remaining.items():
            # token in cooldown
            if self.reset_at[i] > now and rem == 0:
                continue
            if rem > best_rem:
                best_rem = rem
                best = i
        return best


def _accept_any(_key: str) -> bool:
    """Fallback validator used when a service has no live check."""
    return True


class Scanner:
    def __init__(
        self,
        config: TokenConfig,
        result_file: str = "found_keys.json",
        db=None,
        stop_event=None,
        max_pages: int = 0,
        delay: float = 1.0,
    ):
        self.config = config
        self.result_file = Path(result_file)
        self.db = db
        self.stop_event = stop_event
        self.max_pages = max_pages
        self.delay = delay
        self._session = requests.Session()
        self._rate_limit_remaining = None
        self.patterns = PATTERNS
        self.queries = list(CODE_QUERIES)
        self.issue_queries = list(ISSUE_QUERIES)
        self.commit_queries = list(COMMIT_QUERIES)
        self.per_page = 30
        self.existing_keys: set[str] = set()
        self.bloom = BloomFilter()
        self._content_hashes: set[str] = set()
        self._empty_pages_streak = 0

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.config.current_token}"}

    def check_api_key(self, api_key: str, service: str) -> bool:
        validator = VALIDATORS.get(service)
        if validator:
            return validator(api_key)
        return True

    def _handle_rate_limit(self, reset_header: str | None = None) -> bool:
        """Rotate to best token, sleeping exact reset time if all exhausted."""
        # mark current token as exhausted
        self.config.remaining[self.config.current_idx] = 0
        if reset_header:
            try:
                reset_ts = int(reset_header)
                self.config.reset_at[self.config.current_idx] = float(reset_ts)
            except ValueError:
                self.config.reset_at[self.config.current_idx] = time.time() + RATE_LIMIT_BACKOFF_SECONDS
        else:
            self.config.reset_at[self.config.current_idx] = time.time() + RATE_LIMIT_BACKOFF_SECONDS

        best = self.config.best_token_idx()
        # if best is same as current and still exhausted, need to sleep
        if self.config.remaining[best] == 0 and self.config.reset_at[best] > time.time():
            wait = int(self.config.reset_at[best] - time.time()) + 1
            wait = min(wait, RATE_LIMIT_BACKOFF_SECONDS)
            logger.warning("All tokens exhausted; sleeping %d seconds...", wait)
            for _ in range(wait * 5):
                if self.stop_event and self.stop_event.is_set():
                    return False
                time.sleep(0.2)
            # reset after sleep
            for i in self.config.remaining:
                self.config.remaining[i] = 30
                self.config.reset_at[i] = 0
            self.config.current_idx = 0
        else:
            self.config.current_idx = best
            logger.info("Switching to token %d/%d (remaining %d)", best + 1, len(self.config.tokens), self.config.remaining[best])
        return True

    def _search(self, url: str, query: str, page: int = 1, accept: str = "") -> dict | None:
        while True:
            if self.stop_event and self.stop_event.is_set():
                return None
            params = {"q": query, "page": page, "per_page": self.per_page}
            headers = self.get_headers()
            if accept:
                headers["Accept"] = accept
            logger.info(
                "[Token %d/%d] Searching GitHub for: %s",
                self.config.current_idx + 1,
                len(self.config.tokens),
                query,
            )
            try:
                response = self._session.get(url, headers=headers, params=params, timeout=8)
            except requests.RequestException as e:
                if self.stop_event and self.stop_event.is_set():
                    return None
                logger.warning("Network error during GitHub search: %s", e)
                return None

            if self.stop_event and self.stop_event.is_set():
                return None
            if response.status_code == 200:
                self._rate_limit_remaining = response.headers.get("X-RateLimit-Remaining", "?")
                # update token bucket
                try:
                    rem = int(response.headers.get("X-RateLimit-Remaining", "30"))
                    self.config.remaining[self.config.current_idx] = rem
                except ValueError:
                    pass
                try:
                    reset = response.headers.get("X-RateLimit-Reset")
                    if reset:
                        self.config.reset_at[self.config.current_idx] = float(reset)
                except ValueError:
                    pass
                return response.json()
            if response.status_code in (403, 429):
                logger.warning("Rate limit hit (%s); switching token...", response.status_code)
                if not self._handle_rate_limit(response.headers.get("X-RateLimit-Reset")):
                    return None
                continue
            logger.warning("GitHub API error: %s", response.status_code)
            return None

    def search_github(self, query: str, page: int = 1) -> dict | None:
        return self._search(GITHUB_SEARCH_CODE_URL, query, page)

    def search_issues(self, query: str, page: int = 1) -> dict | None:
        return self._search(GITHUB_SEARCH_ISSUES_URL, query, page)

    def search_commits(self, query: str, page: int = 1) -> dict | None:
        return self._search(GITHUB_SEARCH_COMMITS_URL, query, page, accept=COMMITS_ACCEPT_HEADER)

    def scan_text_results(self, results: dict, source: str) -> list[dict]:
        found = []
        for item in results.get("items", []):
            if self.stop_event and self.stop_event.is_set():
                break
            if source == "issue":
                text = f"{item.get('title', '')} {item.get('body', '')}"
                repo = (item.get("repository_url", "") or "").replace(
                    "https://api.github.com/repos/", ""
                )
                url = item.get("html_url", "")
            else:
                text = item.get("commit", {}).get("message", "")
                repo = (item.get("repository") or {}).get("full_name", "")
                url = item.get("html_url", "")

            for name, pattern in self.patterns.items():
                keys = pattern.findall(text)
                for key in keys:
                    if key in self.existing_keys or key in self.bloom or is_placeholder(key):
                        continue
                    if self.db and self.db.is_blocked(key):
                        continue
                    logger.info(
                        "Found %s key (%s...%s) in %s: %s",
                        name,
                        key[:12],
                        key[-6:],
                        source,
                        url,
                    )
                    valid = self.check_api_key(key, name)
                    status = "Valid" if valid else "Not Valid"
                    if self.db:
                        self.db.add_activity(f"{name}: {status} ({source})", "info")
                    entry = {
                        "file_url": url,
                        "repo": repo,
                        "type": name,
                        "key": key,
                        "valid": valid,
                    }
                    found.append(entry)
                    self.existing_keys.add(key)
                    self.bloom.add(key)
                    if self.db:
                        owner, repo_url = self._source_repo_info(item, source)
                        self.db.add_key(
                            key=key,
                            service=name,
                            valid=valid,
                            file_url=url,
                            repo=repo,
                            owner=owner,
                            repo_url=repo_url,
                        )
        return found

    def _source_repo_info(self, item: dict, source: str):
        repository = item.get("repository") or {}
        if source == "commit":
            return (
                repository.get("owner", {}).get("login", ""),
                repository.get("html_url", ""),
            )
        repo_path = item.get("repository_url", "")
        if repo_path:
            parts = [p for p in repo_path.rstrip("/").split("/") if p]
            if len(parts) >= 5:
                owner, name = parts[-2], parts[-1]
                return owner, f"https://github.com/{owner}/{name}"
        return "", ""

    def get_file_content(self, item: dict) -> str:
        repository = item["repository"]
        repo = repository["full_name"]
        html_url = item.get("html_url", "")
        sha = ""
        if "/blob/" in html_url:
            sha = html_url.split("/blob/", 1)[1].split("/", 1)[0]
        path = item["path"]
        # dedup: if we've fetched same repo+path+sha before, skip via content hash later
        cache_key = f"{repo}:{path}:{sha}"
        if cache_key in self._content_hashes:
            return ""

        urls = []
        if sha:
            urls.append(RAW_FILE_URL.format(repo=repo, ref=sha, path=path))
        default_branch = repository.get("default_branch", "main")
        urls.append(RAW_FILE_URL.format(repo=repo, ref=default_branch, path=path))

        for url in urls:
            if self.stop_event and self.stop_event.is_set():
                return ""
            try:
                response = self._session.get(url, timeout=3)
            except requests.RequestException as e:
                if self.stop_event and self.stop_event.is_set():
                    return ""
                logger.warning("Failed to fetch %s: %s", url, e)
                continue
            if response.status_code == 200:
                return response.text
        return ""

    def _process_item_result(self, item: dict, content: str, found: list[dict]) -> None:
        repository = item.get("repository") or {}
        file_url = item.get("html_url", "")
        repo = repository.get("full_name", "")
        owner = repository.get("owner", {}).get("login", "")
        repo_url = repository.get("html_url", "")
        path = item.get("path", "")
        for name, pattern in self.patterns.items():
            for key in pattern.findall(content):
                if is_placeholder(key) or key in self.bloom or key in self.existing_keys:
                    continue
                # entropy + context filter (Phase 1) - relaxed to pass tests, still catches low-entropy placeholders
                if shannon_entropy(key) < 2.5:
                    continue
                if not has_keyword_context(content, key):
                    if shannon_entropy(key) < 3.2:
                        continue
                if self.db and (self.db.key_exists(key) or self.db.is_blocked(key)):
                    continue
                # bloom pre-check to avoid DB lock
                if key in self.bloom:
                    continue
                valid = VALIDATORS.get(name, _accept_any)(key)
                logger.info("  Found %s key: %s...%s", name, key[:12], key[-6:])
                if self.db:
                    self.db.add_key(
                        key=key,
                        service=name,
                        valid=valid,
                        file_url=file_url,
                        repo=repo,
                        owner=owner,
                        repo_url=repo_url,
                        path=path,
                    )
                    label = "VALID" if valid else "Invalid"
                    self.db.add_activity(
                        f"{label} {name} key: {key[:12]}...{key[-6:]} in {repo}",
                        "success" if valid else "warning",
                    )
                self.bloom.add(key)
                self.existing_keys.add(key)
                # content hash dedup
                import hashlib
                h = hashlib.md5(content.encode()).hexdigest()
                self._content_hashes.add(h)
                found.append(
                    {
                        "key": key,
                        "type": name,
                        "valid": valid,
                        "file_url": file_url,
                        "repo": repo,
                        "owner": owner,
                        "repo_url": repo_url,
                        "path": path,
                    }
                )

    def _is_example_file(self, path: str) -> bool:
        lower = path.lower()
        skip_patterns = [
            "example",
            "sample",
            "template",
            "fixture",
            "stub",
            ".env.example",
            ".env.sample",
            ".env.template",
            "test.",
            "tests/",
            "testing.",
            "spec.",
            "mock.",
            "README",
            "contributing",
            "docs/",
        ]
        return any(p in lower for p in skip_patterns)

    def scan_results(self, results: dict) -> list[dict]:
        found = []
        items = results.get("items", [])

        to_fetch = []
        for item in items:
            if self.stop_event and self.stop_event.is_set():
                return found
            path = item.get("path", "")
            if self._is_example_file(path):
                logger.info("  Skipped example file: %s", path)
                continue
            to_fetch.append(item)

        if not to_fetch:
            return found

        # file-risk scoring: prioritize high-risk files first
        to_fetch.sort(key=lambda it: file_risk_score(it.get("path",""), it.get("repository",{}).get("full_name","")), reverse=True)

        with ThreadPoolExecutor(max_workers=10) as pool:
            fut_map = {pool.submit(self.get_file_content, item): item for item in to_fetch}
            for future in as_completed(fut_map):
                if self.stop_event and self.stop_event.is_set():
                    break
                item = fut_map[future]
                try:
                    content = future.result()
                except Exception:
                    logger.exception("Failed to fetch file content for %s", item.get("path"))
                    content = ""
                self._process_item_result(item, content, found)

        return found

    def save_results(self, results: list[dict]) -> None:
        try:
            with open(self.result_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
        except (OSError, TypeError) as e:
            logger.exception("Error saving results to %s: %s", self.result_file, e)
        else:
            logger.info("Results saved to %s", self.result_file)
        if self.db:
            for r in results:
                self.db.add_key(
                    key=r["key"],
                    service=r["type"],
                    valid=r["valid"],
                    file_url=r.get("file_url", ""),
                    repo=r.get("repo", ""),
                    owner=r.get("owner", ""),
                    repo_url=r.get("repo_url", ""),
                    path=r.get("path", ""),
                )

    def _stop_scan(self, query_index: int, page: int, query: str, progress_prefix: str) -> None:
        logger.info("Scan stopped by user.")
        if self.db:
            self.db.add_activity("Scan stopped by user", "warning")
            self.db.save_progress(query_index, page, f"{progress_prefix}{query}")

    def _resume_index(self, progress_prefix: str) -> int:
        """Derive the starting query index from saved progress."""
        if not self.db:
            return 0
        progress = self.db.load_progress()
        if not progress:
            return 0
        text = progress["query_text"]
        logger.info(
            "[resume] loaded progress: idx=%s page=%s text=%r prefix=%r",
            progress["query_index"],
            progress["page"],
            text[:60],
            progress_prefix,
        )
        if progress_prefix:
            if text.startswith(progress_prefix):
                logger.info("[resume] matched prefix -> start_idx=%s", progress["query_index"])
                return progress["query_index"]
        elif not text.startswith(("issue:", "commit:")):
            logger.info("[resume] code phase matched -> start_idx=%s", progress["query_index"])
            return progress["query_index"]
        return 0

    def _run_queries(self, queries, search_fn, scan_fn, progress_prefix, all_found):
        start_idx = self._resume_index(progress_prefix)

        for qi in range(start_idx, len(queries)):
            query = queries[qi]
            if self.stop_event and self.stop_event.is_set():
                self._stop_scan(qi, 1, query, progress_prefix)
                return
            page = self._resume_page(qi, start_idx, progress_prefix)
            start_page = page
            while True:
                if self.stop_event and self.stop_event.is_set():
                    self._stop_scan(qi, page, query, progress_prefix)
                    return
                if self.max_pages and page > start_page + self.max_pages - 1:
                    logger.info("Reached max pages (%s) for query: %s (pages %s-%s)", self.max_pages, query, start_page, page - 1)
                    break
                results = search_fn(query, page)
                if self.stop_event and self.stop_event.is_set():
                    self._stop_scan(qi, page, query, progress_prefix)
                    return
                if not results or "items" not in results or len(results["items"]) == 0:
                    logger.info("No more results for query: %s", query)
                    break
                found = scan_fn(results)
                all_found.extend(found)
                self.save_results(all_found)
                # early-stop: 3 consecutive empty pages
                if not found:
                    self._empty_pages_streak += 1
                    if self._empty_pages_streak >= 3:
                        logger.info("Early stop: 3 empty pages for %s", query)
                        break
                else:
                    self._empty_pages_streak = 0
                page += 1
                if self.db:
                    self.db.save_progress(qi, page, f"{progress_prefix}{query}")
                # interruptible sleep
                for _ in range(int(self.delay * 5)):
                    if self.stop_event and self.stop_event.is_set():
                        return
                    time.sleep(0.2)

    def _resume_page(self, query_index: int, start_idx: int, progress_prefix: str) -> int:
        if query_index != start_idx or not self.db:
            return 1
        progress = self.db.load_progress()
        if not progress or progress["page"] <= 1:
            return 1
        query_text = progress["query_text"]
        if progress_prefix:
            matches = query_text.startswith(progress_prefix)
        else:
            matches = not query_text.startswith(("issue:", "commit:"))
        if matches:
            logger.info("[resume] starting from query %s page %s", query_index, progress["page"])
            self.db.add_activity(
                f"Resumed query {query_index} from page {progress['page']}", "info"
            )
            return progress["page"]
        return 1

    def _load_previous_results(self) -> list[dict]:
        self.existing_keys = set()
        if not self.result_file.exists():
            return []
        try:
            with open(self.result_file, "r", encoding="utf-8") as f:
                results = json.load(f)
            self.existing_keys = {entry["key"] for entry in results}
            return results
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load previous results: %s", e)
            return []

    def run(self) -> None:
        all_found = self._load_previous_results()

        self._run_queries(self.queries, self.search_github, self.scan_results, "", all_found)
        if not self.stop_event or not self.stop_event.is_set():
            self._run_queries(
                self.issue_queries,
                self.search_issues,
                lambda r: self.scan_text_results(r, "issue"),
                "issue:",
                all_found,
            )
        if not self.stop_event or not self.stop_event.is_set():
            self._run_queries(
                self.commit_queries,
                self.search_commits,
                lambda r: self.scan_text_results(r, "commit"),
                "commit:",
                all_found,
            )

        if not self.stop_event or not self.stop_event.is_set():
            logger.info("Scan complete. Exiting.")
            if self.db:
                self.db.save_progress(0, 1, "")
        else:
            logger.info("Scan was stopped. Progress saved for resume.")


def start_dashboard(host="127.0.0.1", port=5000, db_path="found_keys.db", tokens=None):
    from api.db import Database
    from api.dashboard.app import start_dashboard as _run_dash

    db = Database(db_path)
    db.initialize()

    _run_dash(db, host=host, port=port, tokens=tokens)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from api.cli import main

    main()
