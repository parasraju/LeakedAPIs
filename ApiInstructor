import requests
import re
import json
import time
import os

# ===========================
# CONFIGURATION
# ===========================
GITHUB_TOKENS = [
    'Api1',
    'Api2',
    'Api3',
    'Etc'
]

CURRENT_TOKEN_IDX = 0

def get_headers():
    return {'Authorization': f'token {GITHUB_TOKENS[CURRENT_TOKEN_IDX]}'}

PATTERNS = {
    "OpenAI": re.compile(r"sk-[A-Za-z0-9]{48}"),
    "HuggingFace": re.compile(r"hf_[A-Za-z0-9]{32,64}")
}

QUERIES = [
    # Python, JS, and common data files
    "sk- in:file extension:py",
    "sk- in:file extension:js",
    "sk- in:file extension:json",
    "hf_ in:file extension:py",
    "hf_ in:file extension:js",
    "hf_ in:file extension:env",
    "hf_ in:file extension:json",
]
PER_PAGE = 50
RESULT_FILE = "found_keys2.json"

# ===========================
# LOAD EXISTING KEYS
def load_existing_keys():
    existing_keys = set()
    if os.path.isfile(RESULT_FILE):
        try:
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
                for entry in results:
                    existing_keys.add(entry["key"])
            print(f"Loaded {len(existing_keys)} existing keys from {RESULT_FILE}")
        except Exception as e:
            print(f"Could not load {RESULT_FILE}: {e}")
    return existing_keys

# ===========================
# CHECKERS
def check_openai_key(api_key):
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"✅ OpenAI Key is valid! ({api_key[:10]}...{api_key[-6:]})")
            return True
        elif response.status_code == 401:
            print(f"❌ OpenAI Key is invalid or expired. ({api_key[:10]}...{api_key[-6:]})")
            return False
        else:
            print(f"❓ Unknown error (OpenAI). Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error checking OpenAI key: {e}")
        return False

def check_huggingface_key(api_key):
    url = "https://huggingface.co/api/whoami-v2"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"✅ HuggingFace Key is valid! ({api_key[:10]}...{api_key[-6:]})")
            return True
        elif response.status_code == 401:
            print(f"❌ HuggingFace Key is invalid or expired. ({api_key[:10]}...{api_key[-6:]})")
            return False
        else:
            print(f"❓ Unknown error (HuggingFace). Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error checking HuggingFace key: {e}")
        return False

# ===========================
# GITHUB SEARCH FUNCTIONS
def search_github_for_keys(query, page=1):
    global CURRENT_TOKEN_IDX
    while True:
        url = "https://api.github.com/search/code"
        params = {"q": query, "page": page, "per_page": PER_PAGE}
        print(f"\n[Token {CURRENT_TOKEN_IDX+1}/{len(GITHUB_TOKENS)}] Searching GitHub (page {page}) for query: {query}")
        r = requests.get(url, headers=get_headers(), params=params)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 403:
            print("⚠️  Rate limit hit! Switching GitHub token...")
            CURRENT_TOKEN_IDX += 1
            if CURRENT_TOKEN_IDX >= len(GITHUB_TOKENS):
                print("🔄 All tokens exhausted. Sleeping for 5 minutes before retrying...")
                CURRENT_TOKEN_IDX = 0
                time.sleep(300)  # Wait for rate limit reset
            else:
                print(f"➡️  Switched to token #{CURRENT_TOKEN_IDX + 1}")
            continue
        else:
            print("GitHub API error:", r.status_code, r.text)
            return None

def get_file_content(item):
    repo = item['repository']['full_name']
    path = item['path']
    branch = item['repository'].get('default_branch', 'main')
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.text
        else:
            print(f"Could not fetch {url}")
            return ''
    except Exception as e:
        print(f"Error fetching file content: {e}")
        return ''

# ===========================
# SCAN AND COLLECT METADATA
def scan_for_keys_in_results(results, existing_keys):
    found = []
    for item in results.get("items", []):
        file_url = item.get("html_url")
        repo = item.get("repository", {}).get("full_name")
        owner = item.get("repository", {}).get("owner", {}).get("login")
        repo_url = item.get("repository", {}).get("html_url")
        default_branch = item.get("repository", {}).get("default_branch")
        path = item.get("path")
        content = get_file_content(item)
        for name, pattern in PATTERNS.items():
            keys = pattern.findall(content)
            for key in keys:
                if key in existing_keys:
                    print(f"Skipped duplicate {name} key ({key[:10]}...{key[-6:]})")
                    continue  # Skip already-saved key
                print(f"\nFound {name} key in {file_url} ({repo})")
                valid = None
                if name == "OpenAI":
                    valid = check_openai_key(key)
                elif name == "HuggingFace":
                    valid = check_huggingface_key(key)
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
                    existing_keys.add(key)
                time.sleep(1)
    return found

def save_results_to_json(results, filename=RESULT_FILE):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {filename}")
    except Exception as e:
        print("Error saving JSON:", e)

# ===========================
# MAIN SCANNER LOOP


def main():
    existing_keys = load_existing_keys()
    all_found = []
    if existing_keys:
        try:
            with open(RESULT_FILE, "r", encoding="utf-8") as f:
                all_found = json.load(f)
        except Exception as e:
            print(f"Warning: could not load full previous results: {e}")

    for query in QUERIES:
        page = 1
        while True:
            results = search_github_for_keys(query, page)
            if not results or 'items' not in results or len(results['items']) == 0:
                print(f"No more results for query: {query}.")
                break
            found = scan_for_keys_in_results(results, existing_keys)
            all_found.extend(found)
            save_results_to_json(all_found)
            page += 1
            time.sleep(3)
    print("All queries complete. Exiting.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
