# Dogfood findings — first pass against the live guide

**Run date:** 2026-04-24
**Source:** `LinkedIn/articles/oracle-sql-json-developer-guide.md` (1,686 lines, 67 SQL blocks)
**Database:** Oracle 26ai Free (gvenzl/oracle-free:23.26.0-slim-faststart, faststart variant)
**Validator commit:** `87ea91f` (P9 shipped)

## Summary

After P0–P9 ship and the splitter bug fix, the validator extracts **67 snippets** which expand to **90 executable statements** (multi-statement blocks split on top-level `;`). Of those:

| Outcome | Count | % |
|---|---|---|
| Passed | 35 | 39% |
| Failed | 55 | 61% |
| Skipped | 0 | 0% |

44 of 67 distinct snippets have at least one failing statement.

## Failure breakdown

| ORA code | Count | Sample |
|---|---|---|
| ORA-40462 | 11 | JSON path `$.nonexistent` evaluated to no value |
| ORA-00955 | 7 | name is already used by an existing object |
| ORA-00942 | 7 | table or view `EVENTS` does not exist |
| ORA-02158 | 6 | invalid CREATE INDEX option |
| ORA-00904 | 4 | "DOC": invalid identifier |
| ORA-01408 | 3 | such column list already indexed |
| ORA-00000 / DPY-4010 | 2 | bind variable replacement value for `:QUERY_VECTOR` |
| ORA-00936 | 2 | missing expression |
| ORA-29833 | 2 | indextype does not exist |
| ORA-40452 | 1 | default value type ≠ RETURNING type |
| ORA-40481 | 1 | ASCII/PRETTY unsupported on non-text |
| ORA-01400 | 1 | NULL into NOT NULL `order_id` |
| ORA-03048 | 1 | WHERE invalid following `)` |
| ORA-03405 | 1 | end of query; no additional text |
| ORA-00928 | 1 | SELECT keyword missing |
| ORA-00906 | 1 | missing left parenthesis |
| ORA-00907 | 1 | missing right parenthesis |
| ORA-02000 | 1 | missing THEN keyword |
| ORA-01756 / DPY-2041 | 1 | missing ending quote |
| ORA-00900 | 1 | invalid SQL statement |

## Categorization

### A. Sandbox / fixture conflicts — ~21 failures

The guide's prose-driven DDL collides with the validator's own fixture. Most of these are illustrative `CREATE TABLE` / `CREATE INDEX` blocks that should not actually run inside the validator harness.

- **ORA-00955** (×7) — `CREATE TABLE orders ...` examples that conflict with the fixture. Mark these `@skip`.
- **ORA-00942** (×7) — references to `EVENTS`, `customers.<col>` etc. that aren't in our fixture. Either extend the fixture or add `@skip`.
- **ORA-01408** (×3) — duplicate functional indexes against the same column expression. Sandbox-cleanup issue: index lifecycles bleed across snippets within the same run because Oracle DDL auto-commits and the validator's per-run cleanup only catches a small allowlist of object types. Extend `_DDL_PATTERNS` or `@skip`.
- **ORA-00000 / DPY-4010** (×2) — vector-search example uses bind variable `:QUERY_VECTOR`. Either bind a deterministic vector via `@wrap-as` or `@skip`.
- **ORA-01400** (×1) — DML inserting `NULL` into `order_id`. Fixture already has rows; `@skip` or `@wrap-as` to use a unique key.

**Action:** add `docs/sql-overrides.yaml` mapping these snippet IDs to `skip` or richer `wrap-as`.

### B. Schema-shape mismatches — ~5 failures

Guide examples mix column naming conventions: most use `o.order_doc`, but a handful use `doc` directly, and §11 uses an `entities (pk, sk, doc)` shape that differs from our fixture's `entities (pk, sk, data)`.

- **ORA-00904** (×4) — `"DOC"`: invalid identifier in the partial-index examples (lines 1495+).
- **ORA-00936** (×2) — likely fragment-wrap mismatch where `o.order_doc` would be needed.

**Action:** unify on `o.order_doc` in the guide, or rename the fixture's `entities.data` → `entities.doc` (cheaper). The fixture already has the right shape — just one column rename.

### C. Demonstrative-error patterns — 11 failures

`ORA-40462: JSON path evaluated to no value` (×11) appears because the guide intentionally shows `$.nonexistent` queries to demonstrate `DEFAULT ... ON ERROR` and `NULL ON EMPTY` behavior. These are pedagogical, not bugs.

**Action:** tag each with `@expect-error ORA-40462` so the validator confirms the demonstrated error is the one Oracle raises. This converts a fail into an `expected-error-confirmed` pass and surfaces guide drift if the error code ever changes.

### D. Possible 26ai compatibility issues — 8 failures

These warrant Hermann/Beda review against current 26ai grammar:

- **ORA-02158** (×6) — `CREATE INDEX ... WHERE ...` (partial indexes, lines 1478, 1495, 1502, 1512, 1519, 1524). Oracle 23ai/26ai partial indexes use a specific grammar; the syntax shown may not match. Verify against the latest *Oracle Database SQL Language Reference*.
- **ORA-29833** (×2) — `CREATE SEARCH INDEX` blocks. Confirm CTXSYS / search-index extensions are installed in the test database, or update syntax for 26ai's JSON Search index variant.

**Action:** investigate; likely a guide update is required.

### E. Real guide bugs — 9 failures

Each of these is a single, distinct error type — exactly the kind of one-off typo or grammar drift the validator is built to catch:

- **sql-0066 line 1586 — ORA-00907** "missing right parenthesis"
- **sql-0067 line 1597 — ORA-00904** `O.CUSTOMER_NAME` invalid identifier (the duality view example references a column that doesn't exist on `orders`)
- **ORA-40452** — default value not matching `RETURNING` clause type
- **ORA-40481** — `ASCII` or `PRETTY` not supported for non-text return type (this is one of Hermann's flagged bugs — the validator caught it on first run)
- **ORA-03048** — `WHERE` following `)` is invalid
- **ORA-03405** — extra text after query
- **ORA-00928** — `SELECT` keyword missing
- **ORA-00906** — missing `(`
- **ORA-02000** — missing `THEN`
- **ORA-01756** — quote not properly terminated

**Action:** open a tracking issue per snippet against the LinkedIn repo. These are the highest-value findings.

## Validator-side fixes from this dogfood

1. **Splitter:** post-`;` trailing `-- comment` was being treated as a fresh statement. Fixed in this commit by filtering comment-only fragments after splitting. Recovered 8 false-failures.
2. **DDL artifact tracker:** doesn't currently catch `CREATE FUNCTION`, `CREATE TYPE`, or property-graph DDL. Extend `_DDL_PATTERNS` if the guide grows in those directions.

## Next steps (priority order)

1. Author `docs/sql-overrides.yaml` with `@skip` and `@expect-error` directives for categories A and C (eliminates ~32 false failures).
2. Rename fixture `entities.data → entities.doc` (eliminates ~6 failures).
3. File guide-fix tickets for categories D and E with line numbers and proposed diffs.
4. Re-run dogfood and target a 90%+ pass rate.

After step 4, every remaining red snippet is a real guide bug that should block the LinkedIn PR.
