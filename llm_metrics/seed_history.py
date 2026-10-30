"""Seed deterministic simulated TTFT history for the dummy provider.

Usage: python -m llm_metrics.seed_history

Inserts one simulated TTFT observation per hour for a fixed 7-day window,
labelled environment='test'. The same values and timestamps are produced every
time, and re-running inserts nothing new.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

from llm_metrics.config import ConfigError, get_app_env, get_db_path
from llm_metrics.providers import DummyProvider
from llm_metrics.storage import save_new_observations

# Fixed window so the history is identical on every machine and every run.
HISTORY_START = datetime(2026, 10, 23, tzinfo=timezone.utc)
HOURS = 7 * 24
RANDOM_SEED = 4

# Values centre on the dummy provider's 100 ms delay so history and live
# measurements look continuous. A few hours get a latency spike.
BASE_MS = 100.0
NOISE_SD_MS = 8.0
MIN_MS = 60.0
SPIKE_COUNT = 5
SPIKE_RANGE_MS = (250.0, 500.0)


def simulated_ttft_history() -> list[tuple[datetime, dict]]:
    """Return HOURS (recorded_at, result) pairs, oldest first. Deterministic."""
    rng = random.Random(RANDOM_SEED)
    spike_hours = set(rng.sample(range(HOURS), SPIKE_COUNT))
    history = []
    for hour in range(HOURS):
        if hour in spike_hours:
            value_ms = rng.uniform(*SPIKE_RANGE_MS)
        else:
            value_ms = max(MIN_MS, rng.gauss(BASE_MS, NOISE_SD_MS))
        result = {
            "provider": DummyProvider.name,
            "model": DummyProvider.model,
            "metric": "ttft",
            "value": round(value_ms, 1),
        }
        history.append((HISTORY_START + timedelta(hours=hour), result))
    return history


def main() -> int:
    try:
        app_env = get_app_env()
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    if app_env != "test":
        print("Error: simulated history can only be seeded with APP_ENV=test.", file=sys.stderr)
        return 2

    db_path = get_db_path()
    history = simulated_ttft_history()
    inserted = save_new_observations(db_path, history, "test")
    first, last = history[0][0], history[-1][0]
    print(
        f"Simulated TTFT history: {inserted} new, {len(history) - inserted} already present"
        f" ({first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} UTC, hourly)"
    )
    print(f"Database: {os.path.relpath(db_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
