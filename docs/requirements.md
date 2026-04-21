# SQL Validator for the Oracle SQL/JSON Developer Guide

**Status:** Draft requirements, v1
**Owner:** Rick Houlihan
**Repo:** `json-sql-guide`
**Companion to:** `LinkedIn/articles/oracle-sql-json-developer-guide.md`

---

## 1. Why this exists

Hermann Baer filed the first real bug on the SQL/JSON developer guide after reading about half of it, with a promise of more. Two of the specific issues he caught:

- Clause ordering in `JSON_VALUE` — `RETURNING` must come **before** `DEFAULT ... ON ERROR`, not after:
  ```sql
  -- wrong (currently in guide):
  JSON_VALUE(o.order_doc, '$.discount' DEFAULT 0 ON ERROR RETURNING NUMBER)
  -- correct:
  JSON_VALUE(o.order_doc, '$.discount' RETURNING NUMBER DEFAULT 0 ON ERROR)
  ```
- `PRETTY` modifier on `JSON_QUERY` requires an explicit character-based return type; it does not work on the native `JSON` type and raises an error:
  ```sql
  -- wrong (currently in guide):
  JSON_QUERY(o.order_doc, '$.shipping' PRETTY)
  -- correct:
  JSON_QUERY(o.order_doc, '$.shipping' RETURNING VARCHAR2 PRETTY)
  ```

Plus a scattering of `23ai` references that should now read `26ai` since the guide's target is Oracle AI Database 26ai.

Two types of errors to guard against:

1. **Syntactic / semantic errors** that silently pass code review because the article is prose — every `SELECT` is plausible until it hits an actual parser.
2. **Documentation drift** — as Oracle evolves (clause order tightening in 23ai, behavior changes in 26ai, new types like `VECTOR`), yesterday's valid snippet becomes tomorrow's broken example.

The fix is a self-contained validator that parses the article, extracts every SQL block, runs it against a **real Oracle AI Database 26ai instance**, and reports pass/fail per snippet with the exact error message. CI runs it on every doc change. Contributors get a pre-merge red light before bugs ship to readers.

---

## 2. Scope (v1)

The article has **67 SQL code blocks** across 13 sections (see `docs/sql-catalog-snapshot.json` for the full inventory). The distribution:

| Statement kind | Count |
|---|---|
| `SELECT` (direct) | 29 |
| `WITH` (CTE) | 10 |
| `CREATE INDEX` | 9 |
| `CREATE MULTIVALUE INDEX` | 3 |
| `CREATE SEARCH INDEX` | 2 |
| `CREATE TABLE` | 2 |
| `CREATE JSON RELATIONAL DUALITY VIEW` | 1 |
| `INSERT` | 2 |
| `UPDATE` | 2 |
| `ALTER` | 1 |
| Fragments (partial SELECT, NESTED PATH, CYCLE clauses that don't stand alone) | 6 |

**In scope for v1:**

- Parse the article, extract every fenced ` ```sql ` block with its line number, section heading, and subsection heading.
- Classify each block as:
  - **Standalone** — a complete statement the parser can run as-is.
  - **Fragment** — a partial expression (e.g. just a `WHERE` clause, or a `COLUMNS ( ... )` sub-clause of `JSON_TABLE`). These need a wrapping strategy documented per case.
  - **Comment-only** — illustrative pseudo-SQL that shouldn't be executed.
- Provision a **canonical test fixture** (tables, data, indexes) that every snippet can run against without the author having to hand-wire `CREATE TABLE` statements into the guide.
- Execute each standalone block against Oracle AI Database 26ai, collect `ORA-` error codes and messages, and emit a pass/fail report.
- Surface the two Hermann bugs (clause order, PRETTY modifier) as **expected-fail → fixed** regression tests so the validator keeps them fixed.

**Out of scope for v1 (noted for v2):**

- Performance or plan-shape validation (`EXPLAIN PLAN`, `DBMS_XPLAN`, row count assertions). A statement may parse and execute correctly while still hitting the full table scan the article claims it avoids — that's a deeper harness and belongs in a separate `perf/` test suite.
- Auto-fix suggestions (e.g. rewriting mis-ordered clauses). A v2 nice-to-have.
- Validation of the narrative claims themselves (e.g. "this runs in O(1)"). Text analysis is a different problem.
- Multi-version comparison (running the same snippet against 19c, 23ai, and 26ai to highlight where behavior diverges). v2.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Oracle SQL/JSON Guide                          │
│              (articles/oracle-sql-json-developer-guide.md)          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  scan + extract
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       1. Extractor                                  │
│                                                                     │
│  • Walks the markdown tree, collects every ```sql block             │
│  • Records: (line, section, subsection, sql, classification)        │
│  • Emits canonical catalog JSON (sql-catalog.json)                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       2. Classifier                                 │
│                                                                     │
│  • Tags each block: standalone | fragment | comment-only            │
│  • For fragments: applies a wrapping strategy from the registry     │
│    so a WHERE clause becomes SELECT * FROM orders <clause>          │
│    and a NESTED PATH becomes a full JSON_TABLE call                 │
│  • Expands macros like `{now}`, `{customer_id}` to real values      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       3. Fixture loader                             │
│                                                                     │
│  • Self-contained Oracle 26ai schema: orders table, entities        │
│    table, validated_orders, JSON collection tables                  │
│  • Seeded with sample documents that exercise every path expression │
│    referenced in the article                                        │
│  • Idempotent: drops and recreates per run                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       4. Execution harness                          │
│                                                                     │
│  • Containerized Oracle 26ai (Docker, gvenzl/oracle-free:26-full)   │
│  • node-oracledb (thin mode) or python-oracledb for execution       │
│  • Per-snippet savepoint + rollback so DML doesn't leak             │
│  • Captures: success | ORA-NNNNN error | warning (if any)           │
│  • Records cardinality for SELECT results (row count, not shape)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       5. Reporter                                   │
│                                                                     │
│  • Markdown report with per-section pass/fail table                 │
│  • JUnit XML for CI consumption                                     │
│  • Diff mode: highlight which blocks changed result vs last run     │
│  • Annotated copy of the article with ✓/✗ badges inline             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Extractor — detailed behavior

**Input:** path to a markdown file (default: the canonical guide in the sibling `LinkedIn` repo — configurable via `--source`).

**Output:** `sql-catalog.json`, a list of records:

```json
{
  "id": "sql-0042",
  "line": 1345,
  "section": "11. Indexing and Performance",
  "subsection": "Functional B-tree Indexes",
  "sql": "CREATE INDEX idx_amount_str ON orders o (o.order_doc.amount.string());",
  "classification": "standalone",
  "tags": ["ddl", "index", "json-functional"],
  "expected_result": "success",
  "notes": null
}
```

**Rules:**

- Only ` ```sql ` fences count. Blocks fenced as ` ```json `, ` ```javascript `, or un-tagged are ignored.
- Leading `-- ...` comments on a block are preserved as-is (they often explain the block's intent and may contain directives — see §4.1).
- Blocks that begin with a comment block but have no executable statement are tagged `comment-only` and skipped by the executor.
- A block may contain **multiple statements** separated by `;`. The extractor preserves the block as a single unit; the executor splits on `;` at statement boundaries, respecting single-quoted strings and PL/SQL blocks.

### 4.1 Directive comments

The extractor recognizes optional in-block directives to control execution behavior. All are leading-line comments:

| Directive | Effect |
|---|---|
| `-- @skip` | Skip execution entirely (e.g. pseudocode, or `CREATE TABLE` examples that would conflict with the fixture). |
| `-- @expect-error ORA-40569` | Assert that execution fails with this specific error code. |
| `-- @fragment` | Override classifier; treat as a fragment needing wrapping. |
| `-- @wrap-as SELECT * FROM orders o WHERE %s` | Provide an explicit wrap template. `%s` is replaced with the block body. |
| `-- @requires-fixture tags-with-nums` | Request a specific data seed before execution (see §6.1). |
| `-- @runs-as DBA` | Execute as a privileged user (for `CREATE INDEX`, `ALTER SYSTEM`, etc.). |

Directives must precede the executable SQL. They do not need to be committed to the article itself — the validator supports a **sidecar file** `docs/sql-overrides.yaml` that maps `(line, file)` → directives for snippets that should not carry comments for readability.

---

## 5. Classifier

Each block is assigned one of four classes. The decision tree:

1. **`comment-only`** — Block contains no executable statement (only `-- ...` lines, or a stubbed `-- placeholder` style).
2. **`fragment`** — First executable token is not in `{SELECT, WITH, INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, GRANT, BEGIN}`. Typical fragments in this guide:
   - Standalone `WHERE JSON_EXISTS(...)` clauses (3 instances).
   - `JSON_TABLE(doc, ...)` sub-expressions used to illustrate a `COLUMNS` list.
   - `NESTED PATH ...` fragments showing array flattening syntax.
   - `CYCLE ... SET ...` fragments showing recursive CTE cycle detection.
3. **`standalone-ddl`** — Executable, but modifies schema. Run against a scratch user on the test database. Dropped and recreated per test run.
4. **`standalone-query`** — Executable, read-only. Runs inside a read-only transaction; no fixture mutation.

Fragments need a **wrapping strategy** to become executable. The validator ships with a default registry:

| Fragment shape | Wrap template |
|---|---|
| `WHERE JSON_EXISTS(...)` | `SELECT 1 FROM orders o %s` |
| `JSON_TABLE(o.order_doc, ...)` | `SELECT t.* FROM orders o, %s t FETCH FIRST 1 ROW ONLY` |
| `NESTED PATH ...` | Inject into a `JSON_TABLE` wrapper with a minimal parent `COLUMNS` list. |
| `CYCLE col SET ...` | Inject into a minimal recursive CTE over `orders`. |

The wrap registry lives in `src/wraps.ts` (or `.py`) and is contributor-editable.

---

## 6. Test fixture

### 6.1 Canonical schema

The fixture is **self-contained** — everything the article needs to exist, exists. DDL lives in `fixture/schema.sql`:

```sql
-- Primary table used throughout the guide
CREATE TABLE orders (
  order_id   NUMBER PRIMARY KEY,
  order_doc  JSON
);

-- Single-table design example from §11
CREATE TABLE entities (
  pk        VARCHAR2(50),
  sk        VARCHAR2(100),
  data      JSON,
  PRIMARY KEY (pk, sk)
);

-- Validated orders example from §12
CREATE TABLE validated_orders (
  order_id   NUMBER PRIMARY KEY,
  order_doc  JSON
    CONSTRAINT order_shape CHECK (order_doc IS JSON VALIDATE USING '
      { "type": "object", "properties": {
          "orderId":  { "type": "number" },
          "customer": { "type": "string" },
          "items":    { "type": "array" }
        }, "required": ["orderId","customer","items"]
      }'
    )
);

-- Referenced in a handful of relational-join examples
CREATE TABLE customers (
  customer_id   VARCHAR2(50) PRIMARY KEY,
  customer_name VARCHAR2(200),
  tier          VARCHAR2(20)
);

CREATE TABLE products (
  sku           VARCHAR2(50) PRIMARY KEY,
  product_name  VARCHAR2(200),
  category_id   NUMBER,
  list_price    NUMBER
);
```

### 6.2 Seed data

`fixture/seeds/` contains named seed profiles. Each profile is a small Python/Node script that populates tables with shapes the corresponding section exercises. Profiles:

| Profile | Purpose |
|---|---|
| `base` | 10 orders with realistic `customer`, `status`, `items[]`, `shipping`, `tags[]`. Required by every run. |
| `tags-with-nums` | Orders where `tags[]` contains mixed numeric + string values — exercises the multivalue index typed-variant examples. |
| `deep-nest` | Orders with 4-level-deep `$.shipping.address.geo.coords[0]` paths for the extended-types section. |
| `dates-and-intervals` | Orders with `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, and `INTERVAL` values in the document — extended-types table. |
| `hybrid` | Customers and products tables populated; orders reference real `customer_id` and `sku` values for the CTE pipeline example. |

A section's snippets declare which seeds they need via the `@requires-fixture` directive. The default seed is `base`.

### 6.3 Why a fixture, not user-provided data

Two reasons:

1. The article's narrative promises "this query returns X." Without a deterministic fixture, the validator can only check that the statement parses and executes — it can't verify the result shape matches the claim. Controlled seeds let us assert row counts and even specific values where the article calls them out.
2. Contributors should not have to build a demo schema to fact-check a doc change. `cd json-sql-guide && make test` should Just Work.

---

## 7. Execution harness

### 7.1 Database

- **Oracle AI Database 26ai Free** (`container-registry.oracle.com/database/free:26ai`), pinned by digest.
- Provisioned via Docker Compose. `docker compose up -d` brings up a clean instance in ~90s.
- Single PDB. Single app user (`guide_user`) with object privileges on the fixture schema. A separate `guide_dba` user runs DDL statements tagged `@runs-as DBA`.
- `init/` directory with startup scripts auto-loads `fixture/schema.sql` and the seed profiles on first boot.

### 7.2 Driver

- Python reference implementation using `python-oracledb` (thin mode — no Oracle Instant Client install). This keeps the validator `pip install`-friendly.
- Every snippet runs inside a `BEGIN ... SAVEPOINT sp; ... ROLLBACK TO sp; END;` frame so DML doesn't leak between snippets.
- DDL snippets run in a dedicated sandbox schema that is dropped and recreated at the start of each run.

### 7.3 Per-snippet execution

```python
@dataclass
class SnippetResult:
    id: str
    line: int
    classification: str
    outcome: Literal["pass", "fail", "skip", "expected-error-confirmed"]
    error_code: str | None     # e.g. "ORA-40569"
    error_text: str | None
    rows_returned: int | None  # None for DDL/DML; count for SELECT
    elapsed_ms: int
    wrapped_sql: str | None    # If fragment, the SQL that actually ran
```

- A `pass` means the statement executed to completion with no `ORA-` error.
- A `fail` means any unexpected `ORA-` error, or mismatch against an `@expect-error` directive.
- `skip` is reserved for `comment-only` and `@skip`-tagged blocks.
- `expected-error-confirmed` is a success outcome for `@expect-error` directives that matched.

### 7.4 Isolation and ordering

- Snippets run in article order by default. This matters because §1 creates the `orders` table in prose, and later sections reference it.
- The fixture loader runs first. If a snippet's DDL conflicts with the fixture (e.g. a second `CREATE TABLE orders` later in the article for illustrative purposes), the extractor's `@skip` directive or `@wrap-as` rewrite should prevent the duplicate.
- The extractor assigns sequential IDs (`sql-0001` through `sql-0067`) so results are stable across runs regardless of article edits that don't change block content.

---

## 8. Reporter

### 8.1 Pass/fail summary (CLI)

```
Oracle SQL/JSON Guide — Validation Report
  Generated:  2026-04-19T10:24:51Z
  Database:   Oracle AI Database 26ai Free (23.26.1)
  Source:     articles/oracle-sql-json-developer-guide.md (1,686 lines)

  Total blocks:     67
  Executed:         61   (6 skipped: comment-only or @skip)
  Passed:           58
  Failed:            3

  FAILURES
  ────────────────────────────────────────────────────────────────────
  sql-0012  §2 JSON_VALUE  line 140
    ORA-40596: JSON path clause order is invalid
    > JSON_VALUE(o.order_doc, '$.discount' DEFAULT 0 ON ERROR RETURNING NUMBER)
    HINT: RETURNING must precede DEFAULT ... ON ERROR

  sql-0023  §4 JSON_QUERY  line 298
    ORA-40600: PRETTY requires a character returning clause
    > JSON_QUERY(o.order_doc, '$.shipping' PRETTY)
    HINT: Add RETURNING VARCHAR2 before PRETTY

  sql-0054  §11 Indexing   line 1476
    Narrative uses "23ai+" label. Should be "26ai" for current guide scope.
    (warning, not a SQL failure)
```

### 8.2 JUnit XML

Standard JUnit output at `reports/junit.xml` for CI integration. Each snippet is a `<testcase>`; errors include the full `ORA-` text.

### 8.3 Annotated article

`reports/annotated-guide.md` — a copy of the source article with ✓/✗/⊘ badges inserted immediately after each ` ```sql ` fence:

```markdown
```sql
SELECT JSON_VALUE(o.order_doc, '$.customer') AS customer_name
FROM   orders o;
```
<!-- ✓ sql-0004 passed (2 rows, 8ms) -->
```

Makes PR review trivial — reviewer sees exactly which snippets are now broken after a change.

### 8.4 Diff mode

`validator diff previous.json current.json` emits a markdown summary of snippets whose outcome changed since the last run. Useful for regression tracking when the guide is edited.

---

## 9. Developer workflow

```
# One-time setup
git clone git@github.com:rhoulihan/json-sql-guide.git
cd json-sql-guide
make setup                 # pulls the Oracle 26ai image, builds a venv

# Normal run
make test                  # boots DB, loads fixture, runs all snippets, emits report
make test BLOCK=sql-0023   # run one snippet
make test SECTION=11       # run all snippets in section 11

# Running against a local article edit
make test SOURCE=../LinkedIn/articles/oracle-sql-json-developer-guide.md

# Regenerate the catalog after section headings change
make catalog

# Clean state
make clean                 # drops the DB volume
```

Contributor UX targets:

- **Cold start to first green run:** < 5 minutes on a laptop.
- **Incremental run after one article edit:** < 15 seconds (only re-run changed snippets).
- **No Oracle Instant Client install required.** Thin-mode driver only.

---

## 10. CI integration

### 10.1 GitHub Actions workflow

`.github/workflows/validate.yml` in this repo, triggered by:

- `pull_request` against `main` in the sibling `LinkedIn` repo that touches `articles/oracle-sql-json-developer-guide.md`.
- `push` against `main` in **this** repo (validator code changes).
- Manual `workflow_dispatch`.

Steps:

1. Checkout both repos (`LinkedIn` and `json-sql-guide`).
2. Boot Oracle 26ai Free in a service container.
3. `pip install -e .` this repo.
4. Run `validator run --source ../LinkedIn/articles/oracle-sql-json-developer-guide.md --out reports/`.
5. Upload `reports/junit.xml` as a test artifact.
6. Upload `reports/annotated-guide.md` as a build artifact.
7. Comment on the PR with a summary of failures (if any).

### 10.2 PR comment template

```
### SQL Validator Report

✅ **58 of 61** executable blocks passed.
⊘ 6 skipped (comment-only or tagged `@skip`).
❌ **3 failures** — see [annotated report](link).

Failing blocks:
- `sql-0012` §2 line 140 — `ORA-40596: JSON path clause order is invalid`
- `sql-0023` §4 line 298 — `ORA-40600: PRETTY requires character returning clause`
- `sql-0054` §11 line 1476 — 23ai→26ai label drift (warning)

Regressions since last green: none.
```

### 10.3 Branch protection

The validator check is required for merge on the `LinkedIn` repo's `main` branch. A contributor cannot land a doc change that introduces a new SQL failure without explicitly opting out (via `@expect-error` directive, which requires justification).

---

## 11. Implementation stack

**Language:** Python 3.12.
- `python-oracledb` 2.x (thin mode) — database driver.
- `click` — CLI framework.
- `rich` — terminal output formatting.
- `pyyaml` — overrides file parsing.
- `jinja2` — report templating.
- `pytest` — meta-tests for the validator itself (not for the article snippets — those run through the validator directly).

**Why Python over Node:** the reference guide lives in a Python-friendly team, and `python-oracledb` thin mode is the only Oracle driver that works without installing Oracle Instant Client. Contributors can `pip install oracledb` and be running in 30 seconds.

**Project layout:**

```
json-sql-guide/
├── docs/
│   ├── requirements.md           (this file)
│   └── sql-catalog-snapshot.json (reference catalog captured at project start)
├── src/
│   └── validator/
│       ├── __init__.py
│       ├── extractor.py    (markdown → catalog)
│       ├── classifier.py   (catalog → classified blocks)
│       ├── wraps.py        (fragment wrap registry)
│       ├── fixture.py      (schema + seed loader)
│       ├── runner.py       (execution harness)
│       ├── reporter.py     (pass/fail reports, junit, annotated md)
│       ├── overrides.py    (sidecar directives loader)
│       └── cli.py
├── fixture/
│   ├── schema.sql
│   └── seeds/
│       ├── base.py
│       ├── tags-with-nums.py
│       ├── deep-nest.py
│       ├── dates-and-intervals.py
│       └── hybrid.py
├── tests/                  (meta-tests)
│   ├── test_extractor.py
│   ├── test_classifier.py
│   ├── test_wraps.py
│   └── test_reporter.py
├── reports/                (gitignored — run artifacts)
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── README.md
```

---

## 12. Known edge cases the validator must handle

Captured from a walk of the current 67-block catalog:

1. **`CREATE TABLE orders` appears in §1 AND in a later section** as an illustrative variant. The later one needs a `@skip` directive or must be rewritten against a different table name.
2. **`CREATE INDEX idx_order_status ON orders`** appears twice with different column expressions (lines 163 and 1312). The second one will fail with `ORA-00955: name already used` unless the first is dropped or the second is renamed. Options: rename the second to `idx_order_status_v2` in the article, or add a per-block DROP prefix in the runner.
3. **Multiple `CREATE MULTIVALUE INDEX idx_tags_str`** (lines 1431 and 1460). Same issue.
4. **`CREATE INDEX idx_amount_str` and `idx_amount_num` on the same JSON path** with different typed variants. These should both succeed — they're the point of the typed-variant indexes section — but only if the fixture doesn't already carry a conflicting index.
5. **`JSON_TABLE` with `NESTED PATH`** subclauses appear as isolated blocks; these are fragments and need wrapping.
6. **`WITH ... RECURSIVE` CTE with `CYCLE` clause** appears as a fragment in §7.
7. **JSON Schema validation** in §12 uses a long `VALIDATE USING '...'` string. The validator must correctly handle the embedded JSON-in-single-quotes.
8. **`CREATE JSON RELATIONAL DUALITY VIEW`** in §12 references underlying tables (`orders`, `order_items`). The fixture needs an `order_items` table for this block to succeed. Add to `fixture/schema.sql`.
9. **The bigger-picture multi-model query** (§12) uses `VECTOR_DISTANCE(...)`, `GRAPH_TABLE(...)`, and a property graph. The fixture needs a minimal property graph and a `VECTOR` column seeded with deterministic embeddings. Alternatively, that block is tagged `@skip` with a note that it's illustrative.

---

## 13. Success criteria

- **v1 ships** with all 67 blocks categorized, 58+ executing green against Oracle 26ai Free.
- The two Hermann bugs are represented as failing snippets until the article is fixed, then pass after the article fix lands.
- CI runs on every PR touching the article. First-time contributor can run `make test` locally in under 5 minutes.
- A second guide (e.g. a future Graph/Vector guide) can be pointed at the same validator by passing `--source <path>` — the extractor is not article-specific.

---

## 14. Open questions

1. **How aggressive should the validator be about DDL conflicts?** Should it wrap every `CREATE INDEX` in `BEGIN EXECUTE IMMEDIATE 'DROP INDEX ...'; EXCEPTION WHEN OTHERS THEN NULL; END;` or just error loudly and ask the author to rename?
2. **Do we version the Oracle image per guide revision?** As 26ai quarterly RUs land, behavior will shift. Pin by digest per guide version, or always track latest?
3. **Do we publish the validator image to GHCR** so contributors without Docker locally can still run it via a devcontainer?
4. **Result assertions — do we go there in v1?** Catching "this returns 2 rows" as a regression when an edit changes the seed data to return 3. Valuable but doubles the fixture maintenance burden.

These will be decided in v1 design review with Rick + Hermann.
