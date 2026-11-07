"""Plan-only preparation of a new bounded 24-hour collector pilot (027c).

Usage:
    python -m llm_metrics.pilot_plan --start YYYY-MM-DDTHH:MM:SSZ
        [--now YYYY-MM-DDTHH:MM:SSZ] [--runs FILE] [--analytics FILE]
        [--json]

Prints the exact proposed window, its 96 slot times, the existing resources
it reuses, the bounded changes a launch would make, prerequisites, a cost
estimate and the stop/audit/rollback commands. It only reads local files:
it runs no gcloud command, touches no credential, schedule, GCS object or
Cloud Run job, and makes no provider call. There is no execute mode: a
launch is the existing Step 023 `activate` stage, run by an operator under
a separate, explicit Approval C.

Refusals (exit 1): a start that is not a UTC quarter hour, in the past or
less than 30 minutes ahead, more than 14 days ahead, overlapping (with the
late limit) or repeating a registered run, or a previous run that is not
yet closed (stopped and audited). Every window is exactly 96 slots (24 h),
from the collector's own `Policy`.

Run identity: `<request profile>/<policy start>`. Claims are named by slot
time, so two non-overlapping windows never share a claim, and
`record_analytics`/`pilot_series` select one window with `--start` (the
policy start) and `--end`, so pilots are compared without mixing records.
"""

import argparse
import datetime
import json
import pathlib
import sys

from llm_metrics import scheduled_collector as sc

RUNS_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts/gcp/pilot_runs.json"
)
MIN_LEAD = datetime.timedelta(minutes=30)
MAX_LEAD = datetime.timedelta(days=14)
SCRIPT = "bash scripts/gcp/023_collector.sh"
_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_UTC = datetime.timezone.utc


class PlanError(Exception):
    """The proposed run is refused."""


def parse(text: str) -> datetime.datetime:
    try:
        moment = datetime.datetime.strptime(text, _FORMAT).replace(tzinfo=_UTC)
    except (TypeError, ValueError):
        raise PlanError("Times must be UTC YYYY-MM-DDTHH:MM:SSZ.") from None
    return moment


def run_id(start: datetime.datetime) -> str:
    return f"{sc.TARGET.profile_id}/{start.strftime(_FORMAT)}"


def load_runs(path: pathlib.Path) -> list[dict]:
    data = json.loads(pathlib.Path(path).read_text("utf-8"))
    if data.get("schema_version") != "llm-metrics.pilot-runs.v1":
        raise PlanError("Not an llm-metrics.pilot-runs.v1 registry.")
    return data["runs"]


def check(
    start: datetime.datetime, now: datetime.datetime, runs: list[dict]
) -> sc.Policy:
    """The validated policy for `start`.

    Raises:
        PlanError: Describing the refusal.
    """
    if start.minute % 15 or start.second or start.microsecond:
        raise PlanError("START must be a UTC quarter hour (:00/:15/:30/:45).")
    if start < now + MIN_LEAD:
        raise PlanError(
            "START must be at least 30 minutes in the future, so the plan"
            " can be reviewed and approved before the first slot."
        )
    if start > now + MAX_LEAD:
        raise PlanError("START is more than 14 days ahead; plan closer to it.")
    try:
        policy = sc.Policy(start, start + sc.WINDOW)
    except sc.CollectorConfigError as error:
        raise PlanError(str(error)) from None
    for run in runs:
        other_start, other_end = parse(run["start"]), parse(run["expires"])
        if other_start == start:
            raise PlanError(f"Run {run['run_id']} already used this start.")
        if start < other_end + sc.LATE_LIMIT and other_start < policy.expires:
            raise PlanError(
                f"Window overlaps run {run['run_id']} (including the"
                " late-record limit)."
            )
        if not run.get("closed"):
            raise PlanError(
                f"Run {run['run_id']} is not closed: run the approved `stop`"
                " and the post-window audit first, then mark it closed."
            )
    return policy


def cost_estimate(summary: dict | None) -> dict:
    """Model API cost for 96 requests from a reviewed pilot summary."""
    if summary is None:
        return {
            "expected_usd": None,
            "upper_bound_usd": None,
            "basis": "No reviewed summary given (--analytics); no estimate.",
        }
    cost, tokens = summary["cost_usd"], summary["tokens"]
    priced = cost["priced_successes"]
    prices = summary["request_settings"]["prices_per_1m"]
    max_output = max(summary["request_settings"]["requested_max_output_tokens"])
    if not priced or len(prices) != 1 or cost["known_total_cost"] is None:
        return {
            "expected_usd": None,
            "upper_bound_usd": None,
            "basis": "Summary has no single price or no priced successes.",
        }
    price = prices[0]
    per_request = cost["known_total_cost"] / priced
    mean_input = tokens["input_tokens"] / priced
    bound = (mean_input * price["input"] + max_output * price["output"]) / 1e6
    return {
        "expected_usd": round(per_request * sc.MAX_SLOTS, 4),
        "upper_bound_usd": round(bound * 1.5 * sc.MAX_SLOTS, 4),
        "basis": (
            f"Expected: mean estimated cost of {priced} priced successes"
            f" (${per_request:.6f}) x {sc.MAX_SLOTS}. Bound: mean input"
            f" tokens x 1.5 and the {max_output}-token output cap at the"
            " stored list prices. Estimates from token counts, not billing."
        ),
    }


def plan(
    start: datetime.datetime,
    now: datetime.datetime,
    runs: list[dict],
    summary: dict | None = None,
) -> dict:
    policy = check(start, now, runs)
    begin, end = sc.format_utc(policy.start), sc.format_utc(policy.expires)
    return {
        "plan_only": True,
        "run_id": run_id(policy.start),
        "window": {"start": begin, "expires": end, "slots": sc.MAX_SLOTS},
        "slot_times": [sc.format_utc(s) for s in policy.slots()],
        "target": {
            "provider": sc.TARGET.provider,
            "model": sc.TARGET.model,
            "request_profile": sc.TARGET.profile_id,
            "workload": sc.WORKLOAD_ID,
            "origin": f"{sc.ORIGIN_CLOUD}/us-central1",
            "cadence": "one request per 15-minute slot, no retries",
        },
        "reuses": [
            "Cloud Run job llm-metrics-collector (same image, unchanged code)",
            "Cloud Scheduler job llm-metrics-collector-15m (*/15, UTC)",
            "Service accounts llm-metrics-collector@ and"
            " llm-metrics-scheduler@",
            "Results bucket (records under attempts/v1/requests/prod/,"
            " claims under attempts/v1/claims/prod/)",
            "Secret OPENAI_API_KEY (reference only; never read here)",
        ],
        "launch_changes": [
            "Grant the collector SA secretAccessor on OPENAI_API_KEY",
            f"Set job env LLM_METRICS_COLLECTOR_MODE=prod,"
            f" LLM_METRICS_COLLECTOR_START={begin},"
            f" LLM_METRICS_COLLECTOR_EXPIRES={end}; attach the key reference",
            "Enable the missed-slot alert policy; resume the scheduler",
        ],
        "prerequisites": [
            "Previous run closed: `stop` run and post-window audit reviewed",
            "Explicit Approval C naming this run_id, START and the cost cap",
            "Clean pushed HEAD; job image digest unchanged since the review",
            "Operator gcloud login for project llm-metrics-513617",
        ],
        "cost": {
            "model_api": cost_estimate(summary),
            "gcp": "Cloud Run job, Scheduler, Secret Manager and GCS usage"
            " for 96 runs are expected to stay within free tiers (not"
            " verified against billing).",
            "max_paid_requests": sc.MAX_SLOTS,
        },
        "commands": {
            "launch_after_approval_c": f"{SCRIPT} activate {begin}",
            "audit_during_or_after": f"WORK_DIR=/tmp/audit"
            f" TOOL_IMAGE=llm-metrics-tool {SCRIPT} audit {begin}",
            "stop_after_window_or_emergency": f"{SCRIPT} stop",
            "rollback": f"{SCRIPT} stop  (pauses the scheduler and detaches"
            " the key; records already written stay immutable)",
            "analytics_after_window": "python -m llm_metrics.record_analytics"
            f" --input MIRROR --start {begin} --end {end}"
            f" --collector-policy-start {begin} ...",
        },
        "after_run": "Add this run to scripts/gcp/pilot_runs.json with"
        " closed=false at launch; set closed=true after stop and audit.",
    }


def _text(result: dict) -> str:
    lines = [
        "PLAN ONLY: nothing was changed, no cloud or provider call was made.",
        f"Run id:   {result['run_id']}",
        f"Window:   {result['window']['start']} to"
        f" {result['window']['expires']} ({result['window']['slots']} slots)",
        f"Target:   {result['target']['provider']} {result['target']['model']}"
        f" / {result['target']['request_profile']} /"
        f" {result['target']['workload']} from {result['target']['origin']};"
        f" {result['target']['cadence']}",
        "Slots:    "
        + ", ".join(result["slot_times"][:4])
        + ", ..., "
        + result["slot_times"][-1],
        "Reuses:",
        *(f"  - {item}" for item in result["reuses"]),
        "Launch would change (only after Approval C):",
        *(f"  - {item}" for item in result["launch_changes"]),
        "Prerequisites:",
        *(f"  - {item}" for item in result["prerequisites"]),
        "Cost:",
        "  - Model API, expected:"
        f" {result['cost']['model_api']['expected_usd']}"
        f" USD; upper bound: {result['cost']['model_api']['upper_bound_usd']}"
        " USD",
        f"    ({result['cost']['model_api']['basis']})",
        f"  - GCP: {result['cost']['gcp']}",
        f"  - At most {result['cost']['max_paid_requests']} paid requests.",
        "Commands:",
        *(f"  {k}: {v}" for k, v in result["commands"].items()),
        f"After the run: {result['after_run']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.pilot_plan", allow_abbrev=False
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--now", help="override the current UTC time")
    parser.add_argument("--runs", default=str(RUNS_PATH))
    parser.add_argument("--analytics", help="reviewed pilot summary JSON")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="always refused: launching needs Approval C and `activate`",
    )
    options = parser.parse_args(argv)
    try:
        if options.execute:
            raise PlanError(
                "This command only plans. Launching is the Step 023"
                " `activate` stage, under a separate explicit Approval C."
            )
        now = (
            datetime.datetime.now(_UTC).replace(microsecond=0)
            if options.now is None
            else parse(options.now)
        )
        summary = (
            None
            if options.analytics is None
            else json.loads(pathlib.Path(options.analytics).read_text("utf-8"))
        )
        result = plan(
            parse(options.start), now, load_runs(options.runs), summary
        )
    except PlanError as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2) if options.json else _text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
