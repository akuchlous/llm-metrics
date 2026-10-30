# Step 02 — Director

**Step context:** Step 002 added `./run.sh`: one command that creates/reuses `.venv` (without pip), runs all tests, and only if they pass runs the TTFT measurement.

**Question:** The reference developer machine is a Chromebook. What are the implications for an open-source project?

## Answer

It's a deliberate constraint that drives good outcomes: no Docker, no `make`, no system packages, no paid tooling, just Python 3 and bash. The result is a project anyone can clone and run in one command on cheap hardware, which matters for an open benchmark. Reproducibility is part of credibility, and "anyone can rerun this" is a strong claim.

Implications to manage:

- **Supported platforms must be explicit.** Only Linux with bash is tested. macOS probably works; Windows (outside WSL) doesn't. Saying "works anywhere" would be an overclaim.
- **Contributor expectations.** Some contributors expect Docker or `pip install -e .`. The project intentionally has neither (D003, D012), which needs explaining.
- **Constraints compound.** Later choices (no web framework, no pip) trace back to this one, so revisiting it later is expensive.

## Critique

- **Good:** It kept the stack radically simple, and it was validated on real hardware (the owner's Chromebook ran `./run.sh` and the dashboard successfully).
- **Weak:** The platform support statement is implicit ("Linux/Chromebook Linux") with no CI matrix, so regressions on other platforms would go unnoticed.
- **Improve:** Publish a supported-platforms line in the README. Add macOS to CI if contributors need it. Treat "one command on a Chromebook" as a feature to protect, with a test, not an accident.
