# Step 02 — Lead engineer

**Step context:** Step 002 added `./run.sh`: one command that creates/reuses `.venv` (without pip), runs all tests, and only if they pass runs the TTFT measurement.

**Question:** Why does `run.sh` create the venv with `--without-pip`, and what does that cost?

## Answer

On Debian, which ChromeOS's Linux container uses, `python3 -m venv .venv` fails unless the `python3-venv` package is installed, because the standard library's `ensurepip` is split out. The project has zero third-party dependencies, so pip isn't needed inside the venv. `--without-pip` makes `./run.sh` work on a stock Chromebook with no `sudo apt install`. The venv still gives a stable, project-local interpreter path (`.venv/bin/python`), which `run.sh` calls directly instead of `source activate` (D013).

The cost is a known debt: the first third-party dependency forces a change. Either require `python3-venv` and `ensurepip`, or bootstrap pip another way, and update the README and `run.sh` together. Developers used to `pip install` into `.venv` will also find no pip.

## Critique

- **Good:** It solved a real first-run failure on the target machine, and the owner confirmed `./run.sh` worked on a real Chromebook. The debt is recorded (D012), not hidden.
- **Weak:** Today the venv adds little isolation, because there's nothing to isolate. It's mostly ceremony for future-proofing, which the project otherwise avoids.
- **Improve:** Keep it, since it costs about 1 s once. When the first dependency arrives, make the change in the same step that adds the dependency, and add a test that checks `.venv/bin/python -m pip` works.
