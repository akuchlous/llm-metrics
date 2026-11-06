# Senior manager — Step 020: guarded second OpenAI cloud pilot

**Step context:** Step 020 replaced the pre-guard Cloud Run Job image with an immutable, digest-pinned build containing the 018h fail-closed cloud-origin database guard, proved the guard in the cloud with the model key detached (exit 2, "No request was made"), then under a separate approval ran exactly one OpenAI `gpt-6-luna` measurement into a temporary Cloud SQL PostgreSQL 17 instance, exported and independently verified a checksummed backup, and tore the database down.

---

## Question

This step mixed free, reversible work with billable, partly irreversible cloud actions and one paid API call. How was delivery risk controlled — approvals, sequencing, teardown — and what would you change before this becomes routine?

## Answer

**Approval structure.** Two in-session gates, each preceded by an exact, scripted plan and cost:
- **Approval A** ("Approve A", 14:29Z): build, deploy by digest, *one* negative execution — explicitly excluding SQL, key restoration and paid calls.
- **Approval B** ("Approve B", 14:38Z): one temporary Cloud SQL, DB secret, key restoration, *one* paid request, export, verification, teardown — with the rule that unverified backup means *no* deletion and a billing warning.

Earlier authorisations (018f/018g) were not reused.

**Sequencing as code.** `scripts/gcp/020_phase_a.sh` and `020_phase_b.sh` were committed *before* execution, so what ran is reviewable in Git. Each stage was run separately and its output inspected before the next (e.g. saved job spec checked before execute; 0 rows checked before the paid call). No stage retried on its own.

**Environment change handled explicitly.** The plan assumed Cloud Shell; mid-step the user installed `gcloud` locally. The step adapted (explicit `--project/--region` everywhere, tokens via env vars, secrets in 0600 files) and recorded the change instead of hiding it.

**Outcome.** One measurement, backup verified, instance and secret deleted 18 minutes after creation; total spend < $0.01.

## Critique

**Good:** the irreversible step (deleting the only database) was gated on objective evidence; the plan named what was *not* approved; every cloud mutation is traceable to a timestamped stage.

**Weak / missing:** approval is a chat phrase — there is no technical control (e.g. IAM conditions or a deny policy) preventing an operator from executing the job with credentials outside the process. The local machine now holds an owner-level `gcloud` credential. Stage outputs were inspected by the same agent that ran them.

**Stronger:** before routine use, add a technical spend guard (key with OpenAI project budget, or a job that requires a one-time token), revoke or scope down local credentials after each session, and have a second reviewer (ChatGPT/human) sign off the stage log, not only the plan.
