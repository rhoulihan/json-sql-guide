# json-sql-guide

Companion validator for the Oracle SQL/JSON Developer Guide.

Parses the published guide, extracts every `` ```sql `` block, and runs each against a live Oracle AI Database 26ai instance. Emits pass/fail reports, JUnit XML for CI, and an annotated copy of the article with inline badges on every block.

## Why

The guide is ~1,700 lines of prose and 67 SQL snippets. Every snippet is plausible until it hits a parser. Doc drift over time (clause ordering tightening in 23ai, behavior changes in 26ai) turns yesterday's valid example into tomorrow's broken one. This tool is the parser.

## Status

**v1 in build.** P0–P8 complete: scaffold, extractor, classifier, directives, fragment wrap registry, fixture loader, execution runner, reporter, diff mode. P9 wires CI polish + the PR bot. See [`docs/requirements.md`](docs/requirements.md) for the v1 spec and [`docs/implementation-plan.md`](docs/implementation-plan.md) for phase-by-phase TDD.

The initial SQL inventory is captured in [`docs/sql-catalog-snapshot.json`](docs/sql-catalog-snapshot.json) — a baseline of 67 blocks across 13 sections from the guide at the time this repo was created.

## Quick start

```bash
git clone git@github.com:rhoulihan/json-sql-guide.git
cd json-sql-guide
make setup           # uv venv, deps, pre-commit hooks
make db-up           # boot Oracle 26ai Free
make test            # unit + integration suites
```

Reports land in `reports/`:
- `junit.xml` — for CI
- `results.json` — machine-readable run state
- `annotated.md` — source guide with ✓/✗ badges on every SQL block

Run against a guide markdown directly:

```bash
uv run validator run path/to/guide.md --out reports/
uv run validator diff previous.json reports/results.json --format md
```

## CI workflows

Three workflows live under `.github/workflows/`:

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

## License

TBD (likely MIT).
