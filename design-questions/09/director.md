# Step 09 — Director

**Step context:** Step 009 added output throughput (`output_chunks_per_s` = (non-empty chunks − 1) ÷ (last − first chunk time)) to the single-pass measurement, renamed the stored `value_ms` column to `value` with the first versioned schema upgrade, and added the metric to the dashboard with correct units.

**Question:** The industry compares LLM providers on "tokens per second". You shipped "chunks per second". Is that a credibility problem or a strength?

## Answer

It's a strength, as long as it's communicated well. The provider interface yields text chunks, not tokenizer tokens. Calling them tokens would be a false claim: one chunk can be part of a token, one token, or several tokens, depending on the provider. An independent benchmark's main asset is that its numbers mean exactly what they say, so the metric is named for what is actually counted (`output_chunks_per_s`), defined precisely (generation rate after the first chunk), and protected (D034: a real provider must keep the meaning or use a new name).

What this enables now: on the same provider and workload, chunks/s trends are valid for detecting slowdowns, and total latency can be read alongside how much was produced. What it doesn't enable: comparisons *across* providers, because chunk sizes differ. That needs a provider-reported or tokenizer-based `output_tokens_per_s`, with a documented token definition.

## Critique

- **Good:** It refuses to overclaim, names the metric for its actual unit, and documents the path to a comparable metric. That's credibility-preserving behaviour.
- **Weak:** "Chunks/s" is unfamiliar to the audience who will read the dashboard, and nothing on the page explains it or warns that it isn't comparable across providers. Throughput percentiles also use p50/p95/p99, but for a higher-is-better metric the slow tail (p5/p1) is what users feel.
- **Improve:** Add a one-line definition and a "not comparable across providers" note next to throughput on the page. When real providers arrive, add `output_tokens_per_s` from provider usage data, alongside chunks/s rather than replacing it. Report low percentiles for throughput.
