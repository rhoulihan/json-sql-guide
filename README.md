# json-sql-guide

Companion validator for the **Oracle SQL/JSON Developer Guide**.

This repository runs every `` ```sql `` example in the guide against a live Oracle AI Database 26ai instance and emits pass / fail reports, JUnit XML for CI, an annotated copy of the article with inline badges, and a deterministic JSON dump for diffing across runs.

It is published as a **companion artifact to the guide itself**: readers who want to verify the examples in their own database, or contributors editing the article, can clone this repo and run `validator run` to see exactly which snippets pass.

## Why this exists

The guide is ~1,700 lines of prose and 100+ SQL statements. Every snippet is plausible until it hits a parser. Doc drift over time (clause ordering tightening between 23ai and 26ai, behavior changes in `JSON_TRANSFORM`, partial-index syntax that never landed) turns yesterday's valid example into tomorrow's broken one. This tool is the parser.

The validation harness owns:

- **Extraction** — pulls every `` ```sql `` fence into a stable, line-anchored catalog.
- **Classification** — routes each block (standalone query / DDL / fragment / comment-only) to the right execution path.
- **Wrapping** — rewraps partial fragments (bare `WHERE`, naked `JSON_TABLE`, recursive `CYCLE` clauses) into executable SQL via a contributor-editable shape registry.
- **Execution** — runs against Oracle with per-snippet savepoint isolation so DML rolls back between examples; tracks DDL artifacts (TABLE / INDEX / VIEW / MATERIALIZED VIEW / SEARCH INDEX / DUALITY VIEW / PROPERTY GRAPH) and drops them at the end.
- **Reporting** — rich-formatted CLI summary, JUnit XML, annotated Markdown copy of the source, and a stable JSON dump for diffing.
- **Diff mode** — flags regressions (snippets that used to pass and now fail) so a guide PR can be blocked on red blocks.

## Status

**v1 ships.** All ten phases (P0–P10, including the dogfood pass) complete. The live Oracle SQL/JSON Developer Guide currently runs **113 / 113 statements clean** against Oracle 26ai with the bundled fixture. See [`docs/dogfood-findings.md`](docs/dogfood-findings.md) for the historical first-pass triage and [`docs/requirements.md`](docs/requirements.md) for the v1 spec.

## Quick start

```bash
git clone git@github.com:rhoulihan/json-sql-guide.git
cd json-sql-guide

# One-time
make setup                       # uv venv, deps, pre-commit hooks

# Boot Oracle 26ai Free locally and run the guide
docker run -d --name jsg-oracle --shm-size=1g -p 1521:1521 \
  -e ORACLE_PWD=oraclepw \
  container-registry.oracle.com/database/free:latest

# Wait for the container to print "DATABASE IS READY TO USE", then create
# the validator user (one-time)
docker exec -i jsg-oracle sqlplus -s sys/oraclepw@//localhost:1521/FREEPDB1 as sysdba <<'SQL'
ALTER SESSION SET CONTAINER = FREEPDB1;
CREATE USER validator IDENTIFIED BY validator QUOTA UNLIMITED ON USERS;
GRANT CONNECT, RESOURCE, CREATE VIEW, CREATE MATERIALIZED VIEW,
      CREATE SEQUENCE, CREATE PROCEDURE, CTXAPP TO validator;
SQL

# Run the validator against a guide markdown
uv run validator run ../LinkedIn/articles/oracle-sql-json-developer-guide.md \
  --out reports/
```

Outputs in `reports/`:

| File | Purpose |
|---|---|
| `junit.xml` | One `<testcase>` per executable statement, JUnit-schema valid. CI uploads this as a test artifact. |
| `results.json` | Deterministic JSON dump of every Result field. Used by `validator diff` for regression tracking. |
| `annotated.md` | Verbatim copy of the source guide with `<!-- ✓ sql-NNNN passed (N rows, Nms) -->` (or ✗ / ⊘) HTML comments inserted after each `sql` fence. Re-running the annotator over its own output is byte-for-byte idempotent. |

## CLI

```bash
# Extract every ``` sql ``` block into a stable JSON catalog
uv run validator extract <guide.md> [-o catalog.json]

# Full pipeline: extract → classify → execute → report
uv run validator run <guide.md> [--out reports/] [--fast-fail] [--overrides docs/sql-overrides.yaml]

# Diff two results.json runs; emits markdown by default
uv run validator diff previous.json current.json [--format md|json] [-o diff.md]
```

`validator run` exits non-zero if any snippet fails. `validator diff` exits non-zero only on **regressions** (a snippet that used to pass is now failing) — improvements are always exit 0.

## Important environment note

The validator's `CREATE SEARCH INDEX` examples (§11 of the guide) require **Oracle Text** (CTXSYS). The default `gvenzl/oracle-free:23.26.0-faststart` image used by the workflows ships Oracle Text out of the box, and the workflows grant `CTXAPP` to the validator user during setup. The slimmer `*-slim-faststart` variant strips Oracle Text — if you swap to that image you'll see `ORA-29833 indextype does not exist` on those two snippets; everything else still passes.

## Repository layout

```
json-sql-guide/
├── docs/
│   ├── requirements.md              v1 spec
│   ├── implementation-plan.md       phase-by-phase TDD plan
│   ├── dogfood-findings.md          first-pass triage report
│   └── sql-catalog-snapshot.json    baseline catalog from initial guide
├── fixture/
│   ├── schema.sql                   tables for everything in the guide
│   └── seeds/                       composable seed profiles
│       ├── base.py                  10 canonical orders
│       ├── tags_with_nums.py        mixed-type tag arrays
│       ├── deep_nest.py             4-level path examples
│       ├── dates_and_intervals.py   DATE/TIMESTAMPTZ/INTERVAL examples
│       ├── hybrid.py                customers, products, order_items, employees, categories
│       ├── events.py                JSON event log
│       ├── user_settings.py         relational config rows for JSON_OBJECTAGG
│       └── legacy.py                CLOB-backed JSON for migration story
├── src/validator/
│   ├── extractor.py                 markdown → snippet catalog
│   ├── classifier.py                snippet → STANDALONE / FRAGMENT / COMMENT_ONLY
│   ├── directives.py                inline -- @... + sidecar YAML
│   ├── wraps.py                     fragment shape registry
│   ├── fixture.py                   FixtureLoader: drops + recreates schema, seeds
│   ├── runner.py                    Oracle execution + savepoint isolation
│   ├── reporter.py                  CLI / JUnit / annotated MD / JSON
│   ├── diff.py                      regression detection
│   └── cli.py                       click entry points
├── tests/
│   ├── unit/                        pure-logic suites; no DB required
│   ├── integration/                 require_oracle marker; service container in CI
│   └── golden/                      catalog snapshot for extractor regression
├── .github/workflows/
│   ├── ci.yml                       lint + typecheck + unit
│   ├── integration.yml              service container + integration suite
│   ├── dogfood.yml                  runs validator against the live guide; uploads artifacts
│   └── pr-comment.yml               posts a summary back to the originating LinkedIn PR
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

## CI workflows

| Workflow | Trigger | Job |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | PR / push to `master` | Lint, type check, unit tests with 90% coverage gate. |
| [`integration.yml`](.github/workflows/integration.yml) | PR / push to `master` | Boots Oracle 26ai Free service container, runs `tests/integration` (marked `requires_oracle`). |
| [`dogfood.yml`](.github/workflows/dogfood.yml) | `workflow_dispatch` or `repository_dispatch` (`guide_dogfood`) | Validates the live LinkedIn-repo guide markdown end-to-end and uploads `reports/` as an artifact. |
| [`pr-comment.yml`](.github/workflows/pr-comment.yml) | `workflow_run` after Dogfood completes | Reads the artifact, formats a summary, and posts a comment on the originating LinkedIn PR. |

### How to read the bot comment

When a LinkedIn PR touches `articles/oracle-sql-json-developer-guide.md`, the bot comments with:

- **Passed / Failed / Skipped counts** — one line each. ``Skipped`` covers comment-only blocks and snippets tagged ``-- @skip``. ``expected-error-confirmed`` snippets count as passes.
- **Failures section** — collapsible. One bullet per failing snippet: `sql-NNNN line N: ORA-CODE — error text`. The annotated guide MD in the run artifact is the source of truth; the bot summary just helps you triage at a glance.
- **Full reports link** — points at the GitHub Actions run that produced the artifact. Click through to download `annotated.md` (the guide with badges in place) and `results.json` (machine-readable).

If the bot comment never appears, check that:

- The Dogfood workflow ran successfully (look in this repo's Actions tab).
- The originating PR's `repository_dispatch` payload included `pr_number` and `head_sha`.
- The `LINKEDIN_REPO_TOKEN` secret is set in this repo (a GitHub PAT or app token with `pull-requests: write` on the LinkedIn repo).

### Wiring the LinkedIn repo

In the LinkedIn repo, a small workflow fires `repository_dispatch` whenever a PR touches the guide:

```yaml
# .github/workflows/dispatch-guide-validator.yml in the LinkedIn repo
on:
  pull_request:
    paths: ["articles/oracle-sql-json-developer-guide.md"]
jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Fire validator dogfood
        uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.JSON_SQL_GUIDE_DISPATCH_TOKEN }}
          repository: rhoulihan/json-sql-guide
          event-type: guide_dogfood
          client-payload: |
            {
              "guide_url": "https://raw.githubusercontent.com/${{ github.repository }}/${{ github.event.pull_request.head.sha }}/articles/oracle-sql-json-developer-guide.md",
              "pr_number": "${{ github.event.pull_request.number }}",
              "head_sha": "${{ github.event.pull_request.head.sha }}"
            }
```

## Contributing

This is a thin, well-tested codebase. Adding a new shape, directive, or output format follows a strict TDD pattern — RED commit with failing tests, GREEN commit with the implementation, REFACTOR for cleanup. See `docs/implementation-plan.md` for the architecture intent and `tests/` for examples.

If a new guide example fails because the validator can't model some new SQL feature (a future Oracle 27ai construct, say), the path forward is:

1. Reproduce as a unit test against the existing module that owns that concern (extractor / classifier / wraps / runner).
2. Land a RED commit with the failing test.
3. Land a GREEN commit that makes the test pass.
4. Open a PR. The dogfood workflow will run against the actual guide and prove the change doesn't regress anything.

## License

MIT — see [LICENSE](LICENSE).
