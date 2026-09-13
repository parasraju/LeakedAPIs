# API Instructor — AI Provider Reference

API Instructor includes a unified **provider registry** for AI model providers,
plus the key-management, validation, model-discovery and health tooling shown
below. This page is generated alongside the live registry in
`api/providers/catalog.py`.

---

## Provider commands

```powershell
# List supported providers
python main.py providers
python main.py providers --json

# List services scanned for by the GitHub scanner
python main.py services

# Show configured API keys (always masked — never printed in full)
python main.py keys
python main.py keys --json

# Validate one provider (uses its env var by default)
python main.py validate openai
python main.py validate anthropic --json
python main.py validate --key sk-... openai

# Show health/status of every provider (no key required)
python main.py validate
python main.py validate --json

# List the verified static model catalog
python main.py models
python main.py models --provider openai
python main.py models --provider anthropic

# Resolve a convenience alias to a concrete model id
python main.py models --alias deepseek:reasoner
python main.py models --alias google:gemini-flash

# Fetch the live model list from a provider (requires its API key in env)
python main.py models --discover groq
```

## Dashboard routes

| Route | Method | Description |
|---|---|---|
| `/api/providers` | GET | All providers + masked key status |
| `/api/services` | GET | Scanner services list |
| `/api/models` | GET | Model catalog (`?provider=` to filter) |
| `/api/models/discover` | POST | Live model discovery `{provider}` |
| `/api/keys/status` | GET | Configured keys (masked) |
| `/api/health` | GET | Health of every provider |
| `/api/validate/{provider}` | POST | Validate credentials `{key?}` |

---

## Supported providers

| Provider | ID | Env var | OpenAI-compatible | Model discovery |
|---|---|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` | yes | `/v1/models` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | no (dedicated adapter) | `/v1/models` |
| Google Gemini | `google` | `GOOGLE_API_KEY` (`GEMINI_API_KEY`) | no (query-param auth) | `/v1/models` |
| xAI | `xai` | `XAI_API_KEY` | yes | `/v1/models` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | yes | `/v1/models` |
| Mistral | `mistral` | `MISTRAL_API_KEY` | yes | `/v1/models` |
| Groq | `groq` | `GROQ_API_KEY` | yes | `/v1/models` |
| Together AI | `together` | `TOGETHER_API_KEY` | yes | `/v1/models` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | yes (dynamic catalog) | `/v1/models` |
| Fireworks AI | `fireworks` | `FIREWORKS_API_KEY` | yes | `/v1/models` |
| Perplexity | `perplexity` | `PERPLEXITY_API_KEY` | yes | no |
| Cerebras | `cerebras` | `CEREBRAS_API_KEY` | yes | `/v1/models` |
| SambaNova | `sambanova` | `SAMBANOVA_API_KEY` | yes | `/v1/models` |
| DeepInfra | `deepinfra` | `DEEPINFRA_API_KEY` | yes | `/v1/models` |
| Cohere | `cohere` | `COHERE_API_KEY` | no | `/v1/models` |
| AI21 | `ai21` | `AI21_API_KEY` | no | no |
| Replicate | `replicate` | `REPLICATE_API_TOKEN` | no (dynamic per-owner catalog) | no |
| Hugging Face | `huggingface` | `HF_TOKEN` | no | dynamic hub |
| Amazon Bedrock | `bedrock` | via AWS credentials | special-auth | — |
| Azure OpenAI | `azure_openai` | `AZURE_OPENAI_API_KEY` + endpoint | special-auth | — |
| Vertex AI | `vertex` | `GOOGLE_APPLICATION_CREDENTIALS` | special-auth | — |

### Coding/agent ecosystems

OpenCode, Cursor and Kiro do **not** expose public API keys for model access, so
they are registered with `status="unsupported"`. Validate the underlying model
providers instead (e.g. `python main.py validate openai`).

---

## Environment variables

```env
# Model providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=          # or GEMINI_API_KEY
XAI_API_KEY=
DEEPSEEK_API_KEY=
MISTRAL_API_KEY=
COHERE_API_KEY=
GROQ_API_KEY=
TOGETHER_API_KEY=
OPENROUTER_API_KEY=
FIREWORKS_API_KEY=
PERPLEXITY_API_KEY=
CEREBRAS_API_KEY=
SAMBANOVA_API_KEY=
DEEPINFRA_API_KEY=
AI21_API_KEY=
REPLICATE_API_TOKEN=
HF_TOKEN=                 # or HUGGINGFACE_TOKEN

# Special-auth providers (no single API key)
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AWS_ACCESS_KEY_ID=        # Bedrock (SigV4)
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
GOOGLE_APPLICATION_CREDENTIALS=   # Vertex AI service account
GOOGLE_CLOUD_PROJECT=

# Scanner (unchanged)
GITHUB_TOKEN=
```

## Model catalog

- **Static models** — verified flagship models for OpenAI, Anthropic, Google,
  xAI, DeepSeek, Mistral, Groq, Cohere, Together, Cerebras, Perplexity, AI21,
  SambaNova, DeepInfra, Fireworks and OpenRouter (see `api/providers/models.py`).
- **Dynamic models** — providers with a `/v1/models` endpoint (OpenRouter,
  Groq, Fireworks, Together, Cerebras, SambaNova, DeepInfra, OpenAI, etc.) are
  refreshed at runtime with:

  ```powershell
  python main.py models --discover groq
  ```

- **Aliases** resolve to concrete model ids and never silently change meaning:

  ```text
  openai:gpt-latest        anthropic:claude-opus   anthropic:claude-sonnet
  anthropic:claude-haiku   google:gemini-flash     google:gemini-pro
  deepseek:reasoner        deepseek:chat           xai:grok
  mistral:large            mistral:small           mistral:codestral
  groq:llama               together:llama          together:qwen
  cohere:command           fireworks:llama
  ```

## Validation results

`validate` and `POST /api/validate/{provider}` return a normalized result —
the raw key is never included:

```json
{
  "provider": "openai",
  "valid": true,
  "authenticated": true,
  "message": "API key is valid",
  "models_available": true,
  "masked": "sk-••••••••••••••••1234"
}
```

Errors are normalized too:

```json
{
  "provider": "openai",
  "error_type": "authentication",
  "message": "Authentication failed",
  "retryable": false
}
```

`error_type` values: `authentication`, `rate_limited`, `quota_exhausted`,
`model_not_found`, `invalid_request`, `provider_outage`, `timeout`,
`network_failure`, `unsupported_capability`.

## Health statuses

```
configured  authenticated  invalid_credentials  rate_limited
unavailable  unsupported  not_configured
```

---

## Adding a new provider

1. Add one `Provider(...)` record to `api/providers/catalog.py`
   (id, name, `env_var`, `base_url`, `auth_method`, `doc_url`). If it exposes
   an OpenAI-compatible `/v1/models`, set `openai_compatible=True` and
   `supports_model_discovery=True` — the shared adapter handles it.
2. If the key has a recognizable shape, add a hint in
   `api/providers/keys.py::_KEY_FORMAT_HINTS` and a detection pattern in
   `api/patterns.py` (only if the prefix is distinctive enough to avoid
   false positives).
3. Add verified flagship models to `api/providers/models.py`, plus aliases
   in `ALIASES`. Do **not** hardcode rapidly-changing model lists — prefer
   discovery.
4. Run `python main.py providers --json` and
   `python -m pytest tests/test_provider_registry.py`.

Verification rule: never ship an endpoint, model id or auth scheme you have not
confirmed against the provider's official documentation. Unverified services
are registered with `status="unsupported"` rather than fake integration code.

## Security

- Keys are read from environment variables only; never hard-coded or committed
  (see `.env.example` in the repo root as a reference — API Instructor reads
  variables from the environment, it does not load a `.env` file).
- Keys are always masked (`sk-••••••••••••••••1234`), never printed in full.
  `get_credentials()` keeps the key in memory only; `to_dict()` and every
  JSON/CLI response omit it.
- Validation and model endpoints never include the key value in results/logs.
- Never commit a real `.env` with live keys.