# Lead engineer — Step 024: offline analytics from immutable records

**Step context:** Step 024 added `llm_metrics.record_analytics`, an offline, read-only command that reads a local mirror of the immutable `llm-metrics.attempt.v1` GCS records (prod only), selects one exactly filtered population (provider, model, profile, workload, origin, UTC `[start, end)`), validates every candidate file with `object_results.decode_record`, and writes a canonical, create-only `llm-metrics.analytics.v1` summary. Slot completeness is reported only from collector claims via `collector_audit.audit`. It was tested on committed synthetic fixtures; no cloud or provider access was used.

---

## Question

A mirror can be incomplete, hand-edited or partly corrupted. Walk through how `record_analytics` makes sure such input never produces a plausible-looking summary, and how the output stays reproducible.

## Answer

**Input is validated before anything is computed:**
- The prefix is checked with `object_results.ResultTarget`, so `../` and reserved roots are refused.
- `os.walk(followlinks=False)` rejects any symlink under the prefix and stops above 200,000 entries.
- `requests/prod/` may hold only `YYYY-MM-DD` directories. Each day directory may hold only `<32 hex>.json` files of at most 64 KiB.
- Every file in the scanned days goes through `decode_record(data, expected_name=...)`, including files that the filter later excludes. That one call enforces UTF-8 JSON, no duplicate keys, no NaN, canonical bytes, schema v1 (outcome consistency, null-not-zero) and the object name. A `test` record copied into `prod/`, or a record moved to another date, fails the name check.
- Duplicate provider request ids among selected records fail the run, without echoing the id.
- A record with the selected profile but another provider/model raises "Mixed population" instead of being dropped.
- Zero selected records raises an error, because an empty summary would look like a measurement.

**Output is reproducible and create-only:**
- There are no wall-clock fields. Records are sorted by `(recorded_at, attempt_id)`, costs are summed with `math.fsum`, and JSON is canonical (sorted keys, compact, `allow_nan=False`).
- The file is written to a temp file, fsynced, then `os.link`-ed into place, which the OS refuses if the name exists. Identical existing bytes count as "Unchanged". Different bytes, a symlink, or a path inside the mirror are refused.
- Tests cover each of these (31 tests), including a byte-identical second run.

## Critique

**Good:** all record validation is delegated to the one schema owner, so there is no second definition to drift. Refusals are tested by message, and nothing is written on a refusal.

**Weak / missing:**
- Only day directories that overlap the window are decoded. A corrupt file on another day is not detected by this run.
- A hard link (not a symlink) to an outside file is not detected. It is harmless for evidence, because the bytes are what get hashed, but it is undocumented.
- `os.link` needs a filesystem with hard links. It is not tested on network or FUSE mounts.

**Stronger:** an optional `--verify-all-days` flag, and a test that runs the CLI against a real `gcloud storage cp` layout produced from the bucket's listing.
