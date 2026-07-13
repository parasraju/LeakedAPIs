# API Instructor

Scans GitHub for exposed API keys and displays results in a live dashboard.

## Setup

```powershell
cd D:\p\apiInstructor
pip install -r requirements.txt
```

## Commands

### Scan (CLI mode)

```powershell
python main.py scan -t "github_pat_xxxx" "github_pat_yyyy"
```

| Flag | Description |
|---|---|
| `-t` | GitHub personal access token(s) |
| `-o` | Output database file (default: found_keys.db) |
| `-s` | Services to scan for (default: all) |
| `--max-pages` | Max pages per query (default: 50) |
| `--delay` | Delay between requests in seconds (default: 3.0) |

### Dashboard only

```powershell
python main.py dashboard --port 5000
```

### Dashboard + background scan

```powershell
python main.py dashboard -t "github_pat_xxxx" --port 5000
```

| Flag | Description |
|---|---|
| `--port` | Dashboard port (default: 5000) |
| `--host` | Dashboard host (default: 127.0.0.1) |
| `-t` | GitHub tokens to scan in background |
| `--max-pages` | Max pages per query (default: 20) |
| `--delay` | Delay between requests (default: 5.0) |

Open **http://127.0.0.1:5000** in your browser.

### Migrate old JSON data

```powershell
python migrate.py
```

## Services scanned

OpenAI, HuggingFace, Anthropic, Stripe, GitHub, Google Gemini, Telegram Bot, Discord Bot, SendGrid, GitLab, Notion, Linear, Mailgun, Mapbox, Slack, AWS.

## Project structure

```
apiInstructor/
├── main.py                  Entry point
├── requirements.txt
├── migrate.py               Migrate old found_keys.json to SQLite
├── api/
│   ├── cli.py               Argument parsing
│   ├── db.py                SQLite database
│   ├── patterns.py          Regex patterns + search queries
│   ├── scanner.py           GitHub scanner
│   └── validators.py        API key validators
└── dashboard/
    ├── app.py               Flask web app
    ├── templates/            HTML templates
    └── static/               CSS
```
