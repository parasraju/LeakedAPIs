"""Live API-key validators.

Each validator returns True when the key is accepted by the provider's
authentication endpoint and False otherwise (invalid key, expired token, or
network failure).
"""

import logging

import requests

logger = logging.getLogger(__name__)

OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
HUGGINGFACE_WHOAMI_URL = "https://huggingface.co/api/whoami-v2"
ANTHROPIC_USERS_URL = "https://api.anthropic.com/v1/users/me"
STRIPE_CHARGES_URL = "https://api.stripe.com/v1/charges?limit=1"
GITHUB_USER_URL = "https://api.github.com/user"
GOOGLE_MODELS_URL = "https://generativelanguage.googleapis.com/v1/models"
TELEGRAM_GETME_URL = "https://api.telegram.org/bot"
DISCORD_ME_URL = "https://discord.com/api/v10/users/@me"
SENDGRID_SCOPES_URL = "https://api.sendgrid.com/v3/scopes"
GITLAB_USER_URL = "https://gitlab.com/api/v4/user"
NOTION_ME_URL = "https://api.notion.com/v1/users/me"
SLACK_AUTH_TEST_URL = "https://slack.com/api/auth.test"

ANTHROPIC_VERSION = "2023-06-01"
NOTION_VERSION = "2022-06-28"
DISCORD_DEFAULT_USER_AGENT = "API-Instructor/1.0"


def _mask(key: str, head: int = 10, tail: int = 6) -> str:
    return f"{key[:head]}...{key[-tail:]}" if len(key) > head + tail else key


def check_openai_key(api_key: str) -> bool:
    try:
        r = requests.get(
            OPENAI_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking OpenAI key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s OpenAI key: %s", "Valid" if valid else "Invalid", _mask(api_key, 10, 6))
    return valid


def check_huggingface_key(api_key: str) -> bool:
    if not api_key or not api_key.startswith("hf_"):
        return False
    try:
        r = requests.get(
            HUGGINGFACE_WHOAMI_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "HF-Key-Checker/1.0",
            },
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking HF key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s HF key: %s", "Valid" if valid else "Invalid", _mask(api_key))
    return valid


def check_anthropic_key(api_key: str) -> bool:
    try:
        r = requests.get(
            ANTHROPIC_USERS_URL,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Anthropic key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s Anthropic key: %s", "Valid" if valid else "Invalid", _mask(api_key, 12, 6))
    return valid


def check_stripe_key(api_key: str) -> bool:
    try:
        r = requests.get(STRIPE_CHARGES_URL, auth=(api_key, ""), timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Stripe key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s Stripe key: %s", "Valid" if valid else "Invalid", _mask(api_key, 12, 6))
    return valid


def check_github_key(api_key: str) -> bool:
    try:
        r = requests.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking GitHub token: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s GitHub token: %s", "Valid" if valid else "Invalid", _mask(api_key, 6, 6))
    return valid


def check_google_gemini_key(api_key: str) -> bool:
    try:
        r = requests.get(f"{GOOGLE_MODELS_URL}?key={api_key}", timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Google AI key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s Google AI key: %s", "Valid" if valid else "Invalid", _mask(api_key, 8, 6))
    return valid


def check_telegram_bot_key(api_key: str) -> bool:
    try:
        r = requests.get(f"{TELEGRAM_GETME_URL}{api_key}/getMe", timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Telegram bot: %s", e)
        return False
    if r.status_code != 200:
        logger.info("Invalid Telegram bot token")
        return False
    data = r.json()
    if not data.get("ok"):
        logger.info("Invalid Telegram bot token")
        return False
    logger.info("Valid Telegram bot: @%s", data.get("result", {}).get("username", "?"))
    return True


def check_discord_bot_key(api_key: str) -> bool:
    try:
        r = requests.get(
            DISCORD_ME_URL,
            headers={
                "Authorization": f"Bot {api_key}",
                "User-Agent": DISCORD_DEFAULT_USER_AGENT,
            },
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Discord bot: %s", e)
        return False
    logger.info("Valid Discord bot token" if r.status_code == 200 else "Invalid Discord bot token")
    return r.status_code == 200


def check_sendgrid_key(api_key: str) -> bool:
    try:
        r = requests.get(
            SENDGRID_SCOPES_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking SendGrid key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s SendGrid key: %s", "Valid" if valid else "Invalid", _mask(api_key))
    return valid


def check_gitlab_key(api_key: str) -> bool:
    try:
        r = requests.get(
            GITLAB_USER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking GitLab token: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s GitLab token (HTTP %s)", "Valid" if valid else "Invalid", r.status_code)
    return valid


def check_notion_key(api_key: str) -> bool:
    try:
        r = requests.get(
            NOTION_ME_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": NOTION_VERSION,
            },
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Notion key: %s", e)
        return False
    if r.status_code == 200:
        workspace = r.json().get("bot", {}).get("owner", {}).get("workspace_name", "?")
        logger.info("Valid Notion key (workspace: %s)", workspace)
        return True
    logger.info("Invalid Notion key (HTTP %s)", r.status_code)
    return False


def check_slack_key(api_key: str) -> bool:
    try:
        r = requests.get(
            SLACK_AUTH_TEST_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Slack token: %s", e)
        return False
    if r.status_code != 200:
        logger.info("Invalid Slack token (HTTP %s)", r.status_code)
        return False
    data = r.json()
    if not data.get("ok"):
        logger.info("Slack auth failed: %s", data.get("error", "unknown"))
        return False
    logger.info("Valid Slack token (team: %s)", data.get("team", "?"))
    return True


VALIDATORS = {
    "OpenAI": check_openai_key,
    "HuggingFace": check_huggingface_key,
    "Anthropic": check_anthropic_key,
    "Stripe": check_stripe_key,
    "GitHub": check_github_key,
    "GoogleGemini": check_google_gemini_key,
    "TelegramBot": check_telegram_bot_key,
    "DiscordBot": check_discord_bot_key,
    "SendGrid": check_sendgrid_key,
    "GitLab": check_gitlab_key,
    "Notion": check_notion_key,
    "SlackBot": check_slack_key,
}
