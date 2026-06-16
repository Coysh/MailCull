from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file so the server can be launched from any CWD
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    token_path: Path = Path("/data/token.json")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    scan_since_days: int = 365
    dry_run: bool = True

    db_path: Path = Path("/data/mailcull.db")
    app_port: int = 8420
    app_host: str = "127.0.0.1"

    # Gmail scopes requested during OAuth
    gmail_scopes: list[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.settings.basic",
    ]

    # Optional: include gmail.send for mailto unsubscribes
    include_send_scope: bool = False


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
