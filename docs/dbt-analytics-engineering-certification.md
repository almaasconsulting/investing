# dbt Analytics Engineering Certification — Complete Foundation Guide

**Guide scope:** Entry-level dbt certification  
**Exam:** dbt Analytics Engineering Certification  
**Target exam version:** dbt 1.11  
**Guide last reviewed:** 20 July 2026

This is the first guide in the certification series. It teaches the practical dbt
knowledge assessed by the Analytics Engineering exam. All examples use a neutral
retail analytics scenario and can be adapted to any supported data platform. The
planned next guide is the dbt Architect Certification.

The explanations are general: they apply whether the warehouse is PostgreSQL,
Snowflake, BigQuery, Databricks, Redshift or another supported platform. Adapter-
specific behavior is identified as such. The guide does not assume a particular
company, repository, architecture or orchestration product.

> This is an independent learning guide, not an exam dump. Exam details change.
> Confirm them on the official certification page before registering.

## 1. Current exam at a glance

The [official certification page](https://www.getdbt.com/certifications/analytics-engineer-certification-exam)
currently lists:

| Item | Current value |
|---|---:|
| Supported dbt version | 1.11 |
| Duration | 2 hours |
| Questions | 65 |
| Passing score | 65% |
| Price | USD 200 |
| Recommended experience | SQL proficiency and at least six months using dbt |

The live exam page is the authority for current logistics. The downloadable official
study guide may still mention dbt 1.7, so use it for the topic outline and use current
1.11 documentation for command and feature behavior.

The current public exam domains are:

1. Developing and optimizing dbt models
2. Managing dbt model governance
3. Debugging data-modeling errors
4. Troubleshooting and optimizing dbt pipelines
5. Implementing dbt tests
6. Implementing and maintaining external dependencies
7. Leveraging dbt state

Documentation, source freshness, Git, Jinja, packages and deployment practices run
through several domains even when they do not appear as separate headings.

The official study guide describes question formats that can include multiple choice,
fill-in-the-blank, matching, hotspot, ordered/build-list and discrete-option multiple
choice. Treat the current exam page and registration system as authoritative if the
format changes. At 65 questions in 120 minutes, the average time budget is about 1
minute 51 seconds per question; mark difficult questions according to the exam
interface and protect time for a final review.

### Certification path

| Order | Certification | Primary emphasis | What this guide covers |
|---:|---|---|---|
| 1 | Analytics Engineering | Building, testing, documenting, debugging and deploying dbt transformations | Complete foundation and exam preparation |
| 2 | Architect | Secure, scalable environments, orchestration, integrations and enterprise governance | Planned follow-up guide |

The Analytics Engineering certification is the practical foundation. Architect topics
assume that models, tests, lineage, environments, CI and state are already familiar.

### Exam-domain map

| Official exam domain | Primary chapters | You must be able to do |
|---|---|---|
| Developing and optimizing models | 3–8, 17–18 | Build modular DAGs, choose materializations, write performant SQL and use Jinja |
| Model governance | 9–11 | Apply contracts, access, versions, groups, grants and documentation correctly |
| Debugging modeling errors | 12, 15 | Classify failures and diagnose parsed, compiled and executed code |
| Pipelines | 12–16 | Select, build, retry, clone, schedule and troubleshoot graph execution |
| Tests | 9 | Design generic, singular, custom generic and unit tests |
| External dependencies | 8, 10 | Manage packages, sources, freshness and exposures |
| dbt state | 13–14 | Use artifacts, state/result selectors and deferral safely |

## 2. Prerequisites

### SQL

Be comfortable writing and reviewing:

- joins, including understanding duplicate amplification;
- aggregations and `group by`;
- common table expressions;
- window functions such as `row_number()`;
- null handling and type conversion;
- set operations;
- date/time transformations;
- query plans and basic performance diagnosis.

### Git

Know the purpose of:

- a feature branch versus the protected `main` branch;
- `git fetch`, `git pull`, commits and pull requests;
- resolving merge conflicts;
- code review and CI checks;
- keeping credentials and generated artifacts out of source control.

### Analytics engineering

An analytics engineer converts raw data into trusted, documented, tested datasets.
dbt contributes software-engineering practices—modularity, version control, automated
testing, documentation, lineage and deployment—to SQL transformations.

## 3. The dbt mental model

dbt does not normally ingest raw data. It connects to a data platform, compiles SQL
and Jinja into executable SQL, runs that SQL in the platform, and records metadata.

The core workflow is:

<pre class="mermaid">
flowchart LR
    A[Operational systems<br/>SaaS and files] -->|Ingestion or ELT| B[(Raw warehouse objects)]
    B -->|source()| C[Staging models]
    C -->|ref()| D[Intermediate models]
    D -->|ref()| E[Business marts and metrics]
    E -->|exposures| F[Dashboards, applications,<br/>notebooks and ML]
    Q[Tests, descriptions, ownership<br/>and contracts] -. apply across the graph .-> C
    Q -.-> D
    Q -.-> E
</pre>

Important node types include models, sources, seeds, snapshots, tests, analyses,
macros, exposures and metrics. `ref()` and `source()` create dependency edges. dbt
uses those edges to build a directed acyclic graph (DAG) and execute nodes in a valid
order.

### How dbt's control flow fits together

<pre class="mermaid">
flowchart TD
    A[Project SQL and YAML<br/>packages and profile/target] --> B[Parse project]
    B --> C[Manifest and DAG]
    C -->|Selector chooses nodes| D[Render Jinja and compile SQL]
    D --> E[Execute SQL in the data platform]
    E --> F[Build relations and run tests]
    F --> G[Artifacts, logs and documentation]
    G --> H[State-aware CI and deferral]
    G --> I[Observability and orchestration]
</pre>

This distinction is fundamental:

- **Project code** describes transformations and metadata.
- **The manifest/DAG** represents parsed resources and dependencies.
- **Selection** decides which part of the graph is in an invocation.
- **Compilation** converts Jinja and dbt functions into platform SQL.
- **Execution** happens in the connected data platform.
- **Artifacts** allow later invocations and external tools to understand the result.

### Connection map

| Concept | Connects to | Why the connection matters |
|---|---|---|
| Profile/target | dbt project to a data platform and environment | Determines credentials, database, schema and execution context |
| `source()` | model to an externally created relation | Adds source lineage, testing and freshness metadata |
| `ref()` | model/test to another dbt node | Controls relation resolution and DAG build order |
| `config()` | resource to materialization and behavior | Changes how and where a node is built |
| Test | assertion to a model/source/column | Turns an assumption into an executable quality check |
| Contract | declared schema to a model build | Protects the shape of a governed interface |
| Version | old and new model interfaces | Enables migration across a breaking change |
| Exposure | downstream consumer to upstream nodes | Shows business impact, owner and lineage |
| Selector | invocation to a graph subset | Controls cost, CI scope and operational behavior |
| Artifact | one invocation to later tools/invocations | Enables docs, debugging, state comparison and orchestration |
| State + defer | development/CI graph to prior production metadata | Avoids rebuilding unchanged upstream nodes |
| Orchestrator | schedules/events to dbt commands | Coordinates dbt with ingestion and other systems |

## 4. Project anatomy

A typical certification practice project looks like this:

```text
retail_analytics/
|-- dbt_project.yml
|-- profiles.yml
|-- macros/
|-- models/
|   |-- sources.yml
|   |-- staging/
|   |-- intermediate/
|   `-- marts/
|-- seeds/
|-- snapshots/
|-- tests/
`-- target/              # generated; do not commit
```

### `dbt_project.yml`

This identifies the project, selects a profile, defines resource paths and applies
hierarchical configuration. A configuration at a more specific level normally
overrides a broader one.

```yaml
name: retail_analytics
version: "1.0.0"
config-version: 2
profile: retail_analytics

model-paths: ["models"]
test-paths: ["tests"]

models:
  retail_analytics:
    staging:
      +materialized: view
    intermediate:
      +materialized: ephemeral
    marts:
      +materialized: table
```

Configurations can also be placed in a model with `{{ config(...) }}` or, for many
resource properties, in YAML. Understand configuration precedence and prefer
consistent project-level defaults with model-level exceptions.

### Profiles and targets

The profile contains connection details and named targets such as development and
production. Never commit real passwords. Use environment variables or the dbt
platform's credential management.

```yaml
retail_analytics:
  target: dev
  outputs:
    dev:
      type: your_adapter
      host: "{{ env_var('DBT_HOST') }}"
      user: "{{ env_var('DBT_USER') }}"
      password: "{{ env_var('DBT_PASSWORD') }}"
      database: "{{ env_var('DBT_DATABASE') }}"
      schema: analytics_dev
      threads: 4
```

`target.name`, `target.schema` and other target attributes can be used carefully in
Jinja. Avoid embedding environment-specific behavior throughout model SQL when a
project configuration is clearer.

## 5. Sources, models and lineage

### Sources

Declare raw relations as sources rather than hard-coding database identifiers:

```yaml
version: 2

sources:
  - name: raw_sales
    schema: raw_sales
    tables:
      - name: orders
        description: Orders loaded from the operational commerce system.
        loaded_at_field: _loaded_at
        config:
          freshness:
            warn_after: {count: 25, period: hour}
            error_after: {count: 49, period: hour}
```

Reference the table with:

```sql
select * from {{ source('raw_sales', 'orders') }}
```

Benefits include lineage, source tests, freshness checks, documentation and the
ability to change physical names without editing every downstream model.

### `ref()`

Use `ref()` for another dbt model:

```sql
select * from {{ ref('stg_orders') }}
```

`ref()` resolves the correct database relation and creates a DAG dependency. A
hard-coded relation can compile as valid SQL while preventing dbt from knowing the
correct build order.

### `this`

`{{ this }}` is the current model's database relation. It is especially useful in an
incremental filter:

```sql
{% if is_incremental() %}
where refreshed_at >= (
    select coalesce(max(refreshed_at), timestamp '1900-01-01') from {{ this }}
)
{% endif %}
```

## 6. Model design and modularity

A good model has one clear purpose and an explicit grain. State the grain in the
description—for example, “one row per order.”

Common layers:

- **Staging:** light renaming, casting, standardization and source cleanup.
- **Intermediate:** reusable joins, pivots and business transformations.
- **Marts:** business-facing facts, dimensions and aggregates.

Good practices:

- use CTEs to make transformation stages readable;
- centralize repeated logic rather than copying it;
- avoid joining facts at incompatible grains;
- select explicit columns in stable interfaces;
- name models and columns consistently;
- keep business logic in models and reusable technical logic in macros;
- optimize SQL in the warehouse, not only the Jinja that produces it.

### Facts and dimensions

A dimension describes an entity; a fact records an event, measurement or snapshot.
Define keys and grain before joining. In a retail project, `dim_customer` is a
customer dimension, `fct_orders` is a transaction fact and
`fct_customer_balance_snapshot` is a periodic snapshot fact.

## 7. Materializations

Materialization determines how a model is represented in the data platform.

| Materialization | Use when | Main trade-off |
|---|---|---|
| `view` | Logic is light and freshness matters | Recomputed when queried |
| `table` | Fast reads and predictable rebuilds matter | Full rebuild cost |
| `incremental` | The table is large and only part changes | More complex correctness logic |
| `ephemeral` | Small reusable logic should be inlined | No physical relation; harder debugging |
| materialized view | Supported platform should maintain results | Adapter/platform-specific behavior |

### Incremental models

An incremental model must be correct on both its initial/full-refresh path and its
incremental path.

```sql
{{ config(
    materialized='incremental',
    unique_key='order_id',
    incremental_strategy='delete+insert'
) }}

with ranked as (
    select *,
           row_number() over (
               partition by order_id
               order by updated_at desc
           ) as row_rank
    from {{ ref('stg_orders') }}
    {% if is_incremental() %}
    where updated_at >= coalesce(
        (select max(updated_at) from {{ this }}),
        timestamp '1900-01-01'
    )
    {% endif %}
)
select * from ranked where row_rank = 1
```

Know these concerns:

- `unique_key` identifies records to update; it is not automatically a database
  uniqueness constraint;
- late-arriving or updated records require an overlap window or reliable watermark;
- filter early to reduce scanned data, but never before required logic would make
  the result incorrect;
- schema changes may require `on_schema_change` behavior or `--full-refresh`;
- strategy support varies by adapter;
- test idempotency by running the same input twice;
- use `dbt run --full-refresh -s model_name` only when a rebuild is intentional.

Incremental is not automatically better. For small tables, a table rebuild is often
simpler and safer.

### Ephemeral models

An ephemeral model compiles into dependent SQL as a CTE. It is useful for small,
reused transformations that do not need direct querying. Avoid long chains of
ephemeral models when compiled SQL becomes hard to understand or optimize.

## 8. Jinja, macros and packages

dbt uses Jinja to generate SQL. Common constructs:

```sql
{% set payment_methods = ['card', 'bank_transfer'] %}

select
    order_id,
    {% for method in payment_methods %}
    sum(case when payment_method = '{{ method }}' then amount else 0 end)
        as {{ method }}_amount{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('payments') }}
group by 1
```

A macro is a reusable function:

```sql
{% macro cents_to_currency(column_name, scale=2) %}
    round({{ column_name }} / 100.0, {{ scale }})
{% endmacro %}
```

Use it with `{{ cents_to_currency('amount_cents') }}`.

Know the difference between compile time and query runtime. Jinja executes while dbt
builds SQL; most SQL expressions execute later in the database. Use `run_query()` and
the `execute` flag cautiously because parse and execution phases differ.

Useful context/functions include:

- `ref()`, `source()` and `config()`;
- `var()` for project variables;
- `env_var()` for environment values and secrets;
- `target` for target metadata;
- `this` for the current relation;
- `is_incremental()` for the incremental execution condition.

### Packages

Declare packages in `packages.yml`, pin compatible versions, and run `dbt deps`.
Commit the package lock file when used by the supported dbt version so CI and local
development resolve the same dependency versions. Read release notes before upgrades.

## 9. Tests and data quality

Testing proves assumptions; it does not prove that every business rule is correct.
Choose tests based on model grain, business invariants and failure impact.

### Generic data tests

Built-in generic tests include `not_null`, `unique`, `relationships` and
`accepted_values`.

```yaml
models:
  - name: dim_customer
    description: One row per customer.
    columns:
      - name: customer_key
        data_tests:
          - not_null
          - unique
      - name: country
        data_tests:
          - accepted_values:
              arguments:
                values: [norway, sweden, denmark, finland]
```

Test a composite grain with a supported utility test or a custom generic test. A
separate `unique` test on each component is not equivalent to uniqueness of the
combination.

### Singular data tests

A SQL file under `tests/` returns failing rows. Zero returned rows means success:

```sql
select country, ticker, snapshot_date, count(*) as row_count
from {{ ref('fact_fundamental_snapshot') }}
group by 1, 2, 3
having count(*) > 1
```

### Custom generic tests

Use a test block when the same assertion applies to multiple resources:

```sql
{% test non_negative(model, column_name) %}
select *
from {{ model }}
where {{ column_name }} < 0
{% endtest %}
```

### Unit tests

Unit tests validate model SQL against small static inputs before materializing the
complete model. They are useful for conditional logic, date boundaries, window
functions and edge cases. Data tests validate resulting data in the platform; unit
tests isolate transformation logic.

### Test configuration

Understand:

- `severity`, `warn_if` and `error_if`;
- `where` to limit tested rows;
- `store_failures` for investigation;
- tags and selectors for test groups;
- testing sources as well as models;
- executing tests as part of `dbt build` and CI.

Filtering a test can reduce cost but also reduce coverage. Be explicit about which
period is protected by the assertion.

### Model contracts

A contract enforces the declared shape of a model, including column names and data
types. Constraints depend on platform support. Contracts protect interfaces; data
tests validate data-level assumptions. They complement rather than replace each other.

## 10. Documentation, freshness and exposures

Add descriptions to sources, models and columns in YAML. Use docs blocks for longer
reusable explanations. Generate and serve project documentation with:

```powershell
dbt docs generate
dbt docs serve
```

`dbt docs generate` creates metadata such as the manifest and catalog. Documentation
should explain purpose, grain, ownership, important calculations and limitations—not
merely repeat the column name.

### Source freshness

Run:

```powershell
dbt source freshness
```

Freshness compares a configured loaded-at timestamp with warning/error thresholds.
It answers “is source data recent enough?”; it does not replace correctness tests.

### Exposures

An exposure documents a downstream use such as a dashboard, application or ML
pipeline. It links consumers to upstream dbt nodes and adds ownership and lineage.
A business-intelligence dashboard, executive report or ML feature pipeline is a good
candidate for an exposure.

## 11. Governance

### Access

Model access controls who may reference a model:

- `private`: only within its group;
- `protected`: within its project or permitted project relationships;
- `public`: stable cross-project interface.

Do not confuse dbt model access with database privileges.

### Groups

Groups associate governed resources with owners. Use them to make stewardship and
domain boundaries explicit.

### Versions

Version a model when a breaking interface change requires old and new definitions to
coexist. Declare a latest version, migration period and deprecation date. Do not create
a new version for every non-breaking SQL implementation change.

### Contracts

Use contracts for stable, intentionally governed interfaces. Coordinate breaking
changes with model versions and downstream owners.

### Grants

The `grants` configuration instructs dbt to apply database permissions to built
relations. Grants control database access; `access` controls dbt referenceability.
Know which layer is responsible for each requirement.

## 12. Commands to master

| Command | Purpose |
|---|---|
| `dbt debug` | Validate project, profile and connection setup |
| `dbt parse` | Parse project and write metadata without warehouse execution |
| `dbt compile` | Render executable SQL into `target/` |
| `dbt run` | Build selected models |
| `dbt test` | Execute selected data and unit tests |
| `dbt build` | Build selected resources in DAG order, including tests |
| `dbt seed` | Load CSV seed files |
| `dbt snapshot` | Execute snapshot resources |
| `dbt source freshness` | Evaluate source freshness |
| `dbt docs generate` | Generate catalog and documentation artifacts |
| `dbt deps` | Install declared packages |
| `dbt clean` | Remove configured generated directories |
| `dbt run-operation` | Invoke a macro as an operation |
| `dbt clone` | Create zero-copy/metadata clones where supported |
| `dbt retry` | Retry failed nodes from a previous invocation |

Important distinction:

- `dbt run` runs models.
- `dbt test` runs tests.
- `dbt build` processes selected seeds, snapshots, models and tests in DAG order.
- A failed upstream test can prevent downstream nodes in `dbt build`, depending on
  dependency and test placement.

Typical local commands:

```powershell
dbt debug
dbt deps
dbt build
dbt docs generate
```

## 13. Node selection

Selection can use names, paths, tags, packages, configurations, source names, state
and prior results. Graph operators are essential:

```text
model_name+      model and descendants
+model_name      model and ancestors
+model_name+     model, ancestors and descendants
@model_name      model, descendants, and ancestors needed to build descendants
```

Examples:

```powershell
dbt build --select dim_customer
dbt build --select +fct_orders
dbt test --select tag:critical
dbt build --select path:models/marts
dbt build --exclude resource_type:snapshot
```

Spaces commonly express union; commas commonly express intersection within a
selection expression. Quote complex selectors in shells so the shell does not
interpret special characters.

Use a `selectors.yml` file for named, reviewed selection policies rather than copying
complex expressions into every job.

## 14. State, artifacts and slim CI

dbt writes artifacts under `target/`. Know the role of:

- `manifest.json`: graph, parsed resources and configuration;
- `run_results.json`: execution status, timing and adapter response;
- `sources.json`: source freshness results;
- `catalog.json`: warehouse metadata used by generated docs.

`--state PATH` points to artifacts from a comparison run, often production. State
selectors compare the current project with that prior manifest:

```powershell
dbt build --select state:modified+ --state .\prod-artifacts
```

The trailing `+` includes downstream dependants. Choose it intentionally.

Result selectors use a previous run's outcomes:

```powershell
dbt build --select result:error+ --state .\previous-run
dbt retry
```

### Deferral

With `--defer`, unresolved upstream references in a development environment can point
to relations represented by the state manifest. This enables slim CI without
rebuilding all production ancestors.

```powershell
dbt build `
  --select state:modified+ `
  --state .\prod-artifacts `
  --defer
```

State is metadata, not magic data comparison. Understand which manifest is being used,
whether relations exist, and whether environment-specific logic changes parsing.

## 15. Debugging models

Use a repeatable sequence:

1. Read the first meaningful error, node name and database message.
2. Run the smallest failing selection.
3. Run `dbt compile` and inspect compiled SQL under `target/compiled/`.
4. Decide whether the failure occurs during parsing, compilation, database execution,
   a test, or orchestration.
5. Execute compiled SQL directly when warehouse behavior is unclear.
6. Check data types, privileges, relation names and target schema.
7. Fix the cause, add a regression test and rerun the node plus affected descendants.

Common error categories:

| Stage | Typical cause |
|---|---|
| Profile/connection | Wrong target, credentials, host, role or database |
| Parsing | Invalid project/YAML structure, duplicate resources |
| Compilation | Undefined `ref`, source, macro or variable; malformed Jinja |
| SQL execution | Warehouse syntax, cast, permission or data error |
| Test | Broken data assumption or incorrectly scoped assertion |
| Pipeline | Stale artifacts, failed dependency, orchestration or integration issue |

YAML indentation matters. Use spaces, validate nesting against the resource schema and
avoid putting a valid property at the wrong level.

## 16. Pipelines and deployment

A reliable deployment usually separates:

- developer schemas from production schemas;
- pull-request CI from scheduled production jobs;
- credentials and permissions by environment;
- ingestion from transformation while preserving dependencies;
- generated artifacts from source code.

Pipeline design questions:

- Which command should run: `build`, `run`, `test` or a selected combination?
- What is the fail-fast and retry policy?
- Should downstream nodes run after a test failure?
- Are source freshness checks scheduled before transformation?
- Which artifacts must be retained for state comparison and debugging?
- Is the job idempotent?
- Can a full refresh be performed safely and deliberately?

An external orchestrator can coordinate ingestion and dbt transformations. dbt remains
responsible for SQL lineage, model execution, tests and artifacts; the orchestrator is
responsible for higher-level scheduling, event handling and cross-system dependencies.

## 17. Seeds, snapshots, analyses and Python models

### Seeds

Seeds load small, version-controlled CSV files. Appropriate examples are stable code
mappings or small reference lists. They are not intended for large or sensitive raw
datasets.

### Snapshots

Snapshots preserve changes to mutable source rows, commonly as slowly changing
dimension type 2 history. Understand unique keys, timestamp versus check strategies,
and why an unstable key corrupts history.

### Analyses

Analyses compile SQL but are not materialized as models. They are suitable for ad hoc
or audited analytical queries that should live with the project.

### Python models

Python models run on supported data platforms and use a Python dataframe API. They
participate in the DAG and use `dbt.ref()`/`dbt.source()`. Use SQL when SQL is the
clearest tool; choose Python for transformations that genuinely benefit from it.
Platform capabilities and supported materializations vary.

## 18. Performance and cost

Optimization starts with correctness and measurement.

- Filter large inputs early when semantics allow it.
- Select only required columns.
- Avoid accidental many-to-many joins.
- Examine warehouse query plans and scan volume.
- Increment only when a reliable changed-data strategy exists.
- Partition/cluster/index according to the target platform and workload.
- Use state-based CI to avoid unnecessary builds.
- Keep tests valuable and scope expensive tests deliberately.
- Do not materialize every intermediate model as a table by habit.

dbt controls generated SQL and build selection, while the data platform executes and
optimizes SQL. Diagnose the correct layer.

## 19. Exam decision patterns and common traps

1. **Hard-coded relation versus `ref()`** — choose `ref()` for dbt models so the DAG
   and environment resolution work.
2. **Raw table versus `source()`** — declare and reference sources for lineage,
   freshness and tests.
3. **`run` versus `build`** — `run` is model-focused; `build` includes multiple
   resource types and tests in DAG order.
4. **Contract versus data test** — a contract protects shape; a test validates a data
   assertion.
5. **Access versus grants** — access governs dbt references; grants govern database
   permissions.
6. **Incremental versus table** — incremental is valuable only when changed rows can
   be selected correctly and the saved compute justifies complexity.
7. **`unique_key` misconception** — it supports incremental matching but does not by
   itself guarantee database uniqueness.
8. **State misconception** — state compares project artifacts, not arbitrary table
   contents.
9. **Freshness versus test** — freshness measures recency; tests measure assertions.
10. **Jinja versus SQL timing** — Jinja renders first; SQL executes in the platform.
11. **Model versioning** — reserve versions for breaking interface changes.
12. **Compiled SQL** — inspect it whenever generated SQL or adapter behavior is in
    doubt.

## 20. Certification practice lab

Build a small, platform-neutral retail project. Use three raw inputs:

| Source table | Grain | Essential columns |
|---|---|---|
| `raw_sales.customers` | One row per customer | `customer_id`, `name`, `created_at`, `_loaded_at` |
| `raw_sales.orders` | One row per order | `order_id`, `customer_id`, `status`, `ordered_at`, `updated_at`, `_loaded_at` |
| `raw_sales.payments` | One row per payment attempt | `payment_id`, `order_id`, `amount`, `payment_method`, `updated_at` |

Build this target DAG:

```text
source:customers -> stg_customers ---------------------> dim_customers
                                                               |
source:orders ----> stg_orders ---> int_order_payments ---> fct_orders
                                      ^                        |
source:payments --> stg_payments -----|                        v
                                                        exposure:dashboard
```

Complete the labs without copying a finished project. Use a feature branch and a
separate development target.

### Lab 1 — Project and DAG

1. Initialize a project and configure a development target.
2. Declare all three sources with descriptions and freshness for suitable tables.
3. Build staging models using `source()`.
4. Build intermediate and mart models using `ref()`.
5. Generate docs and verify the predicted lineage.

**Mastery check:** You can explain every edge and predict build order.

### Lab 2 — Materializations and incremental correctness

1. Use views for staging, an ephemeral or view intermediate model, and tables for
   small dimensions.
2. Configure `fct_orders` as incremental with `order_id` as its unique key.
3. Handle updated and late-arriving orders with an overlap window.
4. Run identical input twice and prove idempotency.
5. Compare incremental output with a full refresh.

**Mastery check:** You can justify every materialization and identify records that a
bad watermark would miss.

### Lab 3 — Test strategy

Add and run:

- not-null and unique tests for primary business keys;
- accepted values for order status;
- relationships from orders to customers and payments to orders;
- a singular test for duplicate mart grain;
- a custom generic test for non-negative payments;
- a unit test for order-status or payment aggregation logic.

**Mastery check:** Every test maps to a named assumption, grain or edge case.

### Lab 4 — Documentation and governance

Add:

- model purpose, grain, owner and column descriptions;
- a contract on one stable mart;
- a group and intentional access level;
- database grants appropriate to an analyst role;
- an exposure for a fictional revenue dashboard;
- a version/migration design for a breaking column change.

**Mastery check:** You can distinguish documentation, contracts, versions, access and
grants without treating them as interchangeable.

### Lab 5 — Break and debug

Deliberately create and diagnose:

1. an invalid profile/target;
2. a misspelled `ref()`;
3. malformed YAML;
4. malformed Jinja;
5. valid compiled SQL with a data-platform cast error;
6. a failing relationship test;
7. a downstream node skipped after an upstream failure.

For each, identify its lifecycle stage, relevant log/artifact and smallest safe rerun.

### Lab 6 — Selection

Predict and compare the results of:

```powershell
dbt ls --select dim_customers+
dbt ls --select +fct_orders
dbt ls --select path:models/marts
dbt ls --select tag:critical
```

Create a named selector for critical marts and their required ancestors.

### Lab 7 — State-aware CI

1. Preserve a successful production `manifest.json`.
2. Change `int_order_payments` on a feature branch.
3. Compare `state:modified`, `state:modified+` and a result selector.
4. Run a deferred build in an empty development schema.
5. Explain which upstream relations came from production state.
6. Simulate a failed node and use `dbt retry` appropriately.

**Mastery check:** You can identify the exact manifest, selected nodes and deferred
relations before execution.

## 21. Six-week study plan

Assume 7–10 focused hours each week.

### Week 1 — Foundation

- Complete dbt Fundamentals.
- Review SQL CTEs, joins, windows and Git workflow.
- Build the neutral retail practice project and map its DAG.
- Master `debug`, `compile`, `run`, `test` and `build`.

### Week 2 — Modeling

- Practice sources, `ref()`, staging and marts.
- Compare materializations.
- Build and validate an incremental model.
- Refactor one long query into modular models.

### Week 3 — Tests and documentation

- Write generic, singular, custom generic and unit tests.
- Configure freshness.
- Document grain, columns and ownership.
- Add an exposure.

### Week 4 — Advanced development and governance

- Practice Jinja, macros, packages and snapshots.
- Study contracts, access, groups, versions and grants.
- Review Python model purpose and limitations.

### Week 5 — Debugging, pipelines and state

- Diagnose deliberate parse, compile, SQL and test failures.
- Practice graph selectors.
- Build a state/defer workflow.
- Interpret `manifest.json` and `run_results.json`.

### Week 6 — Exam readiness

- Complete all certification labs without notes.
- Take timed original practice questions.
- Revisit weak domains in current official docs.
- Practice 65 questions in 120 minutes.
- Confirm current exam policies and system requirements.

## 22. Original practice questions

These questions are written for this guide and are not copied from the exam.

### Questions

1. A model selects from another dbt model using a hard-coded production schema. What
   should replace the relation and why?
2. Which command builds models and runs tests in DAG order?
3. A table has one row per `country`, `symbol` and `snapshot_date`. Is a unique test on
   `symbol` correct?
4. What two conditions must be true for an incremental model to save compute safely?
5. What does `{{ this }}` mean?
6. A model's compiled SQL is valid, but execution reports a warehouse type mismatch.
   Is this primarily parsing, compilation or database execution?
7. When should a model receive a new version?
8. What is the difference between model `access` and `grants`?
9. Which feature checks whether source data arrived recently?
10. What does `state:modified+` add beyond `state:modified`?
11. Why can a successful `dbt compile` still be followed by a failed `dbt run`?
12. When is an ephemeral model a poor choice?
13. What does a singular data test return when it fails?
14. Does `unique_key` automatically create a database uniqueness constraint?
15. Which artifact records node execution results?
16. What is the purpose of `--defer`?
17. Why should package versions be pinned?
18. A dashboard depends on three mart models. Which dbt resource documents this
    consumer?
19. What is the main risk of filtering an incremental model only after a large join?
20. Why is a source freshness check not a substitute for a data test?

### Answers

1. Use `ref()` so dbt resolves the environment-specific relation and records the DAG
   dependency.
2. `dbt build`.
3. No. The asserted grain is the composite of all three columns.
4. The changed rows can be selected correctly, and processing only those rows saves
   enough work to justify the added complexity.
5. The database relation represented by the currently executing model.
6. Database execution.
7. For a breaking public-interface change that requires a migration window.
8. `access` controls dbt references; `grants` controls database privileges.
9. Source freshness.
10. Descendants of modified nodes.
11. Compile does not execute warehouse SQL or expose runtime data, type, permission or
    platform errors.
12. When inlined SQL becomes large, repeatedly duplicated or difficult to debug and
    optimize.
13. The rows that violate the assertion.
14. No.
15. `run_results.json`.
16. To resolve eligible unbuilt upstream references to relations represented by a
    state manifest, often production relations in slim CI.
17. To make dependency resolution repeatable and avoid unreviewed breaking changes.
18. An exposure.
19. The warehouse may process the full expensive join before reducing changed rows.
20. Freshness evaluates recency; a test evaluates a specified data invariant.

## 23. Readiness checklist

You are ready when you can do all of the following without guessing:

- explain how source, model and test nodes form a DAG;
- choose an appropriate materialization and defend the trade-off;
- write an incremental model that handles updates and late data;
- distinguish `run`, `test`, `build`, `compile`, `retry` and `clone`;
- write generic, singular, custom generic and unit tests;
- configure and explain source freshness;
- inspect compiled SQL and classify failure stages;
- use ancestors, descendants, path, tag, state and result selectors;
- explain manifests, run results, state and deferral;
- use Jinja/macros without confusing compile time and query runtime;
- distinguish contracts, tests, versions, access and grants;
- maintain packages and external dependencies reproducibly;
- explain Git branch, pull request and CI practices;
- complete the hands-on labs in a clean development target;
- sustain the target exam pace of roughly 1 minute 50 seconds per question.

## 24. Official resources

Use official material as the final authority:

- [Analytics Engineering Certification exam](https://www.getdbt.com/certifications/analytics-engineer-certification-exam)
- [Official Analytics Engineering study guide (PDF)](https://www.getdbt.com/assets/uploads/dbt_certificate_study_guide.pdf)
- [dbt certification overview](https://www.getdbt.com/dbt-certification)
- [dbt Developer Hub](https://docs.getdbt.com/)
- [dbt command reference](https://docs.getdbt.com/reference/dbt-commands)
- [Models](https://docs.getdbt.com/docs/build/models)
- [Sources](https://docs.getdbt.com/docs/build/sources)
- [Materializations](https://docs.getdbt.com/docs/build/materializations)
- [Incremental models](https://docs.getdbt.com/docs/build/incremental-models)
- [Data tests](https://docs.getdbt.com/docs/build/data-tests)
- [Unit tests](https://docs.getdbt.com/docs/build/unit-tests)
- [Documentation](https://docs.getdbt.com/docs/collaborate/documentation)
- [Model governance](https://docs.getdbt.com/docs/mesh/govern/model-governance)
- [Node selection](https://docs.getdbt.com/reference/node-selection/syntax)
- [State selection](https://docs.getdbt.com/reference/node-selection/methods#the-state-method)
- [Artifacts](https://docs.getdbt.com/reference/artifacts/dbt-artifacts)
- [dbt Learn course catalog](https://learn.getdbt.com/catalog)

## 25. Building the HTML guide

The documentation workflow builds and publishes this page as HTML automatically when
changes reach `main`. To build locally from the documentation project root:

```powershell
python -m pip install mkdocs
python -m mkdocs build --strict --clean
```

Open the generated file:

```text
site/dbt-analytics-engineering-certification/index.html
```

To preview with live reload:

```powershell
python -m mkdocs serve
```

Then open `http://127.0.0.1:8000/` and select the certification guide in the
navigation.
