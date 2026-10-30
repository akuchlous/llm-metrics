# Coding Guidelines

These guidelines apply to all new and modified code in `llm-metrics`. They are intentionally written so both human engineers and AI coding agents can follow the same expectations.

## Guiding standard

Use the Google Python Style Guide as the primary style reference where it fits this repository, while preferring the repository's existing conventions when changing established public behavior. The goal is not mechanical conformity for its own sake; the goal is production-quality code that is correct, secure, readable, testable, and easy to maintain.

Priority order:

1. Correctness and data integrity.
2. Security and privacy.
3. Readability and maintainability.
4. Simple, explicit design.
5. Consistency with existing repository contracts.
6. Conciseness only when it does not reduce clarity.

Do not make unrelated style-only rewrites while implementing a focused step.

## Python

- Follow normal Python/PEP 8 conventions and Google-style guidance for naming, imports, functions, classes, exceptions, and documentation.
- Prefer small functions with one clear responsibility.
- Prefer explicit data flow and dependency direction over hidden global state or import-time work.
- Use descriptive names. Avoid unexplained abbreviations and generic names such as `data`, `thing`, `obj`, or `tmp` when a domain-specific name is available.
- Keep public/module boundaries clear. Measurement, provider, analytics, storage, and web code should not become mutually dependent.
- Avoid clever abstractions, premature generalization, and speculative extension points. Introduce an abstraction when current code has demonstrated the need for it.
- Validate inputs at boundaries and represent unknown data honestly (`None`/SQL `NULL` where appropriate rather than fabricated zero/default facts).
- Preserve the repository's security rules: never persist or log API keys, prompts, generated responses, raw provider error bodies, or other sensitive material unless a future explicit design decision changes that policy.
- New behavior needs focused tests. Bug fixes should normally include a regression test.

## Comments and docstrings

Comments and docstrings are part of the maintainable interface of the code. Write them for a competent engineer who has not participated in the current conversation. They should also provide enough semantic context for an AI coding agent to modify the code safely without reconstructing intent from Git history.

### Comment the why, not the syntax

Good comments explain:

- invariants and assumptions;
- measurement semantics and timer boundaries;
- non-obvious security/privacy constraints;
- why a seemingly simpler implementation would be incorrect;
- provider/API behavior that affects correctness;
- migration/backward-compatibility constraints;
- important distinctions such as `0` versus unknown/`None`;
- intentional dependency boundaries;
- reasons for unusual algorithms or formulas.

Avoid comments that merely translate the next line of Python into English.

Bad:

```python
# Increment count by one.
count += 1
```

Useful:

```python
# Failed attempts remain in the reliability denominator, but they must not
# contribute fabricated zero values to successful latency distributions.
```

### Keep comments durable

- Describe the current invariant rather than narrating old implementation history. Durable history belongs in `DECISIONS.md` and numbered step reports.
- Do not mention chat conversations or rely on unstated context such as "as discussed above".
- Keep comments close to the code whose behavior they constrain.
- Update or remove a comment when the behavior changes. A stale comment is worse than no comment.
- Do not flood straightforward code with comments. Readability should come primarily from structure and naming.

### Docstrings

Use concise Google-style docstrings for public modules/classes/functions and for non-obvious internal functions where the contract is not clear from the signature and name.

Document, as relevant:

- what the function represents or guarantees;
- arguments whose semantics are not obvious;
- return-value semantics, especially nullable/unknown values;
- raised exceptions that are part of the caller contract;
- side effects such as persistence or network access;
- units and timing boundaries for measurement code.

Do not duplicate type information or obvious implementation details just to make a docstring longer.

## Code for human and AI maintainers

A future maintainer should be able to answer from the code and nearby documentation:

- What responsibility does this module/function own?
- What does it deliberately not own?
- What are its inputs and outputs?
- What invariants must remain true?
- What side effects can occur?
- Which values are measured facts versus derived values or labels?
- Which dependency direction is allowed?

Prefer explicit interfaces and named domain concepts over implicit conventions. When a convention is important but cannot be enforced in code, document it next to the relevant boundary and in `DECISIONS.md` when it is architectural.

## Web architecture

During the Step 014 Flask refactor, maintain this dependency direction:

```text
HTTP / Flask routes
        ↓
view/application/analytics logic
        ↓
storage
```

Benchmark collection, providers, pricing, measurement, percentile logic, and storage must remain usable without Flask. Flask is a web boundary, not the center of the system.

HTML belongs in templates once Step 014b performs that extraction. Python should prepare data and behavior rather than grow large embedded HTML documents.

## Review checklist

For every numbered implementation step, the implementer should review changed code for:

- correctness and edge cases;
- security/privacy regressions;
- clear names and responsibility boundaries;
- unnecessary complexity or duplication;
- comments/docstrings for non-obvious invariants and semantics;
- stale or misleading comments;
- test coverage of new behavior;
- preservation of `./run.sh` and the step's explicit contracts.

A successful test suite is necessary but is not by itself sufficient: the resulting code should be understandable and maintainable.