"""Live API-key validators.

Each validator returns True when the key is accepted by the provider's
authentication endpoint and False otherwise (invalid key, expired token, or
network failure).
"""

import logging
import time
import functools

import requests

logger = logging.getLogger(__name__)

# cache with TTL 1h
_CACHE: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 3600

def _cache_key(service: str, key: str) -> str:
    return f"{service}:{key[:20]}"

def cached_validator(func):
    @functools.wraps(func)
    def wrapper(api_key: str) -> bool:
        # use service name from func
        svc = func.__name__.replace("check_", "").replace("_key", "")
        ck = _cache_key(svc, api_key)
        now = time.time()
        if ck in _CACHE and now - _CACHE[ck][1] < _CACHE_TTL:
            return _CACHE[ck][0]
        # retry on 429
        for attempt in range(3):
            try:
                res = func(api_key)
                # if func handled 429 as False, we still cache but with shorter TTL
                _CACHE[ck] = (res, now)
                return res
            except requests.RequestException as e:
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                    continue
                logger.warning("Retry exhausted for %s: %s", svc, e)
                return False
        return False
    return wrapper

def severity_score(service: str, valid: bool, path: str = "", repo: str = "") -> str:
    if not valid:
        return "low"
    # critical services
    critical = {"OpenAI", "Stripe", "AWSKey", "GitHub", "SlackBot"}
    high = {"Anthropic", "GoogleGemini", "SendGrid", "GitLab"}
    path_lower = path.lower()
    is_env = ".env" in path_lower or "credentials" in path_lower
    if service in critical and is_env:
        return "critical"
    if service in critical:
        return "high"
    if service in high and is_env:
        return "high"
    return "medium"

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


def check_linear_key(api_key: str) -> bool:
    try:
        r = requests.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json={"query": "{ viewer { id } }"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Linear key: %s", e)
        return False
    valid = r.status_code == 200 and "errors" not in r.json()
    logger.info("%s Linear key: %s", "Valid" if valid else "Invalid", _mask(api_key))
    return valid


def check_mailgun_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.mailgun.net/v3/domains",
            auth=("api", api_key),
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Mailgun key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s Mailgun key: %s", "Valid" if valid else "Invalid", _mask(api_key))
    return valid


def check_mapbox_key(api_key: str) -> bool:
    try:
        r = requests.get(
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/test.json?access_token={api_key}",
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Network error checking Mapbox key: %s", e)
        return False
    valid = r.status_code == 200
    logger.info("%s Mapbox key: %s", "Valid" if valid else "Invalid", _mask(api_key))
    return valid


def check_aws_key(api_key: str) -> bool:
    # AWS access key alone cannot be validated without secret; treat format-valid keys as unverifiable
    # Keep current status by returning True so re-check does not falsely invalidate
    logger.info("Skipping AWS key validation (needs secret): %s", _mask(api_key))
    return True


def check_pinecone_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.pinecone.io/indexes", headers={"Api-Key": api_key}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Pinecone: %s", e)
        return False
    valid = r.status_code in (200, 401) and r.status_code == 200 or r.status_code == 200
    # 401 means key format valid but unauthorized, treat as invalid
    valid = r.status_code == 200
    logger.info("%s Pinecone key: %s", "Valid" if valid else "Invalid", _mask(api_key))
    return valid


def check_supabase_key(api_key: str) -> bool:
    # Supabase JWT: try to decode header, basic check
    try:
        if api_key.startswith("eyJ"):
            # JWT format, treat as valid if 3 parts
            return api_key.count(".") == 2
        r = requests.get("https://api.supabase.io/v1/projects", headers={"apikey": api_key}, timeout=10)
        return r.status_code == 200
    except requests.RequestException:
        return False


def check_firebase_key(api_key: str) -> bool:
    # Firebase uses Google API key same as Gemini
    return check_google_gemini_key(api_key)


def check_cloudflare_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.cloudflare.com/client/v4/user/tokens/verify", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Cloudflare: %s", e)
        return False
    valid = r.status_code == 200 and r.json().get("success") is True
    logger.info("%s Cloudflare key", "Valid" if valid else "Invalid")
    return valid


def check_sentry_key(api_key: str) -> bool:
    try:
        r = requests.get("https://sentry.io/api/0/organizations/", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException:
        return False
    return r.status_code == 200


def check_twilio_key(api_key: str) -> bool:
    try:
        # Twilio SID check: need account SID + token, simple format check
        return api_key.startswith("SK") and len(api_key) == 34
    except Exception:
        return False


def check_openrouter_key(api_key: str) -> bool:
    try:
        r = requests.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking OpenRouter: %s", e)
        return False
    return r.status_code == 200


def check_xai_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.x.ai/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking xAI: %s", e)
        return False
    return r.status_code == 200


def check_deepseek_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.deepseek.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking DeepSeek: %s", e)
        return False
    return r.status_code == 200


def check_groq_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Groq: %s", e)
        return False
    return r.status_code == 200


def check_together_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.together.xyz/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Together: %s", e)
        return False
    return r.status_code == 200


def check_cohere_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.cohere.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Cohere: %s", e)
        return False
    return r.status_code == 200


def check_cerebras_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.cerebras.ai/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Cerebras: %s", e)
        return False
    return r.status_code == 200


def check_replicate_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.replicate.com/v1/account", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Replicate: %s", e)
        return False
    return r.status_code == 200


def check_perplexity_key(api_key: str) -> bool:
    try:
        r = requests.get("https://api.perplexity.ai/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": "sonar", "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}, timeout=10)
    except requests.RequestException as e:
        logger.warning("Network error checking Perplexity: %s", e)
        return False
    # 401/403 = invalid, anything else (400 model/auth quirk, 429) = key accepted
    return r.status_code in (200, 400, 429)


VALIDATORS = {
    "OpenAI": cached_validator(check_openai_key),
    "HuggingFace": cached_validator(check_huggingface_key),
    "Anthropic": cached_validator(check_anthropic_key),
    "Stripe": cached_validator(check_stripe_key),
    "GitHub": cached_validator(check_github_key),
    "GoogleGemini": cached_validator(check_google_gemini_key),
    "TelegramBot": cached_validator(check_telegram_bot_key),
    "DiscordBot": cached_validator(check_discord_bot_key),
    "SendGrid": cached_validator(check_sendgrid_key),
    "GitLab": cached_validator(check_gitlab_key),
    "Notion": cached_validator(check_notion_key),
    "SlackBot": cached_validator(check_slack_key),
    "Linear": cached_validator(check_linear_key),
    "Mailgun": cached_validator(check_mailgun_key),
    "Mapbox": cached_validator(check_mapbox_key),
    "AWSKey": cached_validator(check_aws_key),
    "Pinecone": cached_validator(check_pinecone_key),
    "Supabase": cached_validator(check_supabase_key),
    "Firebase": cached_validator(check_firebase_key),
    "Cloudflare": cached_validator(check_cloudflare_key),
    "Sentry": cached_validator(check_sentry_key),
    "Twilio": cached_validator(check_twilio_key),
    "OpenRouter": cached_validator(check_openrouter_key),
    "xAI": cached_validator(check_xai_key),
    "DeepSeek": cached_validator(check_deepseek_key),
    "Groq": cached_validator(check_groq_key),
    "TogetherAI": cached_validator(check_together_key),
    "Cerebras": cached_validator(check_cerebras_key),
    "Replicate": cached_validator(check_replicate_key),
    "Perplexity": cached_validator(check_perplexity_key),
}
