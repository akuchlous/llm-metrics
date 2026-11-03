# Python requires this file name for `python -m llm_metrics`.
# pylint: disable=invalid-name
"""CLI: runs one benchmark workload against the simulated provider and saves it.

Usage: APP_ENV=test python -m llm_metrics [--workload WORKLOAD_ID]

The workload defaults to `workloads.DEFAULT_WORKLOAD_ID`; any id from
`workloads.list_workloads()` can be chosen. An unknown id is refused, with the
list of valid ids, before anything is measured.

This path never calls a paid API: `APP_ENV=prod` is refused by
`config.get_provider`. The only real-provider path is
`python -m llm_metrics.real_smoke`.
"""

import sys

from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import workloads

USAGE = "Usage: python -m llm_metrics [--workload WORKLOAD_ID]"


def _parse_args(args: list[str]) -> workloads.Workload:
    """Returns the selected workload.

    Raises:
        ValueError: For unexpected arguments (message: `USAGE`) or an unknown
            workload id (`workloads.UnknownWorkloadError`, listing valid ids).
    """
    if not args:
        return workloads.get_workload(workloads.DEFAULT_WORKLOAD_ID)
    if len(args) == 2 and args[0] == "--workload":
        return workloads.get_workload(args[1])
    raise ValueError(USAGE)


def main(argv: list[str] | None = None) -> int:
    """Runs one simulated attempt, prints its summary, and saves it.

    Args:
        argv: Command-line arguments without the program name; defaults to
            `sys.argv[1:]`.

    Returns:
        Process exit code: 0 when the attempt was recorded (even if the attempt
        itself failed, because a failure is a valid benchmark result), 2 for a
        usage or configuration error, in which case nothing is measured or
        saved.
    """
    try:
        workload = _parse_args(sys.argv[1:] if argv is None else argv)
        app_env = config.get_app_env()
        provider = config.get_provider(app_env)
        origin = config.get_origin()
    except (ValueError, config.ConfigError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    db_path = config.get_database_url()
    request, results, request_id = benchmark.run_attempt(
        provider, workload, app_env, db_path, origin=origin
    )
    benchmark.print_summary(
        request, results, request_id, db_path, simulated=app_env == "test"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
