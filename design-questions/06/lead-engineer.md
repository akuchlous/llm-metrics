# Step 06 — Lead engineer

**Question:** Why nearest-rank percentiles, and what was the bug risk in implementing them?

## Answer

Nearest-rank: sort the values and take rank ⌈p·n/100⌉ (1-based). Reasons:

- It always returns an **observed** latency; it never reports a number that wasn't measured.
- It's deterministic, independent of input order, and defined for n = 1.
- It's easy to verify by hand. On the live dashboard: 169 values gives p99 rank ⌈167.31⌉ = 168, the second-largest value, 472.3 ms.

The bug risk was floating point: `math.ceil(0.07 * 100)` is 8, because `0.07*100 = 7.000000000000001`. The implementation uses integer arithmetic, `(p * n + 99) // 100`, and a test checks p = 1, 7, 50, 95, 99 and 100 on 1..100. Inputs are validated: an empty list raises an error, and so does p outside 1..100.

## Critique

- **Good:** A pure function with no HTML or storage (`percentiles.py`), tested on known datasets and on order independence. It avoids a subtle off-by-one that many implementations ship with.
- **Weak:** Nearest-rank is coarse for small samples: with fewer than 100 values, p99 is simply the maximum, so a single outlier sets it. Many other tools interpolate, so our numbers aren't directly comparable with theirs without knowing the method.
- **Improve:** Show `n` next to the percentiles, and hide or mark p99 when n < 100. The method name is already on the page; keep it there.
