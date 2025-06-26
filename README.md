GitHub Public Secret Key Scanner
GitHub Public Secret Key Scanner is a Python tool for security researchers and developers to detect and validate exposed API keys (such as OpenAI and HuggingFace) in public GitHub repositories.


Sample output: Finds exposed keys, checks their validity, and skips already-seen results.

Features
🔍 Scans public GitHub code for API key patterns using advanced partitioned queries.

🔒 Validates keys by making API requests to check if they are live/usable.

🔁 Supports multiple GitHub API tokens for extended, uninterrupted scanning.

⚡ Deduplicates findings: skips checking and saving keys that were found before.

📂 Saves only valid, unique keys to a results file (found_keys2.json).

Requirements
Python 3.7+

requests library (pip install requests)

One or more GitHub personal access tokens (PATs)
(scopes: public_repo are enough for public search)

Usage
Clone this repo and place the script in a directory.

Add your GitHub API tokens to the GITHUB_TOKENS list in the script:

python
Copy
Edit
GITHUB_TOKENS = [
    'ghp_xxx...',
    'ghp_yyy...',
    # etc.
]
(Optional) Adjust file types/languages in the QUERIES list to target more or fewer file types.

Run the script:

bash
Copy
Edit
python github_key_scanner.py
Review your results in found_keys2.json.

Example Output
This script prints every key it finds and checks. Only truly valid keys are saved.

❌ OpenAI Key is invalid or expired. (sk-f605U31...fAjsPR)

Found OpenAI key in https://github.com/SomeUser/SomeRepo/blob/abcdef/file.py (SomeRepo)
❌ OpenAI Key is invalid or expired. (sk-Xh1XwUQ...FsEWzt)

How It Works
Searches public GitHub repositories for API keys in many common code/data file types.

Checks the validity of each found key using its real API.

Deduplicates keys against previous runs for maximum efficiency.

Automatically rotates tokens to avoid GitHub API rate limits.

Handles 404s, errors, and duplicate files gracefully.

Configuration
GITHUB_TOKENS: Add as many tokens as you have for longer scans.

QUERIES: Add/remove file extensions or languages as needed for coverage.

RESULT_FILE: Change output filename if desired.

Patterns: Add more key regexes in the PATTERNS dict to support more APIs.

Disclaimer
This tool is provided for authorized security research, education, and personal code auditing only.
Do not use it for malicious purposes or to scan code you do not have permission to analyze.
Violating GitHub's terms of service or any laws is strictly prohibited.

License
MIT

Happy (ethical) hunting!
Feel free to open an issue or PR to add more patterns or improvements.
