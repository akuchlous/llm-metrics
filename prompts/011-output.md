# Step 011 — Implementation report

Prompt: `011-errors-and-availability.md`.

## What changed

- **`outcomes.py` (new):** `SUCCESS`, the stable `FAILURE_CATEGORIES` (`timeout`, `rate_limited`, `provider_error`, `transport_error`, `invalid_response`), and `success_rate(counts)`.
- **`providers.py`:** `ProviderFailure(category)` is the mapping boundary for future adapters and rejects unknown categories such as `"http_503"`. `DummyProvider` gains deterministic simulated failures: `fail_with=<category>` after `fail_after_chunks`, and `omit_usage=True`.
- **`measure_request`:** returns an attempt with an `outcome` instead of raising for provider failures and contract violations. It also rejects text arriving after `Usage`, closing the gap noted in Step 010's design questions.
- **Schema version 3:** `requests.outcome` and `requests.failed_after_ms`; token and cost columns are nullable; a CHECK ties the facts to the outcome. The table is rebuilt inside the upgrade transaction.
- **CLI:** prints `Outcome: success` or `Outcome: FAILED — <label> (<category>)`, the failure time, and "unknown" for missing facts. It saves the attempt and exits 0.
- **Aggregate view:** a new "Observed benchmark success rate" section for the selected window. The metric section is headed "(successful attempts only)".
- **`/requests`:** new Outcome (FAILED + category) and "Failed after (ms)" columns; unknown values show "—".

## Tests / run

- 116 tests, OK on Python 3.13 and 3.11 (~19 s).
- Clean `./run.sh`: `Outcome: success`, plus all Step 010 output; `APP_ENV=prod ./run.sh` exits 2.
- With 3 injected simulated failures (rate-limited, timeout after 2 chunks, missing usage), the page showed **25.0%**, "1 of 4 attempts succeeded (3 failed, 75.0%)", 1 each for Timeout, Rate limited and Invalid response, and total latency n = 1 (success only). Checked in a browser screenshot.
- **Real upgrade:** a version-2 database created by the Step 010 code (2 requests, 174 observations) was upgraded to version 3. Both requests became `success` with their values intact, the 168 unpaired seeded rows were unchanged, and `input_tokens` became nullable.

## Success/failure semantics

- **One attempt = one provider call;** no retries.
- **`success`:** the stream finished, it had text, `Usage` arrived exactly once as the last item, and output stayed within the requested cap.
- **A failure category** comes from either:
  - a `ProviderFailure` raised by the provider (its category), or
  - a contract violation detected by measurement, which is `invalid_response`: no text, usage missing or repeated, text after usage, or output above the cap.
- **Any other exception is an llm-metrics bug:** it propagates and isn't recorded (a test covers this).
- **Nothing textual is stored:** no error messages, stack traces, prompts or secrets; only the category.

## Failure categories and mapping boundary

The categories are generic and cross-provider: timeout, rate limited, provider/server error, network/transport error, invalid response. A future adapter maps its native errors to one of them inside its `stream()` (raising `ProviderFailure`), so analytics never see provider wording. I didn't guess any provider-specific HTTP mapping. Provider-specific codes could later be kept in a separate optional column without changing aggregates.

## Schema / migration (unknown/null fields)

- `input_tokens`, `output_tokens`, `input_cost`, `output_cost` and `total_cost` are **NULL for failures, meaning unknown**, and never 0.
- `requested_max_output_tokens` and the effective prices are still stored for failures, because they're known at attempt time.
- `failed_after_ms` is **request start → failure detected**, only for failures. It is never `total_latency`.
- A table CHECK enforces both rules: success means facts known and `failed_after_ms` NULL; failure means facts NULL and `failed_after_ms` set. Tests show fabricated zeros and inconsistent rows are rejected.
- **Version 2 → 3:** SQLite can't drop `NOT NULL`, so `requests` is rebuilt (create `requests_v3`, copy with `outcome = 'success'`, drop, rename) inside the same `BEGIN IMMEDIATE` transaction as the version bump. Every Step-010 request was a completed success, so that classification is accurate. Unpaired observations are untouched, and no attempts are invented.

## Availability calculation and population

- **Population:** every `requests` row (attempt) for the environment, provider and model with `now − window <= recorded_at <= now`, using the same window rules as the metrics.
- `attempts = successes + failures`, `success_rate = successes / attempts`, `failure_rate = failures / attempts`, plus failures by category.
- **No attempts gives no rate** (the page says so; no "%" is shown). All failed gives 0.0%.
- Labelled **"Observed benchmark success rate"**, with a note that it reflects our runner's own attempts, not provider uptime. Pre-Step-010 observations and simulated history aren't attempts and aren't counted.

## Partial measurements on failure

Discarded. If text arrived before the failure, the TTFT and chunks observed aren't saved, and no observations are written for a failed attempt. That keeps the latency and throughput percentiles success-only with no query changes; a test checks that failures don't change `n`. `save_request` refuses a failed attempt that comes with metrics.

## Known limitations / review questions

- **Lost diagnostic:** discarding partial TTFT loses "it failed after starting to stream". It could be kept later as an explicitly named failure field, e.g. `first_output_ms`.
- **No measurement-level timeout:** a stream that hangs without raising would block. Real adapters must enforce their own timeouts and raise `timeout`.
- **No real provider error mapping yet,** and no retries (a future decision: separate attempts, or part of a logical request).
- **Foreign keys** are still not enforced (`PRAGMA foreign_keys` is off), as noted in Step 10.
- **Exit code:** the CLI exits 0 for a recorded failed attempt; scripts must read the outcome, not the exit code.

## Design Q&A

**Why record failures as rows with NULLs instead of zeros or a separate errors table?** A zero claims a measurement ("this request cost $0 and took 0 ms") and would drag percentiles and cost averages down. NULL says "unknown", and SQL aggregates skip it. One table keeps the attempt count trivially correct (`COUNT(*)`), and the CHECK makes "failure implies unknown facts" a database invariant. A separate errors table would make the success rate a cross-table union and risk counting the same attempt twice.

**Why are partial TTFT values discarded?** The prompt requires that existing percentile charts describe successful measurements only. Storing failure-time TTFT as normal observations would silently mix populations unless every query joined on outcome. Discarding keeps the populations clean by construction. *Tradeoff:* we lose some diagnostic detail; it can return as an explicitly named failure field.

**Why is `invalid_response` decided by measurement, not the provider?** Contract violations (missing or repeated usage, text after usage, output over the cap) are the same for every provider, and they're only detectable by whoever consumes the stream. Centralising them in `measure_request` means every adapter gets identical validation for free.
