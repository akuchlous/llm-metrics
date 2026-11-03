# Step 018d — Principal engineer

**Step context:** Step 018d replaced `alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))` with a connection passed via `config.attributes["connection"]`, and made PostgreSQL with orphan tables fail closed instead of silently stamping.

**Question:** What are the concrete attack surfaces that the URL-in-config approach created, and how does passing the connection eliminate them?

## Answer

Setting `sqlalchemy.url` as a config string created three risks. First, `ConfigParser` (Python's INI parser, used inside Alembic's `Config`) interprets `%` followed by a parenthesised key as a variable substitution marker. A password that contains `%` — common in URL-encoded passwords such as `%40` for `@` or `%25` for `%` itself — would raise `InterpolationSyntaxError` before any SQL ran, or silently produce a wrong value if the pattern happened to match a key. Second, Alembic's config logging (at DEBUG level) records the key-value pairs in the config; a `sqlalchemy.url` entry at DEBUG would write the full URL with credentials to the log. Third, if `Config` serialized the URL into an error message, credentials would appear in exception context. Passing the connection via `config.attributes["connection"]` eliminates all three: no URL string is ever stored in the config object, so there is nothing for `ConfigParser` to interpolate, log, or serialize.

## Critique

- **Good:** The connection-via-attributes pattern is the approach Alembic's own documentation recommends for programmatic usage; it is not a workaround.
- **Weak:** The fix depends on `env.py`'s `config.attributes.get("connection")` check always being reached. If `env.py` were replaced or the offline path were taken instead, the URL fallback would fail because `sqlalchemy.url` is no longer set. The code has no explicit guard against this.
- **Improve:** Add a comment in `env.py` that the online path always expects `config.attributes["connection"]` to be set by `_ensure_schema()`; add a test that the config object has no `sqlalchemy.url` key after `_ensure_schema()` runs. This makes the invariant explicit and machine-checked.
