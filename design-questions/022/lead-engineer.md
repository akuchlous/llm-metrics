# Lead engineer — Step 022: GCS-backed OpenAI pilot

**Step context:** Step 022 added an explicitly selected GCS results backend to `real_benchmark` (`LLM_METRICS_RESULTS_BACKEND=gcs`; gcp origin and OpenAI only). It checks configuration before the key, runs a real create/read/no-overwrite storage preflight before the paid request, fixes the attempt id before the request and exits 3 if the record is not confirmed durable. It added a storage-only `gcs_smoke` command. In the cloud, the job service account proved storage with no provider key (Phase A), then one paid `gpt-6-luna` attempt was stored as an immutable `prod` object and independently verified (Phase B). The key was detached afterwards.

---

## Question

GCS mode runs a storage *probe* (create, read, attempted overwrite, re-read) before the paid call, instead of checking IAM with `testIamPermissions`. And it allocates the attempt id before the request rather than at save time. Justify both, and explain what the 403-vs-412 handling in `GcsObjectStore.create` protects against.

## Answer

**Why a probe, not an IAM check.** An IAM check proves that a permission is granted. It doesn't prove that:
- the bucket exists and is reachable from the job's network
- Application Default Credentials work in the container
- the client library uploads successfully
- the server actually enforces create-only

`object_results.preflight` exercises exactly the operations `write_record` will use, under `<prefix>/v1/preflight/`, outside the record namespace. In the cloud, Phase A ran it as the real job service account, and so did the paid run (probe `fb9bb9f2…`), before the request.

Any preflight failure exits 2 with "No request was made", printing only the error class. Offline tests cover a denied create, a transient error, corrupt read-back, an overwriting store and a client constructor failure, each with zero provider calls.

**Why the id comes before the request.** `attempt_id` is printed in the announcement, so the job log identifies an attempt even if the process dies after the provider bills it. In the paid run, the announced `e00ee56c…` is the record id and the object name.

`recorded_at` is still taken after measurement, matching the SQL path's "save time" semantics.

**403 vs 412.** The job service account has `objectCreator` + `objectViewer`, so it has no permission to replace objects. For an existing name, GCS may answer a create-only upload with 403 instead of 412. Treating every 403 as "exists" would hide a missing grant. So `create` reads the object: if it exists, the 403 is reported as `ObjectExistsError`; otherwise it stays `PermissionDeniedError`. Both branches are tested through the real client over a fake transport.

## Critique

**Good:** the gate tests real behaviour, the refusal paths are exhaustive and tested, and the IAM grant is minimal (bucket-scoped, no delete).

**Weak / missing:**
- Which status code real GCS returned for the refused creates wasn't observed; no audit log captured it.
- Each run leaves a 124-byte probe and spends extra Class A operations.

**Stronger:**
- Enable data-access logs once, to observe 412 vs 403.
- Add a lifecycle rule that deletes `*/v1/preflight/` objects after 7 days.
