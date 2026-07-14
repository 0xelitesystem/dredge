# Contributing

dredge is built around one core abstraction: the `Investigator`. Every data source, search engines, court archives, regulatory databases, on-chain data, social platforms, is a subclass that implements one async method.

## Adding an investigator

1. Create `dredge/investigators/your_source.py`
2. Subclass `Investigator`. Set:
   - `name`, short identifier used on the CLI (e.g. `sec_edgar`)
   - `description`, one-line description
   - `requires_keys`, list of env-var names this module needs (empty list if none)
   - `supports_types`, which target types make sense (`person`, `company`, `domain`, `wallet`)
3. Implement `async investigate(self, target: Target) -> list[Finding]`
4. Register the class in `REGISTRY` in `dredge/cli.py`
5. Update `.env.example` if new env vars were added
6. Open a PR with at least one example output saved under `examples/`

## What makes a good investigator

- **Hits a source that's actually buried.** New search-engine wrappers add little. Court records, regulatory filings, archived/deleted content, on-chain data, and platform-specific archives are where the value is.
- **Returns structured `Finding` objects.** Don't synthesize summaries or score targets. Surface raw evidence with primary-source URLs.
- **Fails gracefully.** If the API is down or returns garbage, log and return `[]`. One module breaking should not break the run.
- **Respects rate limits.** Use the API's actual rate limit, not what you can get away with. Add a `DREDGE_*` env var if a limit needs tuning.

## What we won't merge

- Modules that scrape behind authentication or paywalls
- Modules that fabricate, score, or editorialize on findings
- Modules that target private individuals based on protected attributes
- Modules that violate platform terms of service in a way that exposes users to legal risk

## Code style

- Python 3.10+
- Type hints on every function signature
- `httpx` for HTTP, `asyncio` for concurrency
- No new runtime dependencies without discussion in an issue first
