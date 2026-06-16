"""Application-level singletons, initialised at startup."""
from __future__ import annotations

from .config import get_settings
from .mail_source.gmail import GmailApi
from .ollama_client import OllamaClient

_gmail: GmailApi | None = None
_ollama: OllamaClient | None = None


def init_state() -> None:
    global _gmail, _ollama
    settings = get_settings()
    _gmail = GmailApi(settings)
    _ollama = OllamaClient(settings.ollama_base_url, settings.ollama_model)


def get_gmail() -> GmailApi:
    assert _gmail is not None, "call init_state() first"
    return _gmail


def get_ollama() -> OllamaClient:
    assert _ollama is not None, "call init_state() first"
    return _ollama
