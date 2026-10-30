"""Environment selection (APP_ENV), provider wiring, and database location."""

import os
from collections.abc import Mapping
from pathlib import Path

from llm_metrics.providers import DummyProvider, LLMProvider

VALID_ENVS = ("test", "prod")
DEFAULT_ENV = "test"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "llm_metrics.db"


class ConfigError(Exception):
    """Raised when the configuration is invalid or unsupported."""


def _invalid_env(app_env: str) -> ConfigError:
    return ConfigError(
        f"Invalid APP_ENV={app_env!r}. Expected one of: {', '.join(VALID_ENVS)}."
    )


def get_app_env(environ: Mapping[str, str] | None = None) -> str:
    """Read APP_ENV. Defaults to "test"; values other than test/prod are an error."""
    if environ is None:
        environ = os.environ
    app_env = environ.get("APP_ENV", DEFAULT_ENV)
    if app_env not in VALID_ENVS:
        raise _invalid_env(app_env)
    return app_env


def get_provider(app_env: str) -> LLMProvider:
    """Return the provider for an environment."""
    if app_env == "test":
        return DummyProvider()
    if app_env == "prod":
        raise ConfigError(
            "APP_ENV=prod has no real provider yet. "
            "Refusing to run: the dummy provider is not a production provider."
        )
    raise _invalid_env(app_env)


def get_db_path(environ: Mapping[str, str] | None = None) -> Path:
    """SQLite file for observations. LLM_METRICS_DB_PATH overrides the default
    (used by tests so they never write to the developer's database)."""
    if environ is None:
        environ = os.environ
    return Path(environ.get("LLM_METRICS_DB_PATH") or DEFAULT_DB_PATH)
