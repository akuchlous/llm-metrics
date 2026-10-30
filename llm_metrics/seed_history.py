"""Seeds deterministic simulated TTFT history for the dummy provider.

Usage: python -m llm_metrics.seed_history

Inserts one simulated TTFT observation per hour for a fixed 7-day window,
labelled environment "test", so a fresh clone has a meaningful dashboard. The
same values and timestamps are produced on every machine and every run, and
re-running inserts nothing new. Refuses to run outside the test environment,
so simulated values can never be mixed into real data.
"""

import datetime
import os
import random
import sys

from llm_metrics import config
from llm_metrics import providers
from llm_metrics import storage

# A fixed window, not "the last week", so the history is reproducible. It moves
# out of the dashboard's relative time windows as real time passes.
HISTORY_START = datetime.datetime(2026, 10, 23, tzinfo=datetime.timezone.utc)
HOURS = 7 * 24
RANDOM_SEED = 4

# Values centre on the dummy provider's 100 ms first-token delay so history and
# live measurements look continuous. A few hours get a latency spike so the
# high percentiles differ from the median.
BASE_MS = 100.0
NOISE_SD_MS = 8.0
MIN_MS = 60.0
SPIKE_COUNT = 5
SPIKE_RANGE_MS = (250.0, 500.0)


def simulated_ttft_history() -> list[tuple[datetime.datetime, dict]]:
    """Returns the simulated history, oldest first. Deterministic.

    Returns:
        `HOURS` pairs of (recorded_at in UTC, observation), where each
        observation is {"provider", "model", "metric": "ttft", "value"} in ms.
    """
    rng = random.Random(RANDOM_SEED)
    spike_hours = set(rng.sample(range(HOURS), SPIKE_COUNT))
    history = []
    for hour in range(HOURS):
        if hour in spike_hours:
            value_ms = rng.uniform(*SPIKE_RANGE_MS)
        else:
            value_ms = max(MIN_MS, rng.gauss(BASE_MS, NOISE_SD_MS))
        observation = {
            "provider": providers.DummyProvider.name,
            "model": providers.DummyProvider.model,
            "metric": "ttft",
            "value": round(value_ms, 1),
        }
        recorded_at = HISTORY_START + datetime.timedelta(hours=hour)
        history.append((recorded_at, observation))
    return history


def main() -> int:
    """Seeds the history and prints how many rows were new.

    Returns:
        Process exit code: 0 on success, 2 for an invalid or non-test
        `APP_ENV` (nothing is written).
    """
    try:
        app_env = config.get_app_env()
    except config.ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    if app_env != "test":
        print(
            "Error: simulated history can only be seeded with APP_ENV=test.",
            file=sys.stderr,
        )
        return 2

    db_path = config.get_db_path()
    history = simulated_ttft_history()
    inserted = storage.save_new_observations(db_path, history, "test")
    first, last = history[0][0], history[-1][0]
    print(
        f"Simulated TTFT history: {inserted} new,"
        f" {len(history) - inserted} already present"
        f" ({first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} UTC, hourly)"
    )
    print(f"Database: {os.path.relpath(db_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
