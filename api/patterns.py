import re


SERVICES = [
    "OpenAI", "HuggingFace", "Anthropic", "Stripe", "GitHub",
    "GoogleGemini", "TelegramBot", "DiscordBot", "SendGrid",
    "GitLab", "Notion", "Linear", "Mailgun", "Mapbox", "SlackBot", "AWSKey",
]

PATTERNS = {
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

ENV_VAR_QUERIES = [
    '"OPENAI_API_KEY" extension:env',
    '"OPENAI_API_KEY" extension:json',
    '"OPENAI_API_KEY" extension:yaml',
    '"ANTHROPIC_API_KEY" extension:env',
    '"ANTHROPIC_API_KEY" extension:json',
    '"HUGGINGFACE_TOKEN" extension:env',
    '"HF_TOKEN" extension:env',
    '"STRIPE_SECRET_KEY" extension:env',
    '"STRIPE_API_KEY" extension:env',
    '"GITHUB_TOKEN" extension:env',
    '"GITHUB_TOKEN" extension:json',
    '"GITLAB_TOKEN" extension:env',
    '"GITLAB_API_TOKEN" extension:env',
    '"NOTION_TOKEN" extension:env',
    '"NOTION_API_KEY" extension:env',
    '"LINEAR_API_KEY" extension:env',
    '"SENDGRID_API_KEY" extension:env',
    '"TELEGRAM_BOT_TOKEN" extension:env',
    '"DISCORD_TOKEN" extension:env',
    '"DISCORD_BOT_TOKEN" extension:env',
    '"SLACK_BOT_TOKEN" extension:env',
    '"SLACK_API_TOKEN" extension:env',
    '"MAILGUN_API_KEY" extension:env',
    '"MAPBOX_API_KEY" extension:env',
    '"AWS_SECRET_ACCESS_KEY" extension:env',
    '"AWS_ACCESS_KEY_ID" extension:env',
    '"GOOGLE_API_KEY" extension:env',
    '"GEMINI_API_KEY" extension:env',
]

PREFIX_QUERIES = [
    'sk- AND "sk-" extension:env',
    'sk- AND "sk-" extension:json',
    'sk- AND "sk-" extension:yaml',
    'sk- AND "sk-" extension:py',
    'sk- AND "sk-" extension:js',
    'hf_ AND "hf_" extension:env',
    'hf_ AND "hf_" extension:json',
    'sk-ant- AND "sk-ant-" extension:env',
    'sk-ant- AND "sk-ant-" extension:json',
    'sk_live_ extension:env',
    'rk_live_ extension:env',
    '"ghp_" AND ghp_ extension:env',
    '"ghp_" AND ghp_ extension:json',
    'ghp_ extension:txt',
    'AIza extension:env',
    'AIza extension:json',
    '"SG." AND SG. extension:env',
    '"SG." AND SG. extension:json',
    '"key-" AND api_key extension:env',
    'glpat- extension:env',
    'secret_ AND notion extension:env',
    'lin_api_ extension:env',
    'xoxb- AND "xoxb-" extension:env',
    'xoxb- AND "xoxb-" extension:json',
    '"AKIA" AND secret extension:env',
    'sk- in:filename .env',
    'sk- in:filename .env.local',
    'sk- in:filename .env.production',
    'sk- in:filename .env.development',
    'sk- in:filename .env.staging',
    'hf_ in:filename .env',
    'hf_ in:filename .env.local',
    'ghp_ in:filename .env',
    'ghp_ in:filename .txt',
    'AIza in:filename .env',
    'api_key in:filename .env',
    'api_key in:filename .env.local',
    'secret in:filename .env',
    'secret in:filename .env.local',
    'token in:filename .env',
    'token in:filename .env.local',
]

ALL_QUERIES = ENV_VAR_QUERIES + PREFIX_QUERIES


def is_placeholder(key: str) -> bool:
    placeholders = [
        "1234567", "xxxxx", "changeme", "placeholder",
        "your-api", "your_key", "YOUR_", "your-",
        "example", "test_key", "dummy", "sample",
        "XXXXXXXX", "xxxxxxx", "0000000",
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
