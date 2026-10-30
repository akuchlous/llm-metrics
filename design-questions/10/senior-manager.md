# Step 10 — Senior manager

**Step context:** Step 010 added a `requests` table (own UUID identity, provider-reported input/output tokens, requested max output tokens, effective per-1M prices, and unrounded costs) linked to the existing metric observations, a `Usage` event at the end of each stream, a single `pricing.py`, schema version 2, and a `/requests` view of individual calls.

**Question:** Simulated token counts and prices now appear next to realistic-looking dollar figures. How do you stop these numbers being mistaken for real costs, and how do you keep pricing changes safe?

## Answer

Defence in layers, each verified:

- **Everywhere the numbers appear:** the CLI suffixes tokens and cost with "(simulated)". The `/requests` page sits under the TEST / SIMULATED DATA label, with an explicit sentence: simulated tokenizer, simulated prices, "do not match any real provider". The README carries a "Simulated tokens and prices" callout.
- **In the code:** `simulated_token_count` and `PRICES` both carry SIMULATED comments, and `prod` still refuses to run, so no simulated price can be attributed to a production request.
- **Pricing changes are reviewable:** every price lives in one file (`pricing.py`), so a change is one diff that's easy to review. Each request stores the rates it used, so a later price edit can't silently rewrite past costs. A test changes `PRICES` and proves stored costs are unaffected and still reproducible from the stored rates.

## Critique

- **Good:** Labelling at every surface, a single owner file for prices, and history protected by design rather than by process.
- **Weak:** The dollar values have no currency column or source and date for the price ("USD as of when, from where?"), which will matter for real providers. Exports and screenshots of `/requests` carry the label only while it's on screen (the print issue from Step 005 still applies). Nobody "owns" price updates yet.
- **Improve:** When real providers arrive, record the price's source and effective date alongside the rates, name an owner and review cadence for `pricing.py`, and add the currency explicitly. Fix the label's print styling before any of these pages are shared outside the team.
