"""Environment selection (APP_ENV), provider wiring, database path, dashboard
port, and measurement origin."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from llm_metrics.providers import DummyProvider, LLMProvider

VALID_ENVS = ("test", "prod")
DEFAULT_ENV = "test"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "llm_metrics.db"
DEFAULT_PORT = 8000
# Where the benchmark runner executes (not the provider's serving region). Set
# explicitly by deployment; never inferred from IP, geolocation, or metadata
# services. Unset means local development.
ORIGIN_CLOUD_VARIABLE = "LLM_METRICS_ORIGIN_CLOUD"
ORIGIN_REGION_VARIABLE = "LLM_METRICS_ORIGIN_REGION"
DEFAULT_ORIGIN_CLOUD = "local"
DEFAULT_ORIGIN_REGION = "unknown"
# Lowercase letters, digits and inner hyphens, at most 63 characters: covers
# names like aws / us-east-1, gcp / us-central1, azure / eastus.
_ORIGIN_VALUE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


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
            "APP_ENV=prod: ./run.sh and this command never call a paid API, and the "
            "dummy provider is not a production provider. Refusing to run. For one "
            "real request, use: python -m llm_metrics.real_smoke"
        )
    raise _invalid_env(app_env)


def get_db_path(environ: Mapping[str, str] | None = None) -> Path:
    """SQLite file for observations. LLM_METRICS_DB_PATH overrides the default
    (used by tests so they never write to the developer's database)."""
    if environ is None:
        environ = os.environ
    return Path(environ.get("LLM_METRICS_DB_PATH") or DEFAULT_DB_PATH)


def get_port(environ: Mapping[str, str] | None = None) -> int:
    """Dashboard port. LLM_METRICS_PORT overrides the default; 0 picks a free port."""
    if environ is None:
        environ = os.environ
    value = environ.get("LLM_METRICS_PORT") or str(DEFAULT_PORT)
    if not value.isdigit() or int(value) > 65535:
        raise ConfigError(f"Invalid LLM_METRICS_PORT={value!r}. Expected 0-65535.")
    return int(value)


def get_origin(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    """(origin_cloud, origin_region) of this benchmark runner, from
    LLM_METRICS_ORIGIN_CLOUD / LLM_METRICS_ORIGIN_REGION (unset or empty:
    "local" / "unknown"). Invalid values are a ConfigError and are not echoed."""
    if environ is None:
        environ = os.environ
    origin = []
    for variable, default in ((ORIGIN_CLOUD_VARIABLE, DEFAULT_ORIGIN_CLOUD),
                              (ORIGIN_REGION_VARIABLE, DEFAULT_ORIGIN_REGION)):
        value = environ.get(variable) or default
        if not _ORIGIN_VALUE.fullmatch(value):
            raise ConfigError(
                f"Invalid {variable}. Expected lowercase letters, digits and hyphens "
                "(e.g. aws / us-east-1), at most 63 characters."
            )
        origin.append(value)
    return origin[0], origin[1]
