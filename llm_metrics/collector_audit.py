"""Read-only audit of a scheduled-collector window: claims vs records.

Usage:
    python -m llm_metrics.collector_audit --start YYYY-MM-DDTHH:MM:SSZ
        --expires YYYY-MM-DDTHH:MM:SSZ (--local DIR | --bucket B)
        [--prefix attempts] [--mode prod|dryrun] [--region us-central1]
        [--now YYYY-MM-DDTHH:MM:SSZ]

`--local DIR` audits a downloaded mirror, e.g. after
    gcloud storage cp -r gs://BUCKET/attempts/v1 DIR/attempts/
so the audit needs no credentials of its own; `--bucket` reads GCS directly
with Application Default Credentials (list + get only).

For every slot of the policy that has begun (up to `--now`, default the
current time, and never past the expiry) it reports exactly one state:
- recorded_success / recorded_failure: claim and a valid record with the
  claim's attempt id (failure = recorded provider failure, nulls intact);
- claim_without_record: a claim exists but no record (exit 3, crash after the
  request, or a refusal after claiming: claim_failed/clock_skew/expired);
- missing: no claim at all (scheduler did not deliver, the job failed before
  claiming, late start, or configuration refusal).
It also flags records in the window that no claim accounts for, and claims
outside the policy. Duplicate trigger deliveries never create a second claim
or record; they appear only as `duplicate_skip` events in the job logs.

Prints counts and per-slot problems only (no record payloads). Exit code 0
when every begun slot is recorded and nothing is unaccounted for, else 1;
2 for bad arguments.
"""

import collections
import datetime
import json
import pathlib
import sys

from llm_metrics import object_results
from llm_metrics import scheduled_collector as sc

_USAGE = __doc__.split("\n\n")[1]


class LocalDirStore:
    """Read-only `ObjectStore`-like view of a downloaded bucket mirror."""

    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)

    def read(self, bucket: str, name: str) -> bytes | None:
        del bucket  # the mirror holds one bucket
        path = self.root / name
        return path.read_bytes() if path.is_file() else None

    def list_names(self, bucket: str, prefix: str) -> list[str]:
        del bucket
        return sorted(
            str(p.relative_to(self.root))
            for p in self.root.rglob("*")
            if p.is_file() and str(p.relative_to(self.root)).startswith(prefix)
        )


def audit(
    store,
    target: object_results.ResultTarget,
    policy: sc.Policy,
    *,
    mode: str,
    origin: tuple[str, str],
    now: datetime.datetime,
) -> dict:
    """Returns the audit report (see the module docstring)."""
    environment = "prod" if mode == "prod" else "test"
    claims_root = sc.claim_name(target, mode, origin, policy.start).rsplit(
        "/", 2
    )[0]
    claims = {}
    stray_claims = []
    for name in store.list_names(target.bucket, claims_root + "/"):
        try:
            data = json.loads(store.read(target.bucket, name))
            slot = sc.parse_utc(data["slot"], "slot")
        except (TypeError, ValueError, KeyError):
            stray_claims.append(name)
            continue
        if policy.allows(slot) and data.get("kind") == sc.CLAIM_KIND:
            claims[slot] = data["attempt_id"]
        else:
            stray_claims.append(name)

    records = {}
    invalid_records = []
    days = sorted({s.strftime("%Y-%m-%d") for s in policy.slots()} | {
        (policy.expires).strftime("%Y-%m-%d")
    })  # fmt: skip
    for day in days:
        prefix = f"{target.prefix}/v1/requests/{environment}/{day}/"
        for name in store.list_names(target.bucket, prefix):
            try:
                record = object_results.read_record(store, target, name)
            except object_results.ResultStoreError:
                invalid_records.append(name)
                continue
            records[record["attempt_id"]] = record

    begun = [s for s in policy.slots() if s <= now]
    states = collections.Counter()
    problems = []
    claimed_ids = set()
    for slot in begun:
        attempt_id = claims.get(slot)
        if attempt_id is None:
            state = "missing"
        else:
            claimed_ids.add(attempt_id)
            record = records.get(attempt_id)
            if record is None:
                state = "claim_without_record"
            elif record["request"]["outcome"] == "success":
                state = "recorded_success"
            else:
                state = "recorded_failure"
        states[state] += 1
        if state not in ("recorded_success",):
            problems.append(
                {
                    "slot": sc.format_utc(slot),
                    "state": state,
                    "attempt_id": attempt_id,
                }
            )
    unclaimed = sorted(
        attempt_id
        for attempt_id, record in records.items()
        if attempt_id not in claimed_ids
        and policy.start.strftime("%Y-%m-%dT%H:%M")
        <= record["recorded_at"]
        < (policy.expires + sc.LATE_LIMIT).strftime("%Y-%m-%dT%H:%M")
    )
    failures = collections.Counter(
        records[claims[s]]["request"]["outcome"]
        for s in begun
        if s in claims and claims[s] in records
        and records[claims[s]]["request"]["outcome"] != "success"
    )  # fmt: skip
    return {
        "policy": policy.as_dict(),
        "mode": mode,
        "audited_until": sc.format_utc(min(now, policy.expires)),
        "expected_slots_so_far": len(begun),
        "claimed": sum(1 for s in begun if s in claims),
        "states": dict(states),
        "failed_outcomes": dict(failures),
        "problems": problems,
        "records_without_claim": unclaimed,
        "invalid_records": invalid_records,
        "claims_outside_policy": stray_claims,
    }


def _parse(argv):
    options = {}
    args = list(argv)
    while args:
        key = args.pop(0)
        if not key.startswith("--") or not args or key in options:
            raise ValueError(_USAGE)
        options[key] = args.pop(0)
    allowed = {"--start", "--expires", "--local", "--bucket", "--prefix",
               "--mode", "--region", "--now"}  # fmt: skip
    if set(options) - allowed or ("--local" in options) == (
        "--bucket" in options
    ):
        raise ValueError(_USAGE)
    return options


def main(argv: list[str] | None = None) -> int:
    try:
        options = _parse(sys.argv[1:] if argv is None else argv)
        policy = sc.Policy(
            sc.parse_utc(options.get("--start"), "--start"),
            sc.parse_utc(options.get("--expires"), "--expires"),
        )
        now = (
            sc.parse_utc(options["--now"], "--now")
            if "--now" in options
            else datetime.datetime.now(datetime.timezone.utc)
        )
        mode = options.get("--mode", "prod")
        if mode not in sc.MODES:
            raise ValueError("--mode must be prod or dryrun")
        # A local mirror has no bucket; the placeholder only satisfies the
        # target's validation and is never contacted.
        target = object_results.ResultTarget(
            options.get("--bucket", "local-mirror"),
            options.get("--prefix", "attempts"),
        )
    except (ValueError, object_results.ResultStoreError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    if "--local" in options:
        store = LocalDirStore(pathlib.Path(options["--local"]))
    else:
        store = object_results.GcsObjectStore()
    report = audit(
        store,
        target,
        policy,
        mode=mode,
        origin=(sc.ORIGIN_CLOUD, options.get("--region", "us-central1")),
        now=now,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    clean = (
        report["states"].get("recorded_success", 0)
        + report["states"].get("recorded_failure", 0)
        == report["expected_slots_so_far"]
        and not report["records_without_claim"]
        and not report["invalid_records"]
    )
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
