# Implementation Plan — SQL Validator

**Status:** v1 plan
**Companion to:** `docs/requirements.md`
**Owner:** Rick Houlihan
**Methodology:** Strict TDD (red → green → refactor), trunk-based flow, mandatory pre-commit hooks, required CI checks before merge.

---

## 0. Guiding principles

1. **Tests exist before code.** Every public function and module is landed via a failing test first. No production code is written without a red test demanding it.
2. **Outside-in.** Start at the CLI / integration boundary, stub everything underneath, then fill inward. The first tests describe behavior visible to a user; unit tests follow to cover the pieces the integration tests exercise.
3. **Never merge red.** CI is the truth. A PR that fails any required check cannot land on `master`. Required: lint, type check, unit tests, integration tests against Oracle 26ai Free, and a dogfood run against the guide.
4. **Pre-commit is the first line of defense.** Lint, format, type-check, and fast unit tests all run before the commit hits the server. CI is a safety net, not the first check.
5. **The test pyramid is enforced by CI timing budgets.** Unit tier: under 5 seconds. Integration tier: under 2 minutes against a warm DB. E2E dogfood: under 3 minutes.
6. **Small PRs. Small commits.** Each commit represents one red → green → refactor cycle. A PR represents one feature vertical — extractor, classifier, wrap registry, etc.
7. **No feature flags in v1.** The product doesn't ship to users; it ships to CI. There's no compat surface to protect. Break things cleanly if the design needs it.

---

## 1. Toolchain

| Concern | Tool | Pinned via |
|---|---|---|
| Language | Python 3.12 | `pyproject.toml` `requires-python` |
| Packaging | `uv` (preferred) or `pip` + `venv` | project `Makefile` |
| Linter + formatter | `ruff` (replaces black, isort, flake8) | `pyproject.toml` `[tool.ruff]` |
| Type checker | `mypy` strict mode | `pyproject.toml` `[tool.mypy]` |
| Test runner | `pytest` + `pytest-cov` + `pytest-xdist` | dev-dependency |
| Fixtures | `pytest-oracledb` (internal) + `testcontainers-python` | dev-dependency |
| DB driver | `python-oracledb` 2.x, thin mode | runtime dep |
| CLI | `click` | runtime dep |
| Terminal output | `rich` | runtime dep |
| Templating | `jinja2` | runtime dep |
| YAML | `pyyaml` | runtime dep |
| Pre-commit | `pre-commit` | dev-dependency |
| CI | GitHub Actions | `.github/workflows/` |
| Container | Docker + Docker Compose | `docker-compose.yml` |
| Oracle image | `container-registry.oracle.com/database/free:26ai` | pinned by digest in `docker-compose.yml` |

---

## 2. Phase overview

| Phase | Name | Outcome | PR # (target) | Duration |
|---|---|---|---|---|
| P0 | Scaffold | Empty package, CI green, pre-commit installed, Oracle container boots | 1–2 | 1 day |
| P1 | Extractor | `validator extract <md>` emits a deterministic catalog JSON | 3 | 2 days |
| P2 | Classifier | Every catalog entry is typed: standalone, fragment, comment-only | 4 | 1 day |
| P3 | Directives + overrides | `@skip`, `@expect-error`, `@fragment`, sidecar YAML loader | 5 | 1 day |
| P4 | Fragment wrap registry | Partial SQL shapes are rewrapped into executable statements | 6 | 2 days |
| P5 | Fixture loader | Canonical schema + seed profiles, idempotent drop/recreate | 7 | 2 days |
| P6 | Execution runner | Statements execute against Oracle 26ai with savepoint isolation | 8 | 2 days |
| P7 | Reporter | CLI, JUnit XML, annotated markdown output | 9 | 2 days |
| P8 | Diff mode | `validator diff a.json b.json` highlights outcome changes | 10 | 1 day |
| P9 | CI polish + PR bot | Workflow, artifacts, PR comment template, branch protection | 11 | 1 day |
| P10 | Dogfood against the guide | Validator run against the live article; Hermann's bugs appear as red | 12 | 1 day |

Total: ~16 working days, landable in 12 PRs.

---

## 3. Repository layout

```
json-sql-guide/
├── .github/
│   └── workflows/
│       ├── ci.yml                 (lint + typecheck + unit)
│       ├── integration.yml        (integration against Oracle service container)
│       ├── dogfood.yml            (run validator vs the guide in the sibling repo)
│       └── release.yml            (tagged release → PyPI, future)
├── .pre-commit-config.yaml
├── docker-compose.yml             (Oracle 26ai Free for local + CI)
├── docs/
│   ├── requirements.md
│   ├── implementation-plan.md     (this file)
│   └── sql-catalog-snapshot.json
├── fixture/
│   ├── schema.sql
│   └── seeds/
│       ├── base.py
│       ├── tags_with_nums.py
│       ├── deep_nest.py
│       ├── dates_and_intervals.py
│       └── hybrid.py
├── src/
│   └── validator/
│       ├── __init__.py
│       ├── cli.py
│       ├── extractor.py
│       ├── classifier.py
│       ├── directives.py
│       ├── wraps.py
│       ├── fixture.py
│       ├── runner.py
│       ├── reporter.py
│       ├── diff.py
│       └── models.py              (dataclasses for Snippet, Result, Catalog)
├── tests/
│   ├── conftest.py                (shared fixtures)
│   ├── unit/
│   │   ├── test_extractor.py
│   │   ├── test_classifier.py
│   │   ├── test_directives.py
│   │   ├── test_wraps.py
│   │   ├── test_reporter.py
│   │   └── test_diff.py
│   ├── integration/
│   │   ├── test_fixture.py
│   │   ├── test_runner.py
│   │   └── test_end_to_end.py
│   └── golden/
│       ├── sample_guide.md        (synthetic minimal markdown for extractor tests)
│       ├── sample_catalog.json    (expected output)
│       └── sample_report.md       (expected annotated output)
├── Makefile
├── pyproject.toml
├── README.md
└── uv.lock
```

---

## 4. Phase 0 — Scaffold

**Goal:** PR green with zero behavior. Every tool is wired; every required check runs. The repo can reject a bad commit before code exists.

### TDD cycle

- **RED:** nothing. Phase 0 is configuration, not code. But one test must exist: `tests/unit/test_smoke.py::test_package_imports` — `import validator`. It will fail until the package skeleton is in place.
- **GREEN:** create `src/validator/__init__.py` with `__version__ = "0.0.0"`.
- **REFACTOR:** N/A.

### Deliverables

1. `pyproject.toml` with:
   - `[project]` metadata, `python_requires = ">=3.12"`.
   - Dev and runtime dependency tables.
   - `[tool.ruff]` with `line-length = 100`, all rule groups enabled except `D` (docstrings — enable after P3 when there's something to document).
   - `[tool.mypy]` with `strict = true`, `disallow_untyped_defs = true`, `warn_redundant_casts = true`.
   - `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, `addopts = "-ra --strict-markers --strict-config"`, markers registered for `integration`, `slow`, `requires_oracle`.
   - Coverage config with fail-under threshold at 90% (runtime dir only — excludes `tests/`, `fixture/`).

2. `.pre-commit-config.yaml`:
   ```yaml
   repos:
     - repo: https://github.com/astral-sh/ruff-pre-commit
       hooks:
         - id: ruff           # lint
         - id: ruff-format    # format
     - repo: https://github.com/pre-commit/mirrors-mypy
       hooks:
         - id: mypy
           additional_dependencies: [click, rich, pyyaml, jinja2]
     - repo: https://github.com/pre-commit/pre-commit-hooks
       hooks:
         - id: check-json
         - id: check-yaml
         - id: check-toml
         - id: end-of-file-fixer
         - id: trailing-whitespace
         - id: check-merge-conflict
         - id: check-added-large-files
           args: ['--maxkb=500']
     - repo: local
       hooks:
         - id: pytest-unit
           name: pytest unit
           entry: uv run pytest tests/unit -x -q
           language: system
           pass_filenames: false
           stages: [pre-commit]
   ```

3. `Makefile` with targets: `setup`, `install`, `test`, `test-unit`, `test-integration`, `lint`, `format`, `typecheck`, `clean`, `db-up`, `db-down`.

4. `docker-compose.yml` pinning `container-registry.oracle.com/database/free:26ai` by digest, exposing 1521, with an `init/` mount for schema bootstrap.

5. `.github/workflows/ci.yml` with jobs:
   - `lint` — `ruff check`, `ruff format --check`.
   - `typecheck` — `mypy src tests`.
   - `unit` — `pytest tests/unit --cov=validator --cov-fail-under=90`.
   - All three jobs required for merge (set via branch protection once repo has activity).

6. `.github/workflows/integration.yml` with:
   - Oracle 26ai Free as a service container.
   - Step to wait for DB health.
   - Runs `pytest tests/integration -m requires_oracle`.
   - Fast-fail on first failure.

7. README section "Contributing" with the red-green-refactor loop, PR checklist, and a note that pre-commit is mandatory.

### Acceptance criteria

- `make setup` provisions a venv and installs everything in ≤ 60s on a warm cache.
- `make test-unit` runs in ≤ 5s and passes (the smoke import test).
- `pre-commit run --all-files` passes clean.
- CI goes green on the P0 PR.
- Branch protection is configured to require `lint`, `typecheck`, `unit` checks.

---

## 5. Phase 1 — Extractor

**Goal:** Given a markdown file, emit a deterministic catalog of every ` ```sql ` block with line, section, subsection, and raw body.

### Tests first (written BEFORE code)

File: `tests/unit/test_extractor.py`

Each of these is a new failing test committed in its own RED commit, then a GREEN commit adding just enough extractor code, then a REFACTOR commit if shape warrants.

1. `test_extractor_returns_empty_catalog_for_markdown_without_sql_fences` — input is a simple markdown with no code fences; output is an empty list.
2. `test_extractor_finds_single_sql_block` — one ` ```sql ` fence; output is one `Snippet` with correct `sql` body.
3. `test_extractor_records_line_number_of_opening_fence` — block starts at line 42; snippet's `line` is 42.
4. `test_extractor_captures_current_section_from_preceding_h2` — block nested under `## 3. JSON_VALUE`; `section` is that heading, `subsection` is None.
5. `test_extractor_captures_current_subsection_from_preceding_h3` — block nested under an `### Subheading` inside an H2; both set.
6. `test_extractor_updates_section_when_a_new_h2_appears` — two H2 sections each with a block; each block's `section` matches its own parent.
7. `test_extractor_ignores_non_sql_fences` — a ` ```python ` and a ` ```json ` fence in the input; output catalog is empty.
8. `test_extractor_preserves_leading_dash_comments_inside_block` — body begins with `-- explanatory comment`; that line is preserved verbatim.
9. `test_extractor_handles_multiple_statements_in_one_block` — block contains `SELECT 1; SELECT 2;`; body is preserved as a single entry with both statements.
10. `test_extractor_assigns_sequential_ids_by_appearance_order` — three blocks across the document; ids are `sql-0001`, `sql-0002`, `sql-0003`.
11. `test_extractor_is_deterministic` — same input twice yields identical JSON.
12. `test_extractor_uses_only_the_opening_fence_line_for_positioning` — closing fence is on a later line; `line` is the opener.
13. `test_extractor_rejects_unclosed_fence_with_clear_error` — input ends mid-block; extractor raises `UnclosedFenceError` referencing the opening line.
14. `test_extractor_cli_writes_catalog_to_stdout_by_default` — `validator extract <file>` emits valid JSON to stdout.
15. `test_extractor_cli_writes_to_file_when_output_flag_is_set` — `validator extract <file> -o catalog.json` writes that file.

### Minimum implementation

`src/validator/models.py`:
```python
@dataclass(frozen=True)
class Snippet:
    id: str
    line: int
    section: str
    subsection: str | None
    sql: str
```

`src/validator/extractor.py`:
- `extract(text: str) -> list[Snippet]` — pure function, no I/O.
- `extract_file(path: Path) -> list[Snippet]` — thin wrapper.
- Parser is state-machine based: track current H2/H3, toggle inside-fence on ` ```sql `, capture body, append on close.

`src/validator/cli.py`:
- `validator extract` Click command wired to `extract_file`.

### Acceptance criteria

- All 15 tests pass.
- Coverage of `extractor.py` ≥ 95%.
- Running `validator extract ../LinkedIn/articles/oracle-sql-json-developer-guide.md` emits a catalog matching `docs/sql-catalog-snapshot.json` **byte-for-byte** (barring id prefix — snapshot used a different scheme; update snapshot if needed).
- PR adds a golden-file test: extract the real guide, compare against checked-in `tests/golden/guide_catalog.json`.

---

## 6. Phase 2 — Classifier

**Goal:** Given a catalog, tag each `Snippet` with one of: `standalone_ddl`, `standalone_query`, `fragment`, `comment_only`.

### Tests first

File: `tests/unit/test_classifier.py`

1. `test_classifier_tags_select_as_standalone_query`
2. `test_classifier_tags_with_cte_as_standalone_query`
3. `test_classifier_tags_insert_update_delete_merge_as_standalone_query`
4. `test_classifier_tags_create_table_as_standalone_ddl`
5. `test_classifier_tags_create_index_as_standalone_ddl`
6. `test_classifier_tags_create_json_relational_duality_view_as_standalone_ddl`
7. `test_classifier_tags_alter_drop_as_standalone_ddl`
8. `test_classifier_tags_where_fragment_as_fragment`
9. `test_classifier_tags_json_table_fragment_as_fragment`
10. `test_classifier_tags_nested_path_fragment_as_fragment`
11. `test_classifier_tags_cycle_clause_fragment_as_fragment`
12. `test_classifier_tags_body_with_only_comments_as_comment_only`
13. `test_classifier_ignores_leading_comments_when_classifying`
14. `test_classifier_handles_lowercase_keywords`
15. `test_classifier_classifies_in_a_single_pass_idempotently`

### Minimum implementation

`src/validator/classifier.py`:
- `classify(snippet: Snippet) -> Classification` — enum + rationale string.
- `ClassifiedSnippet` wraps `Snippet` + classification + any hints (e.g. suspected wrap template).
- Decision tree documented in requirements §5.

### Acceptance criteria

- 15 unit tests pass.
- Integration test: classify the full guide catalog and assert counts by class match the expected distribution (58 executable, 6 fragments, rest comment-only).

---

## 7. Phase 3 — Directives + overrides

**Goal:** Support `@skip`, `@expect-error`, `@fragment`, `@wrap-as`, `@requires-fixture`, `@runs-as` either as inline comments or via a sidecar `docs/sql-overrides.yaml`.

### Tests first

File: `tests/unit/test_directives.py`

1. `test_inline_skip_directive_marks_snippet_skipped`
2. `test_inline_expect_error_directive_records_expected_ora_code`
3. `test_inline_fragment_directive_forces_fragment_classification_even_for_select`
4. `test_inline_wrap_as_directive_overrides_default_wrap`
5. `test_inline_requires_fixture_directive_records_seed_profile`
6. `test_inline_runs_as_dba_directive_records_elevated_execution`
7. `test_sidecar_yaml_can_target_snippet_by_id`
8. `test_sidecar_yaml_can_target_snippet_by_line`
9. `test_sidecar_overrides_merge_with_inline_directives_inline_wins`
10. `test_malformed_directive_raises_directive_parse_error_with_line_reference`

### Minimum implementation

`src/validator/directives.py`:
- `Directive` enum.
- `parse_inline(snippet: Snippet) -> list[Directive]` — scans leading `-- @...` lines.
- `load_sidecar(path: Path) -> dict[str, list[Directive]]` — YAML keyed by id or line.
- `apply_directives(snippet, directives) -> DirectedSnippet` — merges and returns augmented snippet.

### Acceptance criteria

- 10 unit tests pass.
- Sidecar YAML schema validated by a JSON Schema file at `docs/overrides.schema.json` (not strictly required but documented for contributors).

---

## 8. Phase 4 — Fragment wrap registry

**Goal:** Given a fragment, look up a wrap template by shape and produce executable SQL.

### Tests first

File: `tests/unit/test_wraps.py`

1. `test_wrap_registry_has_entry_for_where_json_exists_fragment`
2. `test_wrap_registry_applies_template_to_produce_executable_sql`
3. `test_wrap_registry_falls_through_to_explicit_wrap_as_directive_when_provided`
4. `test_wrap_registry_for_json_table_expression_wraps_in_cross_join`
5. `test_wrap_registry_for_nested_path_fragment_injects_into_minimal_json_table_parent`
6. `test_wrap_registry_for_cycle_clause_fragment_injects_into_minimal_recursive_cte`
7. `test_wrap_registry_raises_when_fragment_shape_not_recognized`
8. `test_wrap_registry_is_extensible_via_register_wrapper_function`
9. `test_wrapped_sql_parses_as_valid_oracle_sql_no_execution` — uses a local parser sanity check (regex, not the DB).
10. `test_wrap_registry_emits_diagnostic_comment_in_wrapped_sql_for_debuggability`

### Minimum implementation

`src/validator/wraps.py`:
- Registry of `(shape_matcher, template)` tuples.
- `wrap(fragment: DirectedSnippet) -> WrappedSnippet`.
- Template substitution via `string.Template` or explicit `%s` replacement.
- Registry can be extended via `register(shape_matcher, template)` decorator.

### Acceptance criteria

- 10 unit tests pass.
- All 6 fragments in the current guide have a registry entry and produce syntactically valid wrapped SQL (tested against the real catalog in an integration test).

---

## 9. Phase 5 — Fixture loader

**Goal:** Boot Oracle 26ai, create the canonical schema, load a requested seed profile, drop cleanly.

### Tests first

File: `tests/integration/test_fixture.py` (marked `@pytest.mark.requires_oracle`)

1. `test_fixture_drops_and_recreates_schema_idempotently`
2. `test_fixture_loads_base_seed_and_asserts_row_counts`
3. `test_fixture_loads_tags_with_nums_seed_and_inspects_array_shape`
4. `test_fixture_loads_deep_nest_seed_with_4_level_paths`
5. `test_fixture_loads_dates_and_intervals_seed`
6. `test_fixture_loads_hybrid_seed_with_customers_and_products_populated`
7. `test_fixture_loader_accepts_multiple_seed_profiles_in_one_run`
8. `test_fixture_loader_raises_on_unknown_seed_profile`
9. `test_fixture_loader_can_re_run_against_already_loaded_db_without_error`
10. `test_fixture_loader_creates_order_items_table_for_duality_view_example`

### Minimum implementation

`fixture/schema.sql` — DDL for `orders`, `entities`, `validated_orders`, `customers`, `products`, `order_items`.

`fixture/seeds/*.py` — each module exposes `load(conn: oracledb.Connection) -> None`.

`src/validator/fixture.py`:
- `FixtureLoader(conn, profiles: list[str])` — orchestrator.
- `load()` — drops sandbox schema objects, recreates from `schema.sql`, runs each profile's `load()`.
- `drop()` — idempotent drop for end-of-run cleanup.

### Acceptance criteria

- 10 integration tests pass against the Oracle service container.
- Cold-start time (container up → schema loaded → base seed applied) ≤ 120 seconds.
- Re-run (container already up → drop/recreate → reload) ≤ 15 seconds.

---

## 10. Phase 6 — Execution runner

**Goal:** Run classified snippets (and wrapped fragments) against the DB with savepoint isolation, capture outcomes, respect `@expect-error` and `@skip`.

### Tests first

File: `tests/integration/test_runner.py` (marked `@pytest.mark.requires_oracle`)

1. `test_runner_executes_simple_select_and_records_pass`
2. `test_runner_captures_ora_error_and_records_fail`
3. `test_runner_respects_skip_directive_and_records_skip`
4. `test_runner_confirms_expected_error_when_ora_code_matches`
5. `test_runner_records_fail_when_expected_error_does_not_match_actual`
6. `test_runner_rolls_back_dml_between_snippets_via_savepoint`
7. `test_runner_executes_ddl_in_sandbox_and_drops_artifacts_at_end`
8. `test_runner_records_row_count_for_select_statements`
9. `test_runner_records_elapsed_ms_within_expected_range`
10. `test_runner_splits_multi_statement_block_and_records_per_statement_outcomes`
11. `test_runner_uses_dba_connection_when_runs_as_dba_directive_present`
12. `test_runner_processes_snippets_in_catalog_order`
13. `test_runner_continues_after_failure_by_default`
14. `test_runner_fast_fails_when_fast_fail_flag_is_set`

### Minimum implementation

`src/validator/runner.py`:
- `Runner(conn_factory, options)` — holds config, opens connections lazily per role.
- `execute(snippets: Iterable[DirectedSnippet]) -> list[Result]`.
- Per-snippet savepoint + rollback.
- `Result` dataclass matches the shape in requirements §7.3.

### Acceptance criteria

- 14 integration tests pass.
- Running the full 67-snippet guide catalog end-to-end completes in ≤ 90 seconds against a warm DB.

---

## 11. Phase 7 — Reporter

**Goal:** Emit human and machine-readable outputs: CLI summary, JUnit XML, annotated markdown, JSON results.

### Tests first

File: `tests/unit/test_reporter.py`

1. `test_cli_report_shows_total_pass_fail_skip_counts`
2. `test_cli_report_lists_failures_with_section_line_and_ora_code`
3. `test_cli_report_renders_with_rich_markup_and_strips_cleanly_when_tty_disabled`
4. `test_junit_report_is_valid_xml_against_schema`
5. `test_junit_report_creates_one_testcase_per_snippet`
6. `test_junit_report_marks_failures_with_message_and_type`
7. `test_junit_report_marks_skipped_snippets_as_skipped`
8. `test_annotated_markdown_preserves_original_content_byte_for_byte_outside_of_inserted_badges`
9. `test_annotated_markdown_inserts_pass_badge_after_passing_sql_fence`
10. `test_annotated_markdown_inserts_fail_badge_with_ora_code_after_failing_sql_fence`
11. `test_annotated_markdown_inserts_skip_badge_for_skipped_snippets`
12. `test_annotated_markdown_is_idempotent_when_reapplied_to_already_annotated_file`
13. `test_results_json_serializes_all_result_fields`
14. `test_results_json_is_stable_across_runs_given_identical_inputs`

### Minimum implementation

`src/validator/reporter.py`:
- `render_cli(results, console) -> None` (rich).
- `render_junit(results, path) -> None`.
- `render_annotated(results, source_md_path, output_path) -> None`.
- `dump_json(results, path) -> None`.

### Acceptance criteria

- 14 unit tests pass.
- JUnit XML validates against the Jenkins JUnit schema.
- Annotated markdown roundtrips: re-running the annotator over its own output produces byte-identical output (no badge duplication).

---

## 12. Phase 8 — Diff mode

**Goal:** `validator diff previous.json current.json` → markdown summary of outcome changes.

### Tests first

File: `tests/unit/test_diff.py`

1. `test_diff_reports_no_changes_when_results_are_identical`
2. `test_diff_reports_newly_failing_snippet`
3. `test_diff_reports_newly_passing_snippet`
4. `test_diff_reports_newly_skipped_snippet`
5. `test_diff_reports_snippet_added_since_previous_run`
6. `test_diff_reports_snippet_removed_since_previous_run`
7. `test_diff_emits_markdown_with_section_grouping`
8. `test_diff_ignores_elapsed_ms_fluctuation_by_default`
9. `test_diff_exit_code_is_nonzero_when_regressions_exist`
10. `test_diff_exit_code_is_zero_when_only_improvements_exist`

### Minimum implementation

`src/validator/diff.py` — pure function over `list[Result]` pairs.

### Acceptance criteria

- 10 unit tests pass.
- CLI integration: `validator diff a.json b.json --format=md` produces the expected Markdown.

---

## 13. Phase 9 — CI polish + PR bot

**Goal:** The full CI pipeline (lint + type + unit + integration + dogfood) is wired. PRs to the LinkedIn repo that touch the guide receive a comment with pass/fail summary.

### Tests first (CI-level — no pytest; validated via actual CI run on a draft PR)

1. Dogfood workflow: on `workflow_dispatch`, runs against the live guide; validator output is uploaded as an artifact.
2. Cross-repo workflow: on `pull_request` in `LinkedIn` touching the guide, kick off a remote workflow in this repo.
3. PR comment: bot posts a summary (pass count, fail list with ORA codes, regressions since previous green) using `actions/github-script`.
4. Branch protection: merging to `master` in `LinkedIn` requires a green dogfood run when the guide file is in the diff.

### Deliverables

- `.github/workflows/dogfood.yml` — checks out both repos, boots Oracle 26ai, runs validator, uploads artifacts.
- `.github/workflows/pr-comment.yml` — called by the LinkedIn repo via `workflow_run`; posts comment.
- Documentation in README: "How to interpret the bot comment."

### Acceptance criteria

- Draft PR on the LinkedIn repo touching `oracle-sql-json-developer-guide.md` triggers the bot.
- Comment appears within 3 minutes.
- Branch protection rule in the LinkedIn repo is updated to require the check.

---

## 14. Phase 10 — Dogfood against the guide

**Goal:** The validator runs against the live article. Hermann's two bugs show up as red. Fix the article (in a separate PR in the LinkedIn repo), then validator goes green for those specific snippets.

### Sequence

1. Land the validator v1 on `master`. Tag `v0.1.0`.
2. Run `validator run --source ../LinkedIn/articles/oracle-sql-json-developer-guide.md --out reports/`.
3. Expected output:
   - `sql-0012` (line 140) — fail, `ORA-40596` or similar clause-order error.
   - `sql-0023` (line 298) — fail, `ORA-40600` or similar PRETTY on JSON-type error.
   - All other executable blocks — pass.
   - Possibly: additional failures we didn't anticipate. Log them.
4. For each confirmed failure, open an issue in the LinkedIn repo with the fix diff.
5. Land the article fix. Re-run validator. All green.

### Acceptance criteria

- The two Hermann bugs are reproduced by the validator.
- At least one additional bug (if present) is caught.
- Post-fix article passes the validator green.
- A regression test is added: `tests/regression/test_hermann_bugs_stay_fixed.py` with the fixed SQL variants, ensuring future edits don't reintroduce them.

---

## 15. Pre-commit hook strategy

Pre-commit runs **locally** before a commit hits git. Four tiers, escalating cost:

| Tier | Hooks | Target runtime | Runs on |
|---|---|---|---|
| **Free** | trailing whitespace, EOF fixer, merge-conflict, check-json/yaml/toml, large-files | < 100ms | every commit |
| **Fast** | `ruff check`, `ruff format --check` | < 500ms | every commit |
| **Medium** | `mypy src` | < 2s | every commit |
| **Slow** | `pytest tests/unit -x` | < 5s | every commit |

Integration tests (requiring Oracle) are **not** part of pre-commit. They run in CI only. Rationale: pre-commit must be fast enough that contributors don't disable it. Integration tier lives server-side.

Developers can bypass pre-commit with `git commit --no-verify` for emergency fixes, but CI catches everything pre-commit would have. Pre-commit is a convenience, not a gate.

---

## 16. CI pipeline

```
pull_request
  ├── lint       (ruff check + format check)              ~30s
  ├── typecheck  (mypy src tests)                         ~45s
  ├── unit       (pytest tests/unit --cov)                ~60s
  └── integration (pytest tests/integration)              ~3m
        (service container: Oracle 26ai Free, pinned digest)

push (master)
  └── all of the above + dogfood against the guide       ~4m
        (upload artifacts: junit.xml, annotated-guide.md)

tag (v*)
  └── release (build wheel, publish to PyPI — deferred to v0.2.0)
```

All four pull-request checks are required for merge. Dogfood is advisory on PRs (so a WIP PR isn't blocked) but required on `master`.

---

## 17. Red-green-refactor ritual

Every working cycle is three commits:

1. **`test: add failing test for <behavior>`**  
   A single test file addition or edit. Test asserts desired behavior. CI red. Commit message starts with `test:`.
2. **`feat: <behavior>`** (or `fix:`, `chore:`, etc.)  
   Minimum code to pass the test. CI green. No refactoring.
3. **`refactor: <rationale>`** *(optional)*  
   Improve shape, extract helpers, rename. No behavior change. Tests remain green. Skip if no refactor is warranted.

Commits are squashed on merge via PR, but the full history is preserved in the PR description and visible to reviewers. Code review focuses on:

- Were the tests written first? (Check commit order.)
- Does each test assert one thing?
- Is the green implementation the minimum that passes?
- Is the refactor free of behavior drift?

---

## 18. Definition of done (per phase)

A phase is not merged until every item below is true:

- [ ] All listed tests exist and pass.
- [ ] Coverage of phase-touched files ≥ 90%.
- [ ] `ruff check` and `ruff format --check` pass.
- [ ] `mypy --strict src tests` passes.
- [ ] `pre-commit run --all-files` passes.
- [ ] CI is green on the PR.
- [ ] Phase acceptance criteria (listed per phase above) are individually checked.
- [ ] Documentation: if the phase adds a CLI command, README usage section is updated.
- [ ] No TODO or FIXME comments without a linked GitHub issue.

---

## 19. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Oracle 26ai Free image behavior changes between RUs | medium | medium | Pin by digest in compose and CI. Bump deliberately, run full suite on bump. |
| Flaky tests from DB container startup race | medium | high | Health-check wait loop with generous timeout; retry once on container boot failure in CI. |
| `python-oracledb` thin mode gap vs thick (missing features) | low | low | Document at boundary; move to thick only if a specific test requires it. |
| Pre-commit too slow → developers disable it | medium | high | Timing budgets in §15 are enforced; if the slow tier creeps past 5s, move the offender to CI-only. |
| Fragment wrap registry needs frequent edits as guide grows | high | low | Registration is a one-line decorator; add an integration test that every fragment in the catalog has a registered wrap. |
| Article reshuffling breaks id stability | medium | medium | Ids are based on appearance order, so they're stable as long as blocks are added at the end. If blocks move, the diff report surfaces this as "removed + added" rather than "changed" — that's acceptable; document it. |

---

## 20. Open questions to resolve before P0

(Pulled forward from requirements §14 — these must be answered before CI is configured.)

1. **DDL conflict handling** — should the runner silently drop-before-create, or raise? Recommendation: raise by default, provide a `--drop-before-create` flag for local dev. Author fixes the article.
2. **Image digest pinning cadence** — manual bump after a quarterly Oracle RU, or weekly dependabot-style bot? Recommendation: manual, driven by releases of meaningful 26ai features.
3. **GHCR publishing** — publish a `json-sql-guide:latest` image with the validator baked in for devcontainer use? Recommendation: defer to v0.2.0.
4. **Result assertions (row counts, specific values)** — v1 scope or v2? Recommendation: v2. v1 validates that SQL parses and executes; v2 validates that results match narrative claims.

---

## Appendix A — Sample commit sequence for Phase 1 (illustrative)

```
PR #3 — Extractor

commit 1  test: empty catalog for markdown without sql fences (RED)
commit 2  feat: skeleton extractor returning empty list (GREEN)
commit 3  test: finds single sql block (RED)
commit 4  feat: state machine recognizes ```sql fences (GREEN)
commit 5  test: records line number of opening fence (RED)
commit 6  feat: track line counter (GREEN)
commit 7  test: captures current section from preceding h2 (RED)
commit 8  feat: track latest h2 heading (GREEN)
...
commit 30 refactor: extract Snippet dataclass and ParserState (REFACTOR)
commit 31 test: extract the real guide matches golden catalog (INTEGRATION)
commit 32 feat: golden catalog test file (GREEN)
commit 33 docs: extractor usage in README
```

The PR squash-merges to a single commit on `master`. The full log is in the PR.
