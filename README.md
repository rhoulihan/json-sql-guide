# json-sql-guide

Companion validator for the Oracle SQL/JSON Developer Guide.

Parses the published guide, extracts every `` ```sql `` block, and runs each against a live Oracle AI Database 26ai instance. Emits pass/fail reports, JUnit XML for CI, and an annotated copy of the article with inline badges on every block.

## Why

The guide is ~1,700 lines of prose and 67 SQL snippets. Every snippet is plausible until it hits a parser. Doc drift over time (clause ordering tightening in 23ai, behavior changes in 26ai) turns yesterday's valid example into tomorrow's broken one. This tool is the parser.

## Status

**Design phase.** See [`docs/requirements.md`](docs/requirements.md) for the full v1 specification.

The initial SQL inventory is captured in [`docs/sql-catalog-snapshot.json`](docs/sql-catalog-snapshot.json) — a baseline of 67 blocks across 13 sections from the guide at the time this repo was created.

## Quick start (once implemented)

```bash
git clone git@github.com:rhoulihan/json-sql-guide.git
cd json-sql-guide
make setup           # pulls Oracle 26ai Free, builds a venv
make test            # boots DB, loads fixture, runs every snippet, emits report
```

Reports land in `reports/`:
- `junit.xml` — for CI
- `report.md` — human-readable summary
- `annotated-guide.md` — source article with ✓/✗ badges on every SQL block

## License

TBD (likely MIT).
