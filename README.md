# API Instructor

Scans GitHub for exposed API keys and displays results in a live dashboard.

<div align="center">

  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
  [![Flask](https://img.shields.io/badge/Powered%20by-Flask-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
  [![GitHub](https://img.shields.io/badge/GitHub%20API-181717?logo=github&logoColor=white)](https://github.com)
  [![License](https://img.shields.io/badge/License-MIT-green.svg)]()
  [![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

  <a href="#setup"><img src="https://img.shields.io/badge/%E2%9A%A1-Setup-7c3aed?style=for-the-badge"></a>
  <a href="#commands"><img src="https://img.shields.io/badge/%F0%9F%93%9A-Commands-2563eb?style=for-the-badge"></a>
  <a href="#services-scanned"><img src="https://img.shields.io/badge/%F0%9F%94%8D-Services%20Scanned-0d9488?style=for-the-badge"></a>
  <a href="#project-structure"><img src="https://img.shields.io/badge/%F0%9F%8F%97-Project%20Structure-475569?style=for-the-badge"></a>

</div>

---

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
