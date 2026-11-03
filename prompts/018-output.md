# Step 018 — Live pilot output record

## OpenAI

| Field | Value |
|---|---|
| Date/time | 2026-11-03 |
| Provider | openai |
| Exact model | `gpt-6-luna` |
| Request-profile id | `openai.gpt-6-luna.v1` |
| Workload id | `interactive-chat-v1` |
| Requested output cap | 300 tokens |
| Origin | local / unknown |
| Outcome | success |
| llm-metrics request id | `9453a857d6c140f08404eeda9ad168d1` |
| Provider request id | `req_b410a1a919f64351bd57cd085462fd93` |
| Input tokens | 1795 |
| Cached input tokens | 0 (reported zero; cache policy disabled) |
| Output tokens | 277 |
| TTFT | 4357.7 ms |
| Total latency | 6753.8 ms |
| Output tokens/sec | 119.0 |
| Total cost | $0.000318 |
| Effective input rate | $0.10 / 1M |
| Effective output rate | $0.50 / 1M |
| Effective cached input rate | $0.01 / 1M (applied only to reported cached tokens; none here) |
| Account/setup issues | None. New API key was created before the run (prior key revoked after it was accidentally exposed in chat). |
| Code fix required | No |
| Live API difference from Step 016 fixtures | None observed. Streaming, usage fields, and request-id source all matched fixtures. |
| Paid calls | 1 (initial validation) |

---

_Anthropic, Google, and xAI results to follow._
