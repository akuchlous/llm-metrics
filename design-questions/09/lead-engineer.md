# Step 09 — Lead engineer

**Step context:** Step 009 added output throughput (`output_chunks_per_s` = (non-empty chunks − 1) ÷ (last − first chunk time)) to the single-pass measurement, renamed the stored `value_ms` column to `value` with the first versioned schema upgrade, and added the metric to the dashboard with correct units.

**Question:** Define the throughput formula precisely. Why that denominator, and how do you test timing code like this deterministically?

## Answer

`output_chunks_per_s = (N − 1) / (t_last − t_first)`, where N is the number of **non-empty** items from `stream()`, and `t_first` and `t_last` are the `perf_counter()` readings when the first and last non-empty items arrived.

Why that denominator:

- **N chunks span N − 1 intervals.** Dividing N by (t_last − t_first) overstates the rate. With 5 chunks 20 ms apart, the span is 80 ms: 4/0.08 = 50 chunks/s is correct, while 5/0.08 = 62.5 isn't.
- **Excluding everything before the first chunk** keeps TTFT (queueing, prefill) out of throughput. 5 ÷ total latency would mix the two.
- **Undefined cases return nothing:** N < 2, or t_last == t_first. No row is stored, rather than 0 or infinity, which would corrupt percentiles.

Testing: `time.perf_counter` is patched with `side_effect=[...]`, giving one reading for the start, one per item, and one at the end. That makes the values exact (`assertAlmostEqual(values["output_chunks_per_s"], 50.0)`) with no sleeping. Separate tests cover empty items (`["", "a", "", "b"]` gives 25 chunks/s), a single chunk, only-empty items, and identical timestamps.

## Critique

- **Good:** The formula and its edge cases are explicit in the docstring, D034 and the tests. The controlled-clock tests are exact and fast, which improves on the sleep-based Step 008 tests.
- **Weak:** The clock-mocking tests depend on the exact *number* of `perf_counter()` calls. Adding one more reading inside `measure_request` breaks them with a confusing `StopIteration`. The sleep-based tests remain for TTFT and total latency, so the suite now uses two timing-test styles.
- **Improve:** Inject the clock (`measure_request(provider, prompt, clock=time.perf_counter)`) instead of patching the module, so tests pass a fake clock explicitly and failures are clearer. Then convert the remaining sleep-based assertions to that style.
