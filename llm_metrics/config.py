"""Runtime configuration read from environment variables.

Owns: environment selection (`APP_ENV`), simulated-provider wiring, the
database path, the dashboard port, and the benchmark runner's origin. Every
reader takes an optional `environ` mapping so tests never touch the real
process environment. Invalid values raise `ConfigError` before any measurement
or paid call happens.

Secrets are not read here: the OpenAI key is read only by `real_smoke`.
"""

from collections.abc import Mapping
import os
import pathlib
import re

from llm_metrics import providers

VALID_ENVS = ("test", "prod")
DEFAULT_ENV = "test"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "llm_metrics.db"
DEFAULT_PORT = 8000

# Where the benchmark runner executes, not the provider's serving region. Set
# explicitly by each deployment; never inferred from IP addresses,
# geolocation, or cloud metadata services, so the stored origin is exactly what
# the deployment declared. Unset means local development.
ORIGIN_CLOUD_VARIABLE = "LLM_METRICS_ORIGIN_CLOUD"
ORIGIN_REGION_VARIABLE = "LLM_METRICS_ORIGIN_REGION"
DEFAULT_ORIGIN_CLOUD = "local"
DEFAULT_ORIGIN_REGION = "unknown"
# Lowercase letters, digits and inner hyphens, at most 63 characters: covers
# names like aws / us-east-1, gcp / us-central1, azure / eastus, and rejects
# typos such as "US-East-1" that would otherwise create a new origin.
_ORIGIN_VALUE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class ConfigError(Exception):
    """Raised when the configuration is invalid or unsupported."""


def _invalid_env(app_env: str) -> ConfigError:
    return ConfigError(
        f"Invalid APP_ENV={app_env!r}. Expected one of:"
        f" {', '.join(VALID_ENVS)}."
    )


def get_app_env(environ: Mapping[str, str] | None = None) -> str:
    """Returns `APP_ENV`: "test" (the safe default when unset) or "prod".

    Raises:
        ConfigError: For any other value.
    """
    if environ is None:
        environ = os.environ
    app_env = environ.get("APP_ENV", DEFAULT_ENV)
    if app_env not in VALID_ENVS:
        raise _invalid_env(app_env)
    return app_env


def get_provider(app_env: str) -> providers.LLMProvider:
    """Returns the provider for the simulated CLI in `app_env`.

    Raises:
        ConfigError: For "prod": the simulated CLI and `./run.sh` must never
            spend money or pass simulated data off as production data. Real
            requests go only through `python -m llm_metrics.real_smoke`.
    """
    if app_env == "test":
        return providers.DummyProvider()
    if app_env == "prod":
        raise ConfigError(
            "APP_ENV=prod: ./run.sh and this command never call a paid API,"
            " and the dummy provider is not a production provider. Refusing"
            " to run. For one real request, use:"
            " python -m llm_metrics.real_smoke"
        )
    raise _invalid_env(app_env)


def get_db_path(environ: Mapping[str, str] | None = None) -> pathlib.Path:
    """Returns the SQLite database path.

    `LLM_METRICS_DB_PATH` overrides the default `data/llm_metrics.db`; tests
    use it so they never write to the developer's database.
    """
    if environ is None:
        environ = os.environ
    return pathlib.Path(environ.get("LLM_METRICS_DB_PATH") or DEFAULT_DB_PATH)


def get_port(environ: Mapping[str, str] | None = None) -> int:
    """Returns the dashboard port from `LLM_METRICS_PORT` (default 8000).

    0 asks the operating system for any free port.

    Raises:
        ConfigError: If the value is not an integer from 0 to 65535.
    """
    if environ is None:
        environ = os.environ
    value = environ.get("LLM_METRICS_PORT") or str(DEFAULT_PORT)
    if not value.isdigit() or int(value) > 65535:
        raise ConfigError(
            f"Invalid LLM_METRICS_PORT={value!r}. Expected 0-65535."
        )
    return int(value)


def get_origin(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Returns where this benchmark runner executes.

    Reads `LLM_METRICS_ORIGIN_CLOUD` and `LLM_METRICS_ORIGIN_REGION`. Unset or
    empty values mean local development: ("local", "unknown").

    Returns:
        (origin_cloud, origin_region), e.g. ("aws", "us-east-1").

    Raises:
        ConfigError: If a value is not a lowercase name of letters, digits and
            inner hyphens (at most 63 characters). The invalid value is not
            echoed in the message.
    """
    if environ is None:
        environ = os.environ
    origin = []
    for variable, default in (
        (ORIGIN_CLOUD_VARIABLE, DEFAULT_ORIGIN_CLOUD),
        (ORIGIN_REGION_VARIABLE, DEFAULT_ORIGIN_REGION),
    ):
        value = environ.get(variable) or default
        if not _ORIGIN_VALUE.fullmatch(value):
            raise ConfigError(
                f"Invalid {variable}. Expected lowercase letters, digits and"
                " hyphens (e.g. aws / us-east-1), at most 63 characters."
            )
        origin.append(value)
    return origin[0], origin[1]
