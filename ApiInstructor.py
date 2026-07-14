import requests
import re
import json
import time
import os
import sys
from typing import List, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from api.patterns import is_placeholder
from api.validators import VALIDATORS

@dataclass
class TokenConfig:
    tokens: List[str]
    current_idx: int = 0
    
    @property
    def current_token(self) -> str:
        return self.tokens[self.current_idx % len(self.tokens)]

class Scanner:
    def __init__(self, config: TokenConfig, result_file: str = "found_keys.json", db=None, stop_event=None):
        self.config = config
        self.result_file = Path(result_file)
        self.db = db
        self.stop_event = stop_event
        self._session = requests.Session()
        self._rate_limit_remaining = None
        self.patterns = {
            "OpenAI": re.compile(r"sk-(?:proj-[A-Za-z0-9]{20,}|[A-Za-z0-9]{20,})"),
            "HuggingFace": re.compile(r"hf_[A-Za-z0-9]{36,64}"),
            "Anthropic": re.compile(r"sk-ant-[A-Za-z0-9]{32,96}"),
            "Stripe": re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{24,}"),
            "GitHub": re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"),
            "GoogleGemini": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            "TelegramBot": re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35,45}"),
            "DiscordBot": re.compile(r"[MN][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}"),
            "SendGrid": re.compile(r"SG\.[A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{43,}"),
            "GitLab": re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
            "Notion": re.compile(r"secret_[A-Za-z0-9]{43,48}"),
            "Linear": re.compile(r"lin_api_[A-Za-z0-9]{40,}"),
            "Mailgun": re.compile(r"key-[A-Za-z0-9]{32,}"),
            "Mapbox": re.compile(r"(?:pk|sk)\.[A-Za-z0-9]{60,}\.[A-Za-z0-9]{1,}"),
            "SlackBot": re.compile(r"xox[baprs]-[A-Za-z0-9]{10,}-[A-Za-z0-9]{10,}-[A-Za-z0-9]{24,}"),
            "AWSKey": re.compile(r"AKIA[0-9A-Z]{16}"),
        }
        self.queries = [
            # ---- CODE SEARCH ----
            "sk- AND \"sk-\" extension:env",
            "sk- AND \"sk-\" extension:json",
            "sk- AND \"sk-\" extension:yaml",
            "sk- AND \"sk-\" extension:py",
            "sk- AND \"sk-\" extension:js",
            "hf_ AND \"hf_\" extension:env",
            "hf_ AND \"hf_\" extension:json",
            "hf_ AND \"hf_\" extension:yaml",
            "sk-ant- AND \"sk-ant-\" extension:env",
            "sk-ant- AND \"sk-ant-\" extension:json",
            "sk-ant- AND \"sk-ant-\" extension:yaml",
            "sk_live_ extension:env",
            "sk_live_ extension:json",
            "sk_live_ extension:yaml",
            "rk_live_ extension:env",
            "\"ghp_\" AND ghp_ extension:env",
            "\"ghp_\" AND ghp_ extension:json",
            "ghp_ extension:txt",
            "gho_ extension:env",
            "ghs_ extension:env",
            "AIza extension:env",
            "AIza extension:json",
            "AIza extension:js",
            "\"SG.\" AND SG. extension:env",
            "\"SG.\" AND SG. extension:json",
            "\"key-\" AND api_key extension:env",
            "\"key-\" AND api_key extension:json",
            "glpat- extension:env",
            "glpat- extension:json",
            "secret_ AND notion extension:env",
            "secret_ AND notion extension:json",
            "lin_api_ extension:env",
            "lin_api_ extension:json",
            "xoxb- AND \"xoxb-\" extension:env",
            "xoxb- AND \"xoxb-\" extension:json",
            "\"AKIA\" AND secret extension:env",
            "\"AKIA\" AND secret extension:json",
            "sk- in:filename .env",
            "sk- in:filename .env.local",
            "sk- in:filename .env.production",
            "sk- in:filename .env.development",
            "sk- in:filename .env.staging",
            "hf_ in:filename .env",
            "hf_ in:filename .env.local",
            "ghp_ in:filename .env",
            "ghp_ in:filename .txt",
            "AIza in:filename .env",
            "api_key in:filename .env",
            "api_key in:filename .env.local",
            "secret in:filename .env",
            "secret in:filename .env.local",
            "token in:filename .env",
            "token in:filename .env.local",
            # .yml mirrors of .yaml queries
            "sk- AND \"sk-\" extension:yml",
            "hf_ AND \"hf_\" extension:yml",
            "sk-ant- AND \"sk-ant-\" extension:yml",
            "sk_live_ extension:yml",
            "rk_live_ extension:yml",
            "ghp_ extension:yml",
            "gho_ extension:yml",
            "ghs_ extension:yml",
            "AIza extension:yml",
            "\"SG.\" AND SG. extension:yml",
            "\"key-\" AND api_key extension:yml",
            "glpat- extension:yml",
            "secret_ AND notion extension:yml",
            "lin_api_ extension:yml",
            "xoxb- AND \"xoxb-\" extension:yml",
            "\"AKIA\" AND secret extension:yml",
            # Shell scripts
            "sk- AND \"sk-\" extension:sh",
            "ghp_ extension:sh",
            "AIza extension:sh",
            "\"AKIA\" AND secret extension:sh",
            # TOML, Terraform, PHP, Ruby, TypeScript, Go
            "sk- AND \"sk-\" extension:toml",
            "ghp_ extension:toml",
            "\"AKIA\" AND secret extension:tf",
            "sk- AND \"sk-\" extension:php",
            "AIza extension:php",
            "sk- AND \"sk-\" extension:rb",
            "sk- AND \"sk-\" extension:ts",
            "ghp_ extension:ts",
            "sk- AND \"sk-\" extension:go",
            # Additional filename searches
            "secret in:filename credentials",
            "secret in:filename .env.staging",
            "secret in:filename .env.prod",
            "api_key in:filename .py",
            "api_key in:filename .rb",
            "password in:filename .env",
            "token in:filename .yml",
            "secret in:filename .yml",
            "api_key in:filename .yml",
        ]
        self.issue_queries = [
            # ---- ISSUE SEARCH ----
            "sk- in:body",
            "ghp_ in:body",
            "gho_ in:body",
            "ghs_ in:body",
            "AIza in:body",
            "\"AKIA\" in:body",
            "sk_live_ in:body",
            "rk_live_ in:body",
            "sk-ant- in:body",
            "hf_ in:body",
            "\"SG.\" in:body",
            "glpat- in:body",
            "xoxb- in:body",
        ]
        self.commit_queries = [
            # ---- COMMIT SEARCH ----
            "sk- in:commit",
            "ghp_ in:commit",
            "gho_ in:commit",
            "AIza in:commit",
            "\"AKIA\" in:commit",
            "sk_live_ in:commit",
            "sk-ant- in:commit",
        ]
        self.per_page = 30
        self.existing_keys: Set[str] = set()

    def get_headers(self) -> Dict[str, str]:
        """Generate request headers with current token"""
        return {"Authorization": f"token {self.config.current_token}"}

    def check_api_key(self, api_key: str, service: str) -> bool:
        from api.validators import VALIDATORS
        validator = VALIDATORS.get(service)
        if validator:
            return validator(api_key)
        return True

    def search_github(self, query: str, page: int = 1) -> Optional[Dict]:
        """Search GitHub API for keys"""
        while True:
            if self.stop_event and self.stop_event.is_set():
                return None

            url = "https://api.github.com/search/code"
            params = {"q": query, "page": page, "per_page": self.per_page}
            print(f"[Token {self.config.current_idx+1}/{len(self.config.tokens)}] "
                  f"Searching GitHub for: {query}")
                   
            try:
                response = self._session.get(
                    url, 
                    headers=self.get_headers(),
                    params=params,
                    timeout=15
                )

                if self.stop_event and self.stop_event.is_set():
                    return None

                if response.status_code == 200:
                    self._rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '?')
                    return response.json()
                elif response.status_code == 403:
                    print("Rate limit hit! Switching GitHub token...")
                    self.config.current_idx += 1
                    if self.config.current_idx >= len(self.config.tokens):
                        print("All tokens exhausted. Sleeping for 5 minutes...")
                        self.config.current_idx = 0
                        for _ in range(300):
                            if self.stop_event and self.stop_event.is_set():
                                return None
                            time.sleep(1)
                    continue
                else:
                    print(f"GitHub API error: {response.status_code}")
                    return None
            except Exception as e:
                print(f"Network error: {e}")
                return None

    def _search_api(self, url: str, query: str, page: int = 1, accept: str = "") -> Optional[Dict]:
        while True:
            if self.stop_event and self.stop_event.is_set():
                return None
            params = {"q": query, "page": page, "per_page": self.per_page}
            headers = self.get_headers()
            if accept:
                headers["Accept"] = accept
            try:
                response = self._session.get(url, headers=headers, params=params, timeout=15)
                if self.stop_event and self.stop_event.is_set():
                    return None
                if response.status_code == 200:
                    self._rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '?')
                    return response.json()
                elif response.status_code == 403:
                    print("Rate limit hit! Switching GitHub token...")
                    self.config.current_idx += 1
                    if self.config.current_idx >= len(self.config.tokens):
                        print("All tokens exhausted. Sleeping for 5 minutes...")
                        self.config.current_idx = 0
                        for _ in range(300):
                            if self.stop_event and self.stop_event.is_set():
                                return None
                            time.sleep(1)
                    continue
                else:
                    print(f"GitHub API error: {response.status_code}")
                    return None
            except Exception as e:
                print(f"Network error: {e}")
                return None

    def search_issues(self, query: str, page: int = 1) -> Optional[Dict]:
        return self._search_api("https://api.github.com/search/issues", query, page)

    def search_commits(self, query: str, page: int = 1) -> Optional[Dict]:
        return self._search_api(
            "https://api.github.com/search/commits", query, page,
            accept="application/vnd.github.cloak-preview"
        )

    def scan_text_results(self, results: Dict, source: str) -> List[Dict]:
        found = []
        for item in results.get("items", []):
            if self.stop_event and self.stop_event.is_set():
                break
            if source == "issue":
                text = f"{item.get('title', '')} {item.get('body', '')}"
                repo = item.get("repository_url", "").replace("https://api.github.com/repos/", "")
                url = item.get("html_url", "")
            else:
                text = item.get("commit", {}).get("message", "")
                repo = item.get("repository", {}).get("full_name", "")
                url = item.get("html_url", "")

            for name, pattern in self.patterns.items():
                keys = pattern.findall(text)
                for key in keys:
                    if key in self.existing_keys:
                        continue
                    if self.is_placeholder(key):
                        continue
                    try:
                        print(f"\nFound {name} key ({key[:12]}...{key[-6:]}) in {source}: {url}")
                    except UnicodeEncodeError:
                        print(f"\nFound {name} key in {source}: {url}")
                    valid = self.check_api_key(key, name)
                    status = "Valid" if valid else "Not Valid"
                    if self.db:
                        self.db.add_activity(f"{name}: {status} ({source})", "info")
                    entry = {
                        "file_url": url, "repo": repo,
                        "type": name, "key": key, "valid": valid
                    }
                    found.append(entry)
                    self.existing_keys.add(key)
                    if self.db:
                        owner = item.get("repository", {}).get("owner", {}).get("login", "") if source == "commit" else ""
                        repo_url = item.get("repository", {}).get("html_url", "") if source == "commit" else ""
                        self.db.add_key(key=key, service=name, valid=valid, file_url=url, repo=repo, owner=owner, repo_url=repo_url)
        return found

    def is_placeholder(self, key: str) -> bool:
        placeholders = [
            "1234567", "xxxxx", "changeme", "placeholder",
            "your-api", "your_key", "YOUR_", "your-",
            "example", "test_key", "dummy", "sample",
        ]
        lower = key.lower()
        for p in placeholders:
            if p in lower:
                return True
        if len(set(key[-12:])) <= 3:
            return True
        if key.count("x") + key.count("X") > len(key) * 0.25:
            return True
        return False

    def get_file_content(self, item: Dict) -> str:
        repo = item['repository']['full_name']
        html_url = item.get('html_url', '')
        sha = ""
        if '/blob/' in html_url:
            sha = html_url.split('/blob/', 1)[1].split('/', 1)[0]
        path = item['path']

        urls = []
        if sha:
            urls.append(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}")
        branch = item['repository'].get('default_branch', 'main')
        urls.append(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")

        for url in urls:
            if self.stop_event and self.stop_event.is_set():
                return ''
            try:
                response = self._session.get(url, timeout=5)
                if response.status_code == 200:
                    return response.text
            except Exception:
                continue
        return ''

    def _process_item_result(self, item: Dict, content: str, found: List[Dict]) -> None:
        file_url = item.get("html_url", "")
        repo = item.get("repository", {}).get("full_name", "")
        owner = item.get("repository", {}).get("owner", {}).get("login", "")
        repo_url = item.get("repository", {}).get("html_url", "")
        path = item.get("path", "")
        for name, pattern in self.patterns.items():
            for key in pattern.findall(content):
                if is_placeholder(key):
                    continue
                if self.db and self.db.key_exists(key):
                    continue
                valid = VALIDATORS.get(name, lambda k: True)(key)
                try:
                    print(f"  Found {name} key: {key[:12]}...{key[-6:]}")
                except UnicodeEncodeError:
                    print(f"  Found {name} key: [masked]")
                if self.db:
                    self.db.add_key(
                        key=key, service=name, valid=valid,
                        file_url=file_url, repo=repo,
                        owner=owner, repo_url=repo_url, path=path,
                    )
                    label = "VALID" if valid else "Invalid"
                    self.db.add_activity(
                        f"{label} {name} key: {key[:12]}...{key[-6:]} in {repo}",
                        "success" if valid else "warning"
                    )
                found.append({
                    "key": key, "type": name, "valid": valid,
                    "file_url": file_url, "repo": repo,
                    "owner": owner, "repo_url": repo_url, "path": path,
                })

    def _is_example_file(self, path: str) -> bool:
        lower = path.lower()
        skip_patterns = [
            "example", "sample", "template", "fixture", "stub",
            ".env.example", ".env.sample", ".env.template",
            "test.", "tests/", "testing.", "spec.", "mock.",
            "README", "contributing", "docs/",
        ]
        for p in skip_patterns:
            if p in lower:
                return True
        return False

    def scan_results(self, results: Dict) -> List[Dict]:
        found = []
        items = results.get("items", [])

        to_fetch = []
        for item in items:
            if self.stop_event and self.stop_event.is_set():
                return found
            path = item.get("path", "")
            if self._is_example_file(path):
                try:
                    print(f"  Skipped example file: {path}")
                except UnicodeEncodeError:
                    print(f"  Skipped example file: [non-ASCII path]")
                continue
            to_fetch.append(item)

        if not to_fetch:
            return found

        with ThreadPoolExecutor(max_workers=10) as pool:
            fut_map = {pool.submit(self.get_file_content, item): item for item in to_fetch}
            for future in as_completed(fut_map):
                if self.stop_event and self.stop_event.is_set():
                    break
                item = fut_map[future]
                try:
                    content = future.result()
                except Exception:
                    content = ''
                self._process_item_result(item, content, found)

        return found

    def save_results(self, results: List[Dict]) -> None:
        try:
            with open(self.result_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to {self.result_file}")
        except Exception as e:
            print(f"Error saving JSON: {e}")
        if self.db:
            for r in results:
                self.db.add_key(
                    key=r["key"], service=r["type"], valid=r["valid"],
                    file_url=r.get("file_url", ""), repo=r.get("repo", ""),
                    owner=r.get("owner", ""), repo_url=r.get("repo_url", ""),
                    path=r.get("path", ""),
                )

    def _run_queries(self, queries: List[str], search_fn, scan_fn,
                      progress_prefix: str, all_found: List[Dict]):
        start_idx = 0
        if self.db:
            progress = self.db.load_progress()
            if progress:
                text = progress["query_text"]
                print(f"[resume] loaded progress: idx={progress['query_index']} page={progress['page']} text='{text[:60]}' prefix='{progress_prefix}'")
                if progress_prefix:
                    if text.startswith(progress_prefix):
                        start_idx = progress["query_index"]
                        print(f"[resume] matched prefix -> start_idx={start_idx}")
                else:
                    if not text.startswith("issue:") and not text.startswith("commit:"):
                        start_idx = progress["query_index"]
                        print(f"[resume] code phase matched -> start_idx={start_idx}")

        for qi in range(start_idx, len(queries)):
            query = queries[qi]
            if self.stop_event and self.stop_event.is_set():
                print("Scan stopped by user.")
                if self.db:
                    self.db.add_activity("Scan stopped by user", "warning")
                    self.db.save_progress(qi, 1, f"{progress_prefix}{query}")
                return
            page = 1
            if qi == start_idx and self.db:
                p = self.db.load_progress()
                if p and p["page"] > 1:
                    pt = p["query_text"]
                    if progress_prefix:
                        matches = pt.startswith(progress_prefix)
                    else:
                        matches = not pt.startswith("issue:") and not pt.startswith("commit:")
                    if matches:
                        page = p["page"]
                        print(f"[resume] starting from query {qi} page {page}")
                        if self.db:
                            self.db.add_activity(f"Resumed query {qi} from page {page}", "info")
            while True:
                if self.stop_event and self.stop_event.is_set():
                    print("Scan stopped by user.")
                    if self.db:
                        self.db.add_activity("Scan stopped by user", "warning")
                        self.db.save_progress(qi, page, f"{progress_prefix}{query}")
                    return
                results = search_fn(query, page)
                if self.stop_event and self.stop_event.is_set():
                    print("Scan stopped by user.")
                    if self.db:
                        self.db.add_activity("Scan stopped by user", "warning")
                        self.db.save_progress(qi, page, f"{progress_prefix}{query}")
                    return
                if not results or 'items' not in results or len(results['items']) == 0:
                    print(f"No more results for query: {query}")
                    break
                found = scan_fn(results)
                all_found.extend(found)
                self.save_results(all_found)
                page += 1
                if self.db:
                    self.db.save_progress(qi, page, f"{progress_prefix}{query}")
                time.sleep(1)

    def run(self) -> None:
        all_found = []
        self.existing_keys = set()
        try:
            if self.result_file.exists():
                with open(self.result_file, "r", encoding="utf-8") as f:
                    all_found = json.load(f)
                    self.existing_keys = {entry["key"] for entry in all_found}
        except Exception as e:
            print(f"Warning: could not load previous results: {e}")

        self._run_queries(self.queries, self.search_github, self.scan_results, "", all_found)
        if not self.stop_event or not self.stop_event.is_set():
            self._run_queries(self.issue_queries, self.search_issues,
                              lambda r: self.scan_text_results(r, "issue"), "issue:", all_found)
        if not self.stop_event or not self.stop_event.is_set():
            self._run_queries(self.commit_queries, self.search_commits,
                              lambda r: self.scan_text_results(r, "commit"), "commit:", all_found)

        if not self.stop_event or not self.stop_event.is_set():
            print("Scan complete. Exiting.")
            if self.db:
                self.db.save_progress(0, 1, "")
        else:
            print("Scan was stopped. Progress saved for resume.")


def start_dashboard(host="127.0.0.1", port=5000, db_path="found_keys.db", tokens=None):
    from api.db import Database
    from dashboard.app import app, start_dashboard as _run_dash
    db = Database(db_path)
    db.initialize()

    _run_dash(db, host=host, port=port, tokens=tokens)


if __name__ == "__main__":
    # Auto-clean: kill previous server on port 5000, clear caches
    import subprocess, shutil
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"],
            capture_output=True, text=True, timeout=5
        )
        pid = r.stdout.strip()
        if pid:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            print(f"Killed previous process (PID {pid})")
    except Exception:
        pass
    for d in [Path("__pycache__"), Path("api/__pycache__"), Path("dashboard/__pycache__")]:
        shutil.rmtree(d, ignore_errors=True)
    print("Cache cleared")

    import argparse
    parser = argparse.ArgumentParser(description="API Instructor - scan GitHub for exposed API keys")
    parser.add_argument("--scan", action="store_true", help="Run scan in CLI mode (default: start dashboard)")
    parser.add_argument("-t", "--tokens", help="GitHub token(s), comma-separated")
    parser.add_argument("--port", type=int, default=5000, help="Dashboard port (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard host (default: 127.0.0.1)")
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages per query")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between requests")
    parser.add_argument("-o", "--output", default="found_keys.db", help="Database path")
    args = parser.parse_args()

    if args.scan:
        if not args.tokens:
            print("Error: --tokens required for scan mode")
            sys.exit(1)
        from api.db import Database
        db = Database(args.output)
        db.initialize()
        config = TokenConfig(tokens=[t.strip() for t in args.tokens.split(",") if t.strip()])
        scanner = Scanner(config, result_file="found_keys.json", db=db)
        try:
            scanner.run()
        except KeyboardInterrupt:
            print("\nStopped by user.")
    else:
        token_list = [t.strip() for t in args.tokens.split(",") if t.strip()] if args.tokens else None
        start_dashboard(host=args.host, port=args.port, db_path=args.output, tokens=token_list)