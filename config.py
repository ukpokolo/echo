import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly, human-sounding support assistant for a company on Microsoft Teams. "
    "The user may have sent several short messages in a row; they have been collected and given "
    "to you as one block, in the order they were sent. Treat the whole block as a single enquiry, "
    "recover the true intent across the fragments, and reply ONCE with one natural, concise answer. "
    "Never mention that messages were batched or delayed. If you do not know something (for example "
    "opening hours), ask a short clarifying question or say you will check, rather than inventing it."
)


@dataclass(frozen=True)
class Settings:
    port: int
    microsoft_app_id: str
    microsoft_app_password: str
    microsoft_app_tenant_id: str
    redis_url: str
    debounce_seconds: float
    debounce_max_wait_seconds: float
    buffer_ttl_seconds: int
    poll_interval_seconds: float
    llm_provider: str
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    azure_openai_api_version: str
    openai_api_key: str
    openai_model: str
    system_prompt: str


def load_settings() -> Settings:
    return Settings(
        port=_get_int("PORT", 3978),
        microsoft_app_id=os.getenv("MICROSOFT_APP_ID", ""),
        microsoft_app_password=os.getenv("MICROSOFT_APP_PASSWORD", ""),
        microsoft_app_tenant_id=os.getenv("MICROSOFT_APP_TENANT_ID", ""),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        debounce_seconds=_get_float("DEBOUNCE_SECONDS", 5.0),
        debounce_max_wait_seconds=_get_float("DEBOUNCE_MAX_WAIT_SECONDS", 20.0),
        buffer_ttl_seconds=_get_int("BUFFER_TTL_SECONDS", 300),
        poll_interval_seconds=_get_float("POLL_INTERVAL_SECONDS", 0.5),
        llm_provider=os.getenv("LLM_PROVIDER", "azure").strip().lower(),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        system_prompt=os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    )
