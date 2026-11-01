"""Makes exactly ONE real, paid OpenAI smoke request and saves it.

Usage: OPENAI_API_KEY=... python -m llm_metrics.real_smoke [--debug]

The low-cost connectivity check: the OpenAI benchmark target
(`targets.OPENAI`) with the fixed smoke workload. It is
`real_benchmark --provider openai --workload smoke.short_text.v2 --real`
without the choices: one attempt (no retries, no loop), stored with
environment "prod", run only when invoked explicitly. It never prints the API
key, the prompt, or the response; `--debug` prints sanitized failure
diagnostics to stderr, never stored.
"""

import sys

from llm_metrics import real_benchmark
from llm_metrics import targets
from llm_metrics import workloads

# One short harmless prompt with a 64-token cap. Fixed on purpose: this command
# is the connectivity check, not a way to run the larger benchmark workloads.
WORKLOAD = workloads.SMOKE_SHORT_TEXT_V2


def main(argv: list[str] | None = None) -> int:
    """Runs the smoke command; see `real_benchmark.run` for the exit codes.

    Args:
        argv: Command-line arguments without the program name; defaults to
            `sys.argv[1:]`. Only `[]` and `["--debug"]` are accepted.
    """
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--debug"]):
        print(
            "Usage: python -m llm_metrics.real_smoke [--debug]", file=sys.stderr
        )
        return 2
    return real_benchmark.run(targets.OPENAI, WORKLOAD, args == ["--debug"])


if __name__ == "__main__":
    sys.exit(main())
