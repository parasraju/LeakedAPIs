import requests


def check_openai_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if r.status_code == 200:
            print(f"  Valid OpenAI key: {api_key[:10]}...{api_key[-6:]}")
            return True
        print(f"  Invalid OpenAI key: {api_key[:10]}...{api_key[-6:]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking OpenAI key: {e}")
        return False


def check_huggingface_key(api_key: str) -> bool:
    if not api_key or not api_key.startswith("hf_"):
        return False
    try:
        r = requests.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "HF-Key-Checker/1.0"},
            timeout=10
        )
        masked = f"{api_key[:10]}...{api_key[-6:]}" if len(api_key) > 16 else api_key
        if r.status_code == 200:
            print(f"  Valid HF key: {masked}")
            return True
        print(f"  Invalid HF key: {masked}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking HF key: {e}")
        return False


def check_anthropic_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.anthropic.com/v1/users/me",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=10
        )
        if r.status_code == 200:
            print(f"  Valid Anthropic key: {api_key[:12]}...{api_key[-6:]}")
            return True
        print(f"  Invalid Anthropic key: {api_key[:12]}...{api_key[-6:]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Anthropic key: {e}")
        return False


def check_stripe_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.stripe.com/v1/charges?limit=1",
            auth=(api_key, ""),
            timeout=10
        )
        if r.status_code == 200:
            print(f"  Valid Stripe key: {api_key[:12]}...{api_key[-6:]}")
            return True
        print(f"  Invalid Stripe key: {api_key[:12]}...{api_key[-6:]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Stripe key: {e}")
        return False


def check_github_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if r.status_code == 200:
            print(f"  Valid GitHub token: {api_key[:6]}...{api_key[-6:]}")
            return True
        print(f"  Invalid GitHub token: {api_key[:6]}...{api_key[-6:]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking GitHub token: {e}")
        return False


def check_google_gemini_key(api_key: str) -> bool:
    try:
        r = requests.get(
            f"https://generativelanguage.googleapis.com/v1/models?key={api_key}",
            timeout=10
        )
        if r.status_code == 200:
            print(f"  Valid Google AI key: {api_key[:8]}...{api_key[-6:]}")
            return True
        print(f"  Invalid Google AI key: {api_key[:8]}...{api_key[-6:]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Google AI key: {e}")
        return False


def check_telegram_bot_key(api_key: str) -> bool:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{api_key}/getMe",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                username = data.get("result", {}).get("username", "?")
                print(f"  Valid Telegram bot: @{username}")
                return True
        print("  Invalid Telegram bot token")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Telegram bot: {e}")
        return False


def check_discord_bot_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {api_key}"},
            timeout=10
        )
        if r.status_code == 200:
            print("  Valid Discord bot token")
            return True
        print("  Invalid Discord bot token")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Discord bot: {e}")
        return False


def check_sendgrid_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.sendgrid.com/v3/scopes",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if r.status_code == 200:
            print(f"  Valid SendGrid key: {api_key[:10]}...{api_key[-6:]}")
            return True
        print(f"  Invalid SendGrid key: {api_key[:10]}...{api_key[-6:]}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking SendGrid key: {e}")
        return False


def check_gitlab_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://gitlab.com/api/v4/user",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if r.status_code == 200:
            print("  Valid GitLab token")
            return True
        print(f"  Invalid GitLab token (HTTP {r.status_code})")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking GitLab token: {e}")
        return False


def check_notion_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://api.notion.com/v1/users/me",
            headers={"Authorization": f"Bearer {api_key}", "Notion-Version": "2022-06-28"},
            timeout=10
        )
        if r.status_code == 200:
            bot_name = r.json().get("bot", {}).get("owner", {}).get("workspace_name", "?")
            print(f"  Valid Notion key (workspace: {bot_name})")
            return True
        print(f"  Invalid Notion key (HTTP {r.status_code})")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Notion key: {e}")
        return False


def check_slack_key(api_key: str) -> bool:
    try:
        r = requests.get(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                team = data.get("team", "?")
                print(f"  Valid Slack token (team: {team})")
                return True
            print(f"  Slack auth failed: {data.get('error', 'unknown')}")
            return False
        print(f"  Invalid Slack token (HTTP {r.status_code})")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Network error checking Slack token: {e}")
        return False


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
