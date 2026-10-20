# Data contract: tier-1 marts and tier-2 query templates

Status: the **Watchdog Desk marts (section 10) are verified**: every published card was checked against an
independent query of the source data (2026-10-17), and the 2026-10-20 change (`verified_in` set to NULL, one reason
code renamed) was checked again. Built from `data/fedspend.duckdb` (accounts through FY2026 P11; awards through
2026-10-13; snapshot `data_as_of` 2026-10-16 03:03 UTC). Sections 1–9 were written for the v1 marts (2026-10-15,
revised 2026-10-16: outlier default, award component rule 5, listing map, `__NO_UEI__`, review-tier flag,
`mart_data_issues` per metrics.md section 11).

> **Scope of the public repository.** The public repository ships only the Watchdog Desk pipeline: the files listed
> in section 10 (`sql/marts/00_setup`, `35_subaward_base`, `40_awards`, `50_subawards`, `60_fiscal_years`,
> `75_new_awards`, `sql/desk/`, `sql/checks/reconcile_desk.sql` and the seeds they read) and the published desk
> files. The sections on the v1 marts (1–7 and 9), the tier-2 API templates (8) and the prototype concept and v2
> marts (Appendix P) describe parts that aren't included; they are kept for reference. A full build there still
> writes the award, sub-award and fiscal-year marts of sections 4, 5 and 6.1, which the site doesn't read.

The site reads **only** the files that section 10 lists. Metric definitions are in
`docs/metrics.md` (section numbers below, such as "M4.1", point there).

---

## 1. Defaults the dashboard uses (adopted 2026-10-15)

Every alternative is still in the marts as a column or flag. These are the **defaults**:

| # | Topic | Default | How to get it from the marts | Alternative kept |
|---|---|---|---|---|
| D1 | Headline account totals | **File A** (`obligations_a`, `outlays_a`) | `mart_agency_fy_summary` | File B (`obligations_b`, `outlays_b`) via the A/B toggle (M4.5) |
| D2 | File B breakdowns (object class, program activity) | **Sign-corrected File B plus a residual reconciling row (treatment (a), M5.3)** | use `*_b_corr` columns of `mart_file_b_breakdown`, **all** rows including `row_type = 'reconciling'` | as reported (treatment (b)): use `*_b` columns, all rows |
| D3 | Sub-award outliers | **Exclude all rule-flagged sub-awards**: filter `NOT is_outlier` (17 DOJ rows, $18.33B; since 2026-10-16), with a visible note | `mart_subaward_summary`, `mart_subaward_flows` | toggle "include" = no filter, which matches USAspending |
| D4 | Sub-award duplicate reports (Option A, since 2026-10-16) | **Exclude re-submitted copies**: filter `NOT is_resubmitted_duplicate` (7,790 DOJ rows, $1,118,339,862.09). Same-month copies and near-duplicates (`is_possible_duplicate`, 3,027 rows, $507,439,281.71) stay **flagged and counted** | `mart_subaward_summary`, `mart_subaward_flows` | toggle "Include duplicate sub-award reports (matches USAspending)" = drop the filter. It is independent of the D3 toggle; with both on, totals match USAspending to the cent |
| D5 | State | **Recipient location** (`recipient_state`; sub-awards `sub_state`) | | place of performance (`pop_state`; sub-awards `sub_pop_state`) |
| D6 | Award agency definition | **Awarding** (`definition = 'awarding'`) | filter every award/sub-award mart on `definition` | `definition = 'funding'` |
| D7 | Component map and object class groups | **metrics.md 5.1 and 6.1 as written** (accepted) | `component_group`, `component`, `oc_group_key` | none |
| D8 | Intra-agency flows (WCF, RECA payment to trust fund) | **Not netted out** | | none in v1 |

**Never sum across `definition`.** A transaction both awarded and funded by the agency is a
row under each definition.
**Never add obligations to outlays**, and never add sub-award amounts to prime obligations.

## 2. Files, build, size

```
marts/dim_agency.parquet                    global: one row per toptier agency
marts/<agency_code>/<mart>.parquet          everything else, one directory per agency
```

Every agency-scoped mart has `agency_code` (3-digit text, e.g. `'015'`) and
`fiscal_year` (INTEGER), so government-wide data is just more directories / rows.

Build (repo root, `.venv` active). Opens the database read-only; writes only `marts/`:

```
python sql/build_marts.py                      # all agencies in the database (~25 s for DOJ)
python sql/build_marts.py --agency 015 --check # one agency, then the reconciliation checks
python sql/build_marts.py --check-only         # checks against existing marts
```

The runner attaches `data/fedspend.duckdb` READ_ONLY to an in-memory DuckDB, sets
`SET VARIABLE agency = '<code>'`, runs `sql/marts/0*-7*.sql` in order, writes each
`mart_*` / `account_ab_reconciliation` table to Parquet (ZSTD), then runs
`sql/marts/90_dim_agency.sql`. It fails (exit 1) if a mart is over 5 MB or an agency over 50 MB. Builds are **reproducible**: the runner uses one DuckDB thread and writes every mart sorted on all columns (`ORDER BY ALL`), so the same data gives byte-identical files (same SHA-256). Row order in a file carries no meaning; sort in your query.
Seeds are CSVs in `sql/seeds/` (section 6).
Optional parts are skipped with a printed note when their files are absent: the prototype concept and v2 layer (Appendix P) when `sql/v2/` is absent, `dim_agency` when `90_dim_agency.sql` is absent, and any check whose inputs are absent. `sql/marts/75_new_awards.sql` builds in-memory inputs for the Watchdog Desk (section 10) and exports nothing.

Sizes, agency 015 (budget: < 5 MB per mart, < 50 MB per agency):

| File | Rows | Size |
|---|---:|---:|
| mart_subaward_flows | 177,524 | 2.56 MB |
| mart_award_recipients | 212,580 | 3.47 MB |
| mart_awards | 126,178 | 1.50 MB |
| mart_file_b_breakdown | 23,671 | 0.51 MB |
| mart_subaward_summary | 24,263 | 0.14 MB |
| mart_data_issues | 11,088 | 0.25 MB |
| account_ab_reconciliation | 2,057 | 0.11 MB |
| mart_federal_account | 502 | 43 KB |
| mart_component | 291 | 30 KB |
| mart_subaward_outliers | 86 | 11 KB |
| mart_agency_fy_summary | 10 | 8 KB |
| mart_award_component_lookup | 548 | 7 KB |
| mart_file_b_sign_flips | 12 | 4 KB |
| mart_negative_detail_tas | 2,488 | 43 KB |
| mart_fiscal_years | 11 | 3 KB |
| mart_award_coverage | 42 | 3 KB |
| **Total marts/015/** | | **7.7 MB** (sorted exports; per-mart sizes above are from the unsorted build and are now slightly smaller) |
| marts/dim_agency.parquet | 111 | 7 KB |

Types: money is DOUBLE, nominal dollars, full precision (round only for display, M1).
Counts are INTEGER (not BIGINT, to avoid BigInt in DuckDB-WASM). `data_as_of` is a UTC
TIMESTAMP (the snapshot's `fetched_at`). Rates are fractions (0.648, not 64.8).

---

## 3. Account marts (File A and File B)

Common to all account marts: one FYTD snapshot per FY, the latest period
(`latest_period`); sums are across accounts, never across periods (M1). Scope = Treasury
accounts owned by the agency. FY2027 has no account data, so it has no rows here.

Shared columns (where present):

| Column | Type | Unit | Meaning |
|---|---|---|---|
| agency_code | VARCHAR | | toptier code |
| fiscal_year | INTEGER | | submission FY |
| latest_period | INTEGER | | 1-12; < 12 means provisional |
| period_end_date | DATE | | last day of `latest_period` |
| is_provisional | BOOLEAN | | `latest_period < 12` (M2.3) |
| component_group, component | VARCHAR | | account-side component by federal account (M6.1, seed `component_map.csv`). Label charts "Component (by federal account)" |
| total_budgetary_resources | DOUBLE | $ | File A TBR (M3.1) |
| unobligated_balance | DOUBLE | $ | File A (M3.5) |
| obligations_a / outlays_a | DOUBLE | $ | File A obligations incurred / gross outlays (M3.2, M3.3) |
| obligations_b / outlays_b | DOUBLE | $ | sum of File B as reported (M4.1) |
| obligations_b_corr / outlays_b_corr | DOUBLE | $ | File B with registered sign flips reversed (M5.3 (a)) |
| obligations_gap / outlays_gap | DOUBLE | $ | A - B as reported (M4.1); equals the treatment (b) reconciling amount |
| obligations_residual / outlays_residual | DOUBLE | $ | A - B corrected; the treatment (a) residual. Signed; can be negative |
| execution_rate | DOUBLE | fraction | `obligations_a / TBR`, ratio of sums (M3.4). Always File A |
| *_gap_called_out, *_residual_called_out | BOOLEAN | | materiality rule M4.4: `abs(diff) >= 0.5% * abs(File A)` AND `abs(diff) >= $1M` |
| n_sign_corrected_tas | INTEGER | | TAS in scope with a registered flip for either measure (M5.3) |
| data_as_of | TIMESTAMP | UTC | snapshot time |

### 3.1 `mart_agency_fy_summary` (Overview)

- **Path:** `marts/<agency>/mart_agency_fy_summary.parquet`
- **Grain:** agency x fiscal_year (one row; wide, not one row per source).
- **Supports:** M3.1-3.5, M4.1-4.5, the residual for M5.3.
- **Extra columns:**

| Column | Type | Meaning |
|---|---|---|
| period_label | VARCHAR | exact M2.4 label: `FY2025`, `FY2026 (through P11, Aug 2026)` |
| obligations_gap_pct, outlays_gap_pct | DOUBLE | gap / abs(File A) (fraction) |
| execution_rate_b | DOUBLE | `obligations_b / TBR`; tooltip-only secondary (M3.4) |
| top_obligations_gap_tas, top_outlays_gap_tas | VARCHAR | footnote text: top 3 TAS by abs(gap), `"<TAS> +123.4M; ..."` (contributions >= $0.5M) |
| top_obligations_residual_tas, top_outlays_residual_tas | VARCHAR | same for the residual (default footnote under D2) |

DOJ values reproduce M4.3 and M5.3: e.g. FY2025 `obligations_a` 51,478.9M, `obligations_b`
50,456.4M, gap 1,022.5M, residual 0.0M; FY2018 residual 885.8M (obligations) / 2,174.8M (outlays).

### 3.2 `mart_component` ("Where it goes": by component)

- **Grain:** agency x FY x component_group x component.
- **Basis:** **File A** for the headline (`obligations_a`, `outlays_a`, TBR, `execution_rate`).
  The File B, sign-corrected File B, gap and residual columns are alongside for the toggle
  and the reconciliation row. Component is defined by **federal account** (M6.1), so the
  same TAS set is used on both sides.
- **Extra columns:** `n_federal_accounts`, `top_obligations_residual_tas`, `top_outlays_residual_tas`.

### 3.3 `mart_federal_account` ("Where it goes": by federal account)

- **Grain:** agency x FY x federal_account_symbol. Basis as 3.2.
- **Extra columns:** `federal_account_symbol` (e.g. `015-0200`), `federal_account_name`,
  `n_tas`, `usaspending_url` (`https://www.usaspending.gov/federal_account/<symbol>`, M9).

### 3.4 `account_ab_reconciliation` (TAS level; M4.1)

- **Grain:** agency x FY x treasury_account_symbol. FULL OUTER JOIN of File A and File B at
  TAS level, so a TAS in only one file shows as gap.
- Every account mart above is a roll-up of this table.
- **Extra columns:** `treasury_account_symbol`, `treasury_account_name`,
  `federal_account_symbol`, `federal_account_name`, `in_file_a`, `in_file_b` (BOOLEAN),
  `sign_corrected_obligations`, `sign_corrected_outlays`, `sign_corrected` (registered flip
  applied), `flip_candidate_obligations`, `flip_candidate_outlays` (the M5.3 detection
  rule; proposes register entries, corrects nothing).
- **Use:** tooltips listing TAS-level contributions when a scope has mixed signs (M5.3
  display rule 4), and the A-vs-B footnotes.

### 3.5 `mart_file_b_sign_flips` (register, for the visible note)

- **Grain:** agency x FY x TAS x measure (`'obligations'` | `'outlays'`). From seed
  `sql/seeds/file_b_sign_flips.csv` (verified pairs only).
- **Columns:** `treasury_account_symbol`, `treasury_account_name`, `federal_account_symbol`,
  `federal_account_name`, `component`, `measure`, `verified_by`, `verified_on` (DATE),
  `evidence`, `amount_a`, `amount_b_as_reported`, `amount_b_corrected` ($).
- **Use:** the mandatory note under D2: "Sign corrected: [federal_account_name]
  reported [measure] with reversed sign in File B for FY[y]; shown here with the sign
  reversed back to match File A." Show it on every chart/table/export whose scope and FY
  include a row here.

### 3.6 `mart_file_b_breakdown` (object class and program activity)

- **Grain:**
  - `row_type = 'detail'`: agency x FY x federal account x program activity
    (`program_activity_code`, `program_activity_reporting_key`) x `object_class_code` x
    `direct_or_reimbursable`.
  - `row_type = 'reconciling'`: agency x FY x federal account (one row where any
    difference is non-zero; File B dimension columns are NULL).
- **Measures:**

| Column | detail rows | reconciling rows |
|---|---|---|
| obligations_b / outlays_b | File B as reported | A - B as reported (treatment (b) row) |
| obligations_b_corr / outlays_b_corr | File B sign-corrected | A - B corrected (treatment (a) residual) |

  So for any scope (agency, component, federal account) and FY:
  `sum(*_b_corr)` over all rows = `sum(*_b)` over all rows = File A; `sum(*_b)` over
  detail rows = File B as reported.
- **Other columns:**

| Column | Type | Meaning |
|---|---|---|
| program_activity_code, program_activity_name | VARCHAR | NULL for every FY2026 row (M5.2): use `program_activity_reporting_key` (PARK) for FY2026. Show program activity one FY at a time; key on (federal_account_symbol, program_activity_code) |
| program_activity_reporting_key | VARCHAR | PARK (FY2026+). `program_activity_name` is one deterministic spelling per (FY, federal account, code, PARK): where the source has several (e.g. code 0000), the spelling with the largest absolute obligations, then the alphabetically first |
| object_class_code, object_class_name | VARCHAR | e.g. `11.1`; level 3 |
| oc_group_key | VARCHAR | M5.1 level 1: `payroll`, `contracts`, `grants` (41.0 only), `other` (42-44, 9x), `unknown` (00.0/NULL/unmatched), `reconciling` |
| oc_group_label | VARCHAR | `Payroll & benefits`, `Contracts, services & purchases`, `Grants`, `Other`, `Unknown object class`, `Other difference from account totals` |
| oc_major_code, oc_major_label | VARCHAR | M5.1 level 2 (OMB major class 1/2/3/4/9/0); `4` = "Grants & fixed charges" includes 42-44. Do not confuse with the `grants` group |
| direct_or_reimbursable | VARCHAR | `D`, `R` or NULL |
| sign_corrected_obligations, sign_corrected_outlays, sign_corrected | BOOLEAN | a registered flip was applied to this row |
| has_negative_detail | BOOLEAN | this row's corrected obligations or outlays are negative (M5.4) |
| has_negative_detail_as_reported | BOOLEAN | same on as-reported values |
| negative_detail_tas | VARCHAR | TAS whose net contribution to this row is negative (corrected values), comma-separated |

- **Rules for the frontend (M5.3 display rules):**
  1. Show the reconciling row **only when no File B dimension is filtered** (all object
     classes, all program activities, D and R). Otherwise hide it and footnote "File B
     detail; does not reconcile to the File A total."
  2. Reconciling row label by sign of the scope sum, under D2: positive → "Not in File B
     detail (reported as $0 or lower)"; negative → "File B detail exceeds account totals".
     Under (b): "Difference from account totals (not reported, or reported with reversed
     sign, in File B)". Always last, grey/hatched; shown when `abs >= $0.5M`.
  3. **Groups are signed sums. Never floor at zero, never take abs.** Example: DOJ FY2026
     `other` = **-$1,504.2M** (42.0 RECA offsets) and `unknown` = +$6,548.2M; both carry
     the "FY2026 includes offsetting RECA entries" note. A check enforces this (section 7).
  4. When File B is the primary series (A/B toggle), the headline is the uncorrected
     File B sum (`mart_agency_fy_summary.obligations_b`) under either treatment.

DOJ FY2025 obligations ($M) reproduce M5.1: payroll 22,557.1; contracts 21,766.4; grants
3,498.9; other + unknown 2,634.1; reconciling (b) 1,022.5; total 51,478.9 = File A. Under
(a) payroll 22,857.5, contracts 22,488.5, residual 0.0.

---

### 3.7 `mart_negative_detail_tas` (accounts behind "Includes offsetting negative detail")

- **Path:** `marts/<agency>/mart_negative_detail_tas.parquet`. Added 2026-10-16.
- **Grain:** agency x FY x measure (`obligations` | `outlays`) x `oc_group_key` x
  `treasury_account_symbol`. One row for every TAS that has negative detail in that object
  class group for that measure.
- **Definition of negative detail:** the same as `mart_file_b_breakdown.has_negative_detail`.
  A TAS has negative detail in a cell when its net **sign-corrected** amount in that cell is
  below zero; a cell is (federal account, program activity code, PARK, object class,
  direct/reimbursable). Here it is evaluated for **one measure at a time**. The TAS sets
  (either measure) equal the TAS listed in `negative_detail_tas` for the group.
- **Columns:**

| Column | Type | Meaning |
|---|---|---|
| agency_code, fiscal_year | VARCHAR, INTEGER | |
| measure | VARCHAR | `obligations` or `outlays` |
| oc_group_key | VARCHAR | M5.1 group (`payroll`, `contracts`, `grants`, `other`, `unknown`) |
| treasury_account_symbol | VARCHAR | the TAS |
| federal_account_symbol, federal_account_name, component_group, component | VARCHAR | for scope filters |
| neg_amount | DOUBLE $ | sum of the TAS's negative cells in the group for the measure, rounded to cents (negative) |
| most_negative_cell | DOUBLE $ | its single most negative cell |
| n_negative_cells | INTEGER | number of negative cells |
| rank_in_group | INTEGER | 1 = most negative `neg_amount` at **agency scope**; ties broken by TAS |
| data_as_of | TIMESTAMP | |

- **Use:** for the note on the measure shown, take `WHERE fiscal_year = ? AND measure = ? AND
  oc_group_key = ?`, `ORDER BY neg_amount, treasury_account_symbol`, and name the first N.
  At agency scope that is `rank_in_group`. For a component or federal-account scope, filter
  first and re-order the same way (don't reuse `rank_in_group`).
- **DOJ check values:** FY2017 obligations `unknown` starts with 015-2017/2017-0128-000,
  015-2017/2017-0322-000, 015-X-0322-000. FY2019 starts with 015-X-4526-000,
  015-2019/2019-1060-000, 015-2018/2018-1060-000.
- Program activity views have no negative-detail note, so there is no program-activity
  version. Ask if one is needed.

## 4. Award marts (prime awards, D1/D2)

Source: `prime_transactions`. Award FY = FY of `action_date` (M2.1). Amount =
`federal_action_obligation` (net, M7.1). Shared columns:

| Column | Type | Meaning |
|---|---|---|
| definition | VARCHAR | `awarding` (`awarding_agency_code = agency_code`) or `funding` (`funding_agency_code = agency_code`) (M7.1). Label every award chart "Awarding agency: X" / "Funding agency: X" |
| is_partial_year | BOOLEAN | snapshot date falls inside the FY (DOJ: FY2027). Exclude from trends by default; selectable in the explorer (M2.5) |
| is_provisional | BOOLEAN | partial, or FY ended < 90 days before the snapshot (DOJ: FY2026, FY2027) (M2.3) |
| component | VARCHAR | award-side component (M6.2). Assistance by awarding office (OVW, COPS, OJP), else by sub-agency. A NULL office is resolved by (1) the award's latest non-null office, then (2) the assistance listing via seed `listing_office_map.csv`, then (3) the sub-agency's component with `program_office = 'OJP (office not reported)'` (OJP) or `'Office not reported'` (others). Rule 5: under **both** definitions, rows awarded by the agency use these awarding-office rules; only funding-only rows (awarded by another agency) use `funding_sub_agency_name`, and a NULL or unspecified DOJ funding sub-agency becomes `Department of Justice (sub-agency not specified)`. Label "Component (by awarding office)" |
| award_type_group | VARCHAR | M7.2: `Contracts`, `IDVs` (award_key `CONT_IDV_%`), `Grants` (02-05), `Direct payments` (06, 10), `Loans` (07, 08), `Other` |

**Award-level attributes (mart_awards, and the cell keys of mart_award_recipients).**
Within one (definition, FY) each award is assigned the component, type and states of its
**latest action in that FY**. Dollars per cell are exact, and `mart_awards.n_awards` adds
up across cells **within one FY and definition**. Across FYs, `n_awards` counts an award
once per FY it had actions in. (Within a FY an award's dollars sit in its latest
state/component; this only matters against USAspending's transaction-level map.)
**Recipients are NOT award-level:** see 4.2.

### 4.1 `mart_awards` (awards explorer, trends, maps)

- **Grain:** agency x definition x FY x award_category x award_type_group x award_type_code
  x component x program_office x recipient_state x pop_state. Complete: no top-N.
- **Columns:** shared, plus:

| Column | Type | Unit | Meaning |
|---|---|---|---|
| award_category | VARCHAR | | `contract` / `assistance` |
| award_type_code | VARCHAR | | D1/D2 code; `IDV` for IDV rows (type code is NULL in the source) |
| award_type_label | VARCHAR | | display text derived from the code (never from `award_type`, M7.2) |
| program_office | VARCHAR | | OJP sub-office (e.g. `OJP BUREAU OF JUSTICE ASSISTANCE`) for drill-down; NULL otherwise |
| recipient_state | VARCHAR | | USPS code of recipient location, or `Foreign / unknown` (default basis, D5) |
| pop_state | VARCHAR | | USPS code of place of performance (from FIPS), or `Foreign / unknown` |
| obligations | DOUBLE | $ | net (M7.1) |
| gross_obligations | DOUBLE | $ | sum of positive actions (M7.6) |
| deobligations | DOUBLE | $ | sum of negative actions; negative number (M7.6) |
| n_transactions | INTEGER | | transactions |
| n_awards | INTEGER | | awards (see award-level note) |

- Award obligations are a subset of account obligations; never stack them with File B
  object classes (M7.1).

### 4.2 `mart_award_recipients` (top recipients, recipient filter, recipient search)

- **Grain:** agency x definition x FY x component x award_type_group x recipient_state x
  recipient_uei. `recipient_state` is the recipient location on each **transaction** (USPS
  code or `Foreign / unknown`), so a recipient that reported more than one location has more
  than one row in a cell.
- **Attribution:** dollars go to the recipient **on each
  transaction** (M7.3), as on USAspending and in T3/T4. The cell keys `component` and
  `award_type_group` stay award-level (as in `mart_awards`), so each (definition, FY,
  component, award_type_group) sums to the same `mart_awards` cell.
- **Completeness guarantee (revised 2026-10-16):** the naming set is
  **global per (definition, recipient) across all FYs**. A recipient that is named anywhere
  is named in every cell of every FY, and none of its transactions sit in a rollup row. So
  **any sum of a named recipient's rows is exact**: any FY range, any component or award
  type filter, any state filter, and all years. The check in section 7 verifies dollars and
  transaction counts per (definition, FY, state, UEI) and over all FYs.
- **Who is named (per definition):** the union of
  - recipients ranked <= 250 by **absolute** net amount in any (FY, component, award type) cell;
  - the top 2,500 by absolute net and by net amount in any FY;
  - the top 2,500 by absolute net and by net amount over all FYs;
  - the `__NO_UEI__` group.

  Ranking by absolute value keeps large terminations named (FY2023 SAVA Workforce Solutions,
  −$160.5M). DOJ: 13,189 named UEIs; 97.9% of absolute net dollars are on named rows.
- **Rollup rows:** everything else rolls up to one row per (definition, FY, component,
  award_type_group, recipient_state). On these rows `is_rollup = true`, `recipient_name =
  'All other recipients'`, and **`recipient_uei`, `cell_rank` and the parent columns are
  NULL**. Totals still reconcile. A recipient in the rollup is not in the mart under any
  filter; find it with T4 (tier 2).
- **No-UEI transactions** are always their own named group (M7.3): `recipient_uei =
  '__NO_UEI__'`, `recipient_name = 'Recipient not identified'`, `is_unidentified = true`
  (DOJ: 6 transactions, $274,548.54 net).
- **Award counts:** `n_awards` = distinct awards with at least one transaction for that
  recipient in that row. An award whose recipient changed within the FY (e.g. a novation)
  counts once for **each** recipient. So `n_awards` must not be summed across recipients;
  for cell totals use `mart_awards.n_awards`. Summing one recipient's `n_awards` across
  rows can count an award twice if it spans FYs or reported locations; label it
  "award-years" or show transactions. `n_transactions` is additive.
- **Columns:** shared, plus `recipient_uei`, `recipient_name` (latest name for the UEI),
  `is_unidentified`, `recipient_parent_uei`, `recipient_parent_name` (often NULL: fall back
  to the recipient, M7.3), `recipient_state`, `obligations` ($), `n_awards`,
  `n_transactions`, `cell_rank` (INTEGER: rank by absolute amount, rounded to cents, in the
  (FY, component, award type) cell, ties broken by `recipient_uei`; NULL on rollups), `is_rollup`.
- **How to compute a ranking:** `GROUP BY recipient_uei` (with `WHERE NOT is_rollup`) over
  whatever filters apply, sum `obligations`, then sort by the sum (descending, or ascending
  for terminations). For display state, take the `recipient_state` with the largest absolute
  amount.
- No place-of-performance state here: recipients by PoP state is tier 2.

### 4.3 `mart_award_component_lookup` (for the API, not for charts)

- **Grain:** basis x award_category x office_eff x sub_agency_eff → `component`,
  `program_office`. `basis` = `awarding_office` (agency-awarded rows, either definition) or
  `funding_sub_agency` (funding-only rows). Lets the API filter row-level data by the same
  component (T2).

---

## 5. Sub-award marts (File F)

Source: `subawards`. FY = FY of `subaward_action_date` (not the prime's FY, M2.1).
Amounts are **self-reported and a floor**; mandatory caption wherever shown: "Sub-award
amounts are self-reported by prime recipients and incomplete. Treat them as a lower bound
(a floor), not a total." Never add to prime obligations, never present as a share of prime
obligations in the same FY (M8.1).

Shared flags (dimensions; filter on them, the rows are never dropped):

| Column | Type | Meaning |
|---|---|---|
| definition | VARCHAR | `awarding` (`prime_award_awarding_agency_code`) / `funding` (`prime_award_funding_agency_code`) |
| is_outlier | BOOLEAN | **rule** from `sql/seeds/subaward_outlier_rule.csv`, currently `subaward_amount >= 10 * prime_award_amount AND prime_award_amount > 0 AND subaward_amount >= 1e8`. DOJ: 17 rows, $18.33B (FY2017-2024). **Default: excluded (D3)**; the include toggle matches USAspending |
| is_outlier_registered | BOOLEAN | individually verified record in `sql/seeds/subaward_outliers.csv` (DOJ: the FY2021 $10.54B CASA record, also caught by the rule). Used for the record-level explanation and link |
| subaward_review_flag | BOOLEAN | review tier below the outlier rule (M8.1): `prime_award_amount > 0 AND subaward_amount > prime_award_amount AND subaward_amount >= $10M AND NOT is_outlier`. Thresholds in the same seed, `subaward_outlier_rule.csv`. DOJ awarding: 28 rows, $2,044.4M. **Flag only, never excluded by default**; show in drill-down |
| is_resubmitted_duplicate | BOOLEAN | M8.1 caveat 4, Option A. The **strict key** is prime key, sub-award number, exact amount, action date, sub UEI and normalized description (`upper(regexp_replace(coalesce(subaward_description,''), '[^A-Za-z0-9]', '', 'g'))`); rows with a NULL number, UEI or date are never grouped. The kept copy is the newest last-modified, then the lowest report ID. A non-kept copy in a group spanning **2 or more SAM report months** is a re-submission. DOJ awarding: 7,790 rows, $1,118,339,862.09. **Default: excluded (D4)** |
| is_possible_duplicate | BOOLEAN | **Flagged, kept in totals.** A non-kept copy under the six-field key (prime key, number, amount, date, sub UEI; newest last-modified kept, then lowest report ID) that is **not** a re-submission. That covers same-month copies (2,511 rows, $382,381,759.58) and near-duplicates whose description differs (516, $125,057,522.13). DOJ awarding: 3,027 rows, $507,439,281.71. Together with `is_resubmitted_duplicate`, these are the earlier 10,817 "possible duplicates" |
| is_partial_year, is_provisional | BOOLEAN | as section 4 |
| component, program_office | VARCHAR | M6.2 rule 1 on the prime's awarding office / sub-agency (the "program": OJP, OVW, COPS) |

DOJ awarding sub-award totals ($M). There are three views:
- **all rows** (= USAspending; both toggles on);
- **excluding `is_outlier` only**;
- **default, excluding `is_outlier` and `is_resubmitted_duplicate`**.

| FY | All rows | Excluding `is_outlier` | Default |
|---|---:|---:|---:|
| 2017 | 3,953.1 | 2,484.8 | 2,263.4 |
| 2018 | 4,377.3 | 3,390.2 | 3,133.5 |
| 2019 | 2,931.3 | 2,931.3 | 2,807.9 |
| 2020 | 5,192.3 | 3,362.2 | 3,225.0 |
| 2021 | 13,767.4 | 3,226.2 | 2,981.0 |
| 2022 | 3,233.0 | 3,033.0 | 2,972.7 |
| 2023 | 5,086.1 | 2,864.1 | 2,818.4 |
| 2024 | 3,999.1 | 2,918.6 | 2,890.9 |
| 2025 | 2,280.2 | 2,280.2 | 2,279.6 |
| 2026 | 1,955.9 | 1,955.9 | 1,955.7 |

The finding's table shows 2,263.5 / 2,972.8 / 2,279.5 for FY2017 / 2022 / 2025, because it
subtracts rounded values; the exact dollars match. Validation against USAspending always
runs on all rows. Required note next to the outlier note (M8.1): "Excludes N duplicate
sub-award reports totaling $X that re-submit an earlier report; list available." The finding's 28-row review tier
(section 4) is the `subaward_review_flag` column (flag only; never excluded).

### 5.1 `mart_subaward_summary` (totals, state maps, program split)

- **Grain:** agency x definition x FY x award_category x component x program_office x
  prime_state x sub_state x sub_pop_state x is_outlier x is_outlier_registered x subaward_review_flag x
  is_possible_duplicate x is_resubmitted_duplicate x exceeds_prime_amount. Complete.
- **Columns:** shared, plus `award_category`, `prime_state` (prime recipient location),
  `sub_state` (sub-recipient location, default), `sub_pop_state` (sub-award place of
  performance), all USPS or `Foreign / unknown`; `exceeds_prime_amount` (BOOLEAN,
  `subaward_amount > prime_award_amount`; a flag only, M8.1 caveat 5);
  `subaward_amount` ($), `n_subawards`, `n_prime_awards` (distinct primes in the cell;
  not additive across cells).

### 5.2 `mart_subaward_flows` (prime → sub-recipient)

- **Grain:** agency x definition x FY x component x program_office x prime_uei x sub_uei x
  prime_state x sub_state x flags.
- **Kept rows:** edges ranked <= 300 by amount within (definition, FY, component), plus
  every edge of the top 300 primes of (definition, FY), plus every `is_outlier`, `is_outlier_registered` or `subaward_review_flag` row. The rest
  roll up per (definition, FY, component, program_office, prime_state, sub_state, flags)
  with `is_rollup = true` and names `All other prime recipients` / `All other
  sub-recipients`. Totals reconcile to 5.1.
- **Columns:** shared, plus `prime_uei`, `prime_name`, `prime_state`, `sub_uei`,
  `sub_name` (latest name per UEI), `sub_state`, `subaward_amount` ($), `n_subawards`,
  `is_rollup`.

### 5.3 `mart_subaward_outliers` (note and links)

- **Grain:** sub-award report x definition, for every row with `is_outlier`,
  `is_outlier_registered` or `subaward_review_flag`.
- **Columns:** `subaward_sam_report_id`, `subaward_number`, `subaward_amount`,
  `subaward_action_date`, `prime_award_unique_key`, `prime_award_fain`,
  `prime_award_amount`, `prime_awardee_name`, `subawardee_name`,
  `prime_award_awarding_office_name`, `ratio_to_prime`, `is_outlier`,
  `is_outlier_registered`, `subaward_review_flag`, `outlier_rule_id`, `reason`, `source` (register rows only),
  `usaspending_permalink`.
- **Use:** the default note ("Excludes N sub-award reports totalling $X that are at least
  10 times their prime award and at least $100M; see list. Include them to match
  USAspending.") and the links. FY2021 charts must annotate the CASA record either way
  (`is_outlier_registered` carries its explanation).

---

## 6. Metadata marts and seeds

### 6.1 `mart_fiscal_years` (labels, flags)

- **Grain:** agency x FY (every FY with account, award or sub-award data).
- **Columns:** `has_account_data`, `account_latest_period`, `account_period_end_date`,
  `account_is_provisional`, `account_label` (M2.4, e.g. `FY2026 (through P11, Aug 2026)`),
  `has_award_data`, `award_first_action_date`, `award_last_action_date`,
  `last_prime_action_date`, `last_subaward_action_date`, `is_partial_year`,
  `award_is_provisional`, `award_label` (e.g. `FY2026 (provisional, actions through Sep
  30, 2026)`, `FY2027 (partial: Oct 1-13, 2026)`), `data_as_of`.
- **Use:** FY filter options, period labels, and chart footnotes ("Account data through
  P11 (Aug 2026); award data through Oct 13, 2026.").

- **Per-category cut-offs (added 2026-10-16, metrics 2.3/2.4):** `last_contract_action_date`,
  `last_grant_action_date` (DATE) and `contract_award_label`, `grant_award_label` (VARCHAR),
  from `mart_award_coverage` (awarding definition). **Use these for any award chart that
  shows contracts or grants;** the combined `award_label` is kept only for charts that mix
  both and must name both cut-offs. DOJ FY2026: contracts "FY2026 (provisional, contract
  actions through Sep 30, 2026)", grants "FY2026 (provisional, grant actions through Jul 31,
  2026)".

### 6.1a `mart_award_coverage` (award data cut-off per category)

- **Path:** `marts/<agency>/mart_award_coverage.parquet`. **Grain:** agency x definition x
  FY x `award_category` (`contract` | `assistance`).
- **Columns:** `category_word` (`contract` | `grant`, as used in labels),
  `min_action_date`, `max_action_date` (DATE, the latest action for that category),
  `n_transactions`, `obligations` ($, net, for the category and definition),
  `is_partial_year`, `is_provisional`, `fy_end_date`.
  - `has_reporting_gap` (BOOLEAN, M2.4): `(fy_end_date − max_action_date) > 30 days AND snapshot date > fy_end_date`. DOJ: only FY2026 assistance, under both definitions.
  - `award_label` (M2.4, exact): e.g. `FY2026 (provisional, grant actions through Jul 31, 2026)`, `FY2027 (partial: Oct 1-13, 2026)`, `FY2025`.
  - `short_label`: `FY{fy}*` when there's a reporting gap, else `FY{fy}` (axes, legends, table headers).
  - **Gap rows only:**
    - `prior_missing_share_min`, `prior_missing_share_max`: over earlier complete FYs, the share of each year's net obligations dated after the same day of the FY. DOJ grants: 0.664 / 1.003.
    - `like_period_obligations` (this FY through the cut-off) and `prior_fy_like_period_obligations` (previous FY, Oct 1 to the same day). DOJ: $0.868B vs $0.709B.
    - `gap_footnote`: an agency-level override from `sql/seeds/award_gap_footnotes.csv` when one exists (DOJ FY2026 assistance: the exact metrics 2.4 text, both definitions); otherwise the agency-neutral M2.4 template, plus the seasonality sentence when the minimum share is >= 25%. `gap_footnote_source` = `agency override` or `template`.
    - `gap_tooltip`: e.g. "Grants through Jul 31, 2026 only. Aug–Sep not yet reported."
  - `data_as_of`.
- **Rules for the frontend (M2.3/2.4):** label contracts and grants separately. For a year
  with `has_reporting_gap`:
  - use `short_label` and hatch the bar;
  - add the footnote. Use `gap_footnote` as given: for DOJ FY2026 grants it is the exact metrics 2.4 text.
  - suppress year-over-year changes, except an explicit like-period comparison.

### 6.2 `dim_agency` (global)

- **Path:** `marts/dim_agency.parquet`. **Grain:** one row per USAspending toptier agency
  (from `toptier_agencies.json`), plus any agency in the database that the list lacks.
- **Columns:** `agency_code`, `agency_name`, `abbreviation`, `agency_slug` (for M9 links),
  `has_data` (marts exist), `latest_account_fy`, `latest_account_period`,
  `latest_account_period_end_date`, `latest_award_fy`, `latest_award_action_date`,
  `data_as_of`, `marts_path` (`marts/<code>/`, NULL when no data).

### 6.3 `mart_data_issues` (Data Issues page)

- **Path:** `marts/<agency>/mart_data_issues.parquet`. **Catalog:** docs/metrics.md section 11
  (types, rules, amounts, severity, labels; authoritative). **Page spec:**
  docs/specs/data-issues-page.md.
- **Grain:** one row per issue instance. Rule-based types are detected in SQL for any
  agency; hand-verified rows come from `sql/seeds/data_issues_manual.csv` (keyed by
  `agency_code`). Labels and descriptions come from `sql/seeds/issue_types.csv` and
  `sql/seeds/issue_treatments.csv`, verbatim from M11.2, M11.3 and M11.10. Duplicates stay
  row-level (the mart is about 0.2 MB).
- **Columns:**

| Column | Type | Meaning |
|---|---|---|
| agency_code | VARCHAR | |
| issue_id | VARCHAR | stable across refreshes: `SIGNREV-`, `ZEROB-`, `RESID-`, `NEGGRP-` + FY + entity + measure; `SUBOUT-`, `SUBREV-`, `SUBDUP-` + SAM report ID; `NOUEI-` + transaction key; seed ids for manual rows |
| issue_type | VARCHAR | key (table below) |
| issue_type_label | VARCHAR | M11.10 label, e.g. "Sign reversed in File B" |
| issue_type_description | VARCHAR | M11.10 one sentence (summary views) |
| counts_in_header | BOOLEAN | count this row in the 11.7 header and card counts. False only for detail rows (contractor-address state-years). Duplicate-report rows are true but counted separately (11.7) |
| detail_of_issue_id | VARCHAR | for detail rows, the `issue_id` of the row they belong under |
| issue_type_explanation | VARCHAR | M11.2 / M11.3 longer reader text (expanded row) |
| severity | VARCHAR | M11.1, relative: magnitude >= 1% of the agency's total for that measure and FY → `high`; >= 0.1% → `medium`; else `low`. Magnitude = abs(dollar_impact), or abs(amount_as_reported) for `flagged` rows and for `footnoted` rows with zero impact (M11.1, e.g. negative groups). `note` rows and NULL-measure rows are always `low`. Seed rows may override. Base = File A obligations / outlays / budgetary resources; awarding prime obligations; all reported sub-award amounts (before exclusion) |
| fiscal_year | INTEGER | |
| period_label | VARCHAR | account label for account issues, award label for award issues |
| source | VARCHAR | `File B`, `Prime awards`, `Sub-awards`, `SF-133`, `USAspending API` |
| entity_type, entity_id | VARCHAR | `tas` + TAS; `agency` + agency code or `ALL_OTHER_ACCOUNTS`; `agency_group` + `agency\|<oc_group_key>`; `subaward_report` + SAM report ID; `transaction` + transaction key |
| federal_account_symbol | VARCHAR | for TAS rows, the TAS's federal account (e.g. `015-1060`), so badges can attach to federal-account views; NULL otherwise |
| entity_name | VARCHAR | account name; "prime -> sub-recipient"; recipient name as USAspending publishes it. **No-UEI rows show the recipient name as published, including private individuals on assistance rows** (since 2026-10-16) |
| component | VARCHAR | TAS rows: 6.1 map; sub-award and prime (no-UEI) rows: 6.2 rules, as in `mart_awards`; NULL = agency-wide |
| measure | VARCHAR | `obligations`, `outlays`, `budgetary resources`, `award obligations`, `sub-award amount`, or NULL (coverage gaps). **Every dollar aggregate groups by measure** |
| amount_as_reported | DOUBLE $ | as the source filed it; for footnote/note rows, the other source's figure (SF-133, USAspending). NULL for `ALL_OTHER_ACCOUNTS` and coverage gaps |
| amount_used | DOUBLE $ | what the dashboard uses by default |
| dollar_impact | DOUBLE $ | `amount_used - amount_as_reported`, signed; for `ALL_OTHER_ACCOUNTS` rows, the sum of the sub-$1M differences |
| treatment | VARCHAR | `corrected` / `reconciled` / `excluded` / `flagged` / `footnoted` / `note` |
| treatment_label, treatment_description | VARCHAR | M11.10, verbatim |
| treatment_footer | VARCHAR | holds metrics' `card_footer` (M11.10), verbatim and agency-neutral, e.g. "Changes breakdown detail only; headline totals are unchanged." The column name stays `treatment_footer` |
| changes_default_number | BOOLEAN | true for `corrected`, `reconciled`, `excluded`. **The header numbers, cards' dollar lines and the impact chart use only these rows** (M11.1, M11.7) |
| affects | VARCHAR | reader-facing text: metric sections and pages. **Don't match on it** |
| affects_views | VARCHAR[] | structured view keys for badges, from `overview`, `where`, `awards`, `subawards`, `places` (v2 Places view). Set per issue_type in `issue_types.csv` (`affects_views`, pipe-separated); a manual seed row can override it. DOJ: File B sign reversal / placeholder / residual → where, overview; negative group → where; implausible sub-award → subawards, overview; review tier and duplicates → subawards; no-UEI and timing → awards; SF-133 difference → overview, where; USAspending discrepancy → overview; coverage gaps → overview (SF-133) or where (FY2026 program activity names). Badge rule: match `affects_views` plus `fiscal_year`, and optionally `measure`, `component` and (awards and sub-awards) `award_type_group` |
| evidence | VARCHAR | short text. A residual row on a TAS × FY × measure that has a manual SF-133 entry ends with that entry's cross-reference, from the seed column `residual_cross_ref`. FY2024 015-X-1060: "OMB SF-133 agrees with File B here; see the SF-133 entry". FY2022 015-2020/2020-1060: "OMB SF-133 September data is blank for this account; see the SF-133 entry (File A likely understated by $24–30M)" |
| detection_rule | VARCHAR | the rule, or `manual` |
| verification_status | VARCHAR | `verified`, `rule-detected (count verified)`, `rule-detected (not yet verified)` (M11.5). As of 2026-10-16 every DOJ type is `verified`; the other values apply to new agencies or new types |
| verified_in, finding_doc | VARCHAR | internal review references (not shown to readers) |
| usaspending_url | VARCHAR | federal account page (TAS rows), prime award page (sub-award rows), award permalink (prime rows), agency page or API endpoint (agency rows). Coverage-gap rows link the USAspending agency page for that FY |
| duplicate_kind | VARCHAR | `possible_duplicate_subaward` rows only: `resubmitted` (excluded), `same_month` (flagged), `near_duplicate` (flagged). If a row is also implausible, the implausible exclusion wins and the duplicate row is flagged with impact 0 (M11.2) |
| award_type_group | VARCHAR | for prime-award rows (`recipient_not_identified`), the award's group under the `mart_awards` rule (M7.2: `CONT_IDV_` prefix → IDVs, other contracts → Contracts, 02-05 Grants, 06/10 Direct payments, 07/08 Loans, else Other), taken from the award's latest action in that FY. For sub-award rows, the prime award's group from its latest FY in the window (NULL if the prime is outside the window). Agency-level rows may carry a group when the issue is specific to one award type (set in the manual seed's `award_type_group` column; DOJ: the two `timing_difference` rows = Contracts). NULL on account-level rows and other agency rows. **Awards badges must match on this column, not on `entity_name`** |
| sibling_n, sibling_median, sibling_max | INTEGER / DOUBLE | other sub-awards on the same prime (implausible and review rows) |
| data_as_of | TIMESTAMP | |

- **Rules (M11.2):**
  - `file_b_sign_reversal`: register pairs; reported = File B, used = −File B.
  - `file_b_zero_placeholder`: TAS in File B whose every line is $0 for the measure, File A >= $1M. Reported 0, used File A.
  - `file_b_residual`: per TAS and measure (not placeholders), d = File A − sign-corrected File B; a row when |d| >= $1M. Plus one `ALL_OTHER_ACCOUNTS` row per (FY, measure) for the sum of smaller differences when that sum is >= $1M in absolute value. Identity: sign reversal + placeholder + residual impacts = File A − File B as reported, within $1M per FY and measure.
  - `file_b_negative_group`: agency-level object class group (sign-corrected) <= −$1M per FY and measure; footnoted, impact 0; evidence lists the TAS × object class cells <= −$50M.
  - Sub-award types use the rules in section 5. Duplicates: the **most recently modified copy is not flagged** (`ORDER BY subaward_sam_report_last_modified_date DESC NULLS LAST, subaward_sam_report_id`). **Tie-break:** when copies share the latest last-modified date (DOJ: 1,230 groups, 2,313 flagged rows), the copy with the **lowest `subaward_sam_report_id`** is kept unflagged. That choice is deterministic but arbitrary, so in those groups "newest" doesn't mean a later re-submission. Counts and dollars are unaffected, because every copy has the same amount and date.
- **DOJ contents, by measure (never add across measures):**

| issue_type | Rows | Treatment | Measure: Σ dollar_impact (flagged / footnoted: Σ amount_as_reported) |
|---|---:|---|---|
| file_b_sign_reversal | 12 | corrected | obligations (10 rows) +$8,052,604,203.66; outlays (2) +$2,283,469,454.78 |
| file_b_zero_placeholder | 12 | reconciled | obligations (5) +$880,066,473.18; outlays (7) +$775,419,205.93 (all FY2018) |
| file_b_residual | 52 (47 TAS + 5 all-other) | reconciled | obligations (29) −$160,878,753.70; outlays (23) +$2,664,997,778.86 |
| file_b_negative_group | 3 | footnoted | obligations −$1,906,009,329.99 (FY2019 unknown, FY2026 other); outlays −$1,549,270,816.97 (FY2026 other) |
| implausible_subaward | 17 | excluded | sub-award amount −$18,329,149,678.00 |
| subaward_review | 28 | flagged | sub-award amount $2,044,381,651.00 |
| possible_duplicate_subaward | 10,817 | 7,790 excluded (`duplicate_kind` = `resubmitted`); 3,027 flagged (`same_month` 2,511, `near_duplicate` 516) | excluded: sub-award amount −$1,118,339,862.09 (impact); flagged: sub-award amount $507,439,281.71 (as reported; same-month $382,381,759.58, near $125,057,522.13) |
| recipient_not_identified | 6 | flagged | award obligations $274,548.54 |
| file_a_sf133_difference | 5 | 3 footnoted, 2 note | FY2024 015-X-1060: −$100.0M each on obligations, outlays, budgetary resources; FY2025 015-X-4500 budgetary resources −$153,900 (note); FY2022 015-2020/2020-1060 obligations −$23,908,337.09 (note; as reported = File B $31,005,373.49, used = File A $7,097,036.40; M3.6) |
| published_figure_discrepancy | 5 | note | GTAS FY2025 (obligations); our File B sum vs USAspending's, FY2025-26 obligations and outlays |
| timing_difference | 2 | note | award obligations −$24,960 (FY2025), −$526,270 (FY2026) |
| coverage_gap | 6 | note | no amounts |
| pop_equals_contractor_address (v1.1, 2026-10-16) | 123 (10 agency-FY + 113 FY × state) | footnoted, impact 0 | award obligations flagged (as reported): FY2017 $1,827.2M … FY2026 $5,921.5M (metrics 11.2 table). Contracts (incl. IDVs), awarding; complete FYs only; state rows where flagged ≥ $25M and ≥ 50% of that state's place-of-performance contract dollars. `award_type_group` = Contracts; `issue_type_description` from metrics 11.10; `affects_views` = `awards`, `places`. **Header counting: once per agency-year** (`counts_in_header` true on the 10 agency-year rows; the 113 state-year rows have `counts_in_header` false and `detail_of_issue_id` = `POPADDR-{FY}`) |

  Totals for the header (metrics 11.6/11.7, rows with `counts_in_header`): **158 issues** excluding duplicate-report rows (140 rule-based incl. 10 contractor-address agency-years, 18 manual); 271 rows. Plus 10,817
  duplicate-report rows: 7,790 excluded, 3,027 flagged.
  By treatment (header counting), excluding duplicate-report rows: corrected 12, reconciled 64, excluded 17,
  flagged 34, footnoted 16 (plus 113 state-year details), note 15.
- **Page rules for the frontend (M11.7):**
  - **Header:** counts per treatment, as in M11.7. The only dollar figure is
    `{$E}` = Σ `amount_as_reported` of `excluded` rows (one type, one measure).
    Never "sum of absolute impacts".
  - **Cards:** one per treatment, with `treatment_label`, the count, `treatment_description` and `treatment_footer`. Then one line per (issue_type_label, measure) with dollars. No total line.
  - **Impact chart:** facet by `measure` (obligations, outlays, sub-award amount). Plot signed `dollar_impact` of rows with `changes_default_number`, stacked by `issue_type_label` as a diverging stack. Default panel: obligations. Never stack across measures.
  - Footnoted and note rows are not plotted. Show the GTAS row as text, not as an impact.

### 6.4 Seeds (`sql/seeds/`)

| File | Purpose |
|---|---|
| component_map.csv | M6.1 federal account → component (DOJ: all 56 accounts mapped). Agencies with a map: unmapped accounts become `Unmapped: <name>`; agencies without one: component = federal account name |
| award_component_rules.csv | M6.2 office rules (assistance), sub-agency name → component, the null-office `program_office` label, and the NULL sub-agency bucket |
| file_b_sign_flips.csv | M5.3 verified sign-flip register (12 DOJ rows; the candidate rule reproduces exactly these) |
| subaward_outlier_rule.csv | the single place the sub-award outlier rule and review-tier thresholds live |
| subaward_outliers.csv | individually verified outlier records (`is_outlier_registered`) |
| data_issues_manual.csv | hand-verified issues for `mart_data_issues` (M11.4; 18 DOJ rows), keyed by `agency_code`; `residual_cross_ref` holds the sentence appended to the matching `file_b_residual` row |
| issue_types.csv | per issue type: `issue_type_label`, `issue_type_description` (M11.10), `explanation` (M11.2/11.3), default treatment, affects, `affects_views`, default verification status and review reference |
| issue_treatments.csv | per treatment: `treatment_label`, `treatment_description` (M11.10), `treatment_footer` (= metrics `card_footer`, M11.10), `changes_default_number` |
| listing_office_map.csv | M6.2 null-office step 2: assistance listing → office awarding >= 95% of its known-office rows. Derived from the data by `listing_office_map.sql`; regenerate with `python sql/build_marts.py --regen-listing-map` |
| state_codes.csv | FIPS ↔ USPS ↔ name for states, DC, territories, military codes |

---

## 7. Reconciliation

`sql/checks/reconcile_marts.sql` recomputes every total from the base tables and seed
CSVs only (no mart helper tables) and compares per FY and definition (tolerance $0.01;
counts exact). `sql/build_marts.py --check` also compares the marts with the newest
`logs/validation_*_<agency>.md` to $0.001B.

Checks: File A TBR/obligations/outlays (summary, TAS, component, federal account); File B
obligations/outlays; corrected = B - 2 x flipped File B; breakdown detail = File B; breakdown
all rows = File A under (a) and (b); "other" group equals the signed base sum; prime
obligations and transaction counts by FY x definition (awards and recipients marts,
including the "Recipient not identified" bucket); named recipients complete (dollars and transaction counts per definition x FY x state x UEI, and over all FYs, equal the base); recipient cells = `mart_awards` cells; net = gross + deobligations; sub-award
amounts and counts by FY x definition (summary and flows): all rows, default (excluding rule outliers) and excluding registered outliers only; the
outlier count/amount; the review tier; `mart_data_issues` per type and measure (counts and dollars vs the base rules and vs the M11.2/M11.6 expected values; sign reversal + placeholder + residual = File A − File B within $1M per FY and measure; unique `issue_id`); `mart_negative_detail_tas` (neg_amount per FY x measure x group x TAS recomputed from account_activity and the flip seed, same TAS sets as the breakdown's `negative_detail_tas`, rank order, and the expected first three TAS); and the DOJ FY2025 object class figures from M5.1.

Result 2026-10-16, agency 015: **666/666 PASS; 62/62 validation-log totals reproduced**
( 10 FY File A obligations, 10 TBR, 10 File B obligations, 10 File B outlays, 11 prime
obligations awarding, 11 sub-awards awarding).

Grand-total reconciliation query for one FY, independent of the build:

```sql
-- File A obligations (expected 51,478,906,028.49 for 015 FY2025)
SELECT sum(obligations_incurred) FROM account_balances
WHERE agency_code = '015' AND fiscal_year = 2025
  AND submission_period_num = (SELECT max(submission_period_num) FROM account_balances
                               WHERE agency_code = '015' AND fiscal_year = 2025);
-- must equal, from the marts:
SELECT sum(obligations_b_corr) FROM 'marts/015/mart_file_b_breakdown.parquet' WHERE fiscal_year = 2025;
SELECT obligations_a FROM 'marts/015/mart_agency_fy_summary.parquet' WHERE fiscal_year = 2025;
```

---

## 8. Tier-2 query templates (API drill-down)

Parameterized DuckDB SQL in `sql/api/`, named parameters (`$agency`, ...), always with
`LIMIT`. Run against `data/fedspend.duckdb` (read-only), with the working directory at the
repo root (T2 and T5 read seeds and the lookup mart). They work for any `agency_code`.
Timings for DOJ on a Mac: all under 0.2 s.

| Id | File | Purpose | Parameters |
|---|---|---|---|
| T1 | award_transactions.sql | all transactions of one award; `usaspending_permalink` for traceability (M7.5) | `$agency`, `$award_key`, `$limit` (<= 1000) |
| T2 | awards_in_cell.sql | the awards behind a `mart_awards` bar. Same award-level attribute rule as the mart, so without truncation rows sum exactly to the cell (tested: FY2025 funding, all cells, 66,042 awards, $11,130,001,026.13 = mart) | `$agency`, `$definition`, `$fy`, `$component` (NULL = all), `$award_type_group` (NULL), `$state_basis` (`recipient`/`pop`), `$state` (NULL), `$lookup_path` (`marts/<agency>/mart_award_component_lookup.parquet`), `$limit` (<= 500), `$offset` |
| T3 | recipient_history.sql | one recipient's awards by FY | `$agency`, `$definition`, `$recipient_uei` (`'__NO_UEI__'` = not identified), `$limit` |
| T4 | recipient_search.sql | substring search on name or exact UEI across all recipients | `$agency`, `$definition`, `$fy` (NULL = all), `$q`, `$limit` |
| T5 | subawards_list.sql | sub-award reports under one prime or along one flow edge, with `is_outlier`, `subaward_review_flag`, `is_resubmitted_duplicate` and `is_possible_duplicate` computed by the same rules as the marts. **Defaults match the marts' default totals:** `$include_flagged = false` hides `is_outlier` rows, `$include_dups = false` hides `is_resubmitted_duplicate` rows; both true lists every report as USAspending does (DOJ awarding: 139,219 rows by default vs 147,026, the same as the marts) | `$agency`, `$definition`, `$prime_award_unique_key`, `$fy`, `$prime_uei`, `$sub_uei` (each NULL = any), `$include_flagged`, `$include_dups` (bool), `$limit` |

The API should cap `$limit` server-side and never return unbounded results.

---

## 9. Differences from `app/src/data/types.ts` (the frontend's assumed shapes)

| types.ts | Contract | Why |
|---|---|---|
| `FySummaryRow`, one row per `source` (`file_a` / `file_b`) | `mart_agency_fy_summary`: **one wide row per FY** with `obligations_a`, `obligations_b`, `obligations_b_corr`, gaps, residuals | gaps, residuals and call-out flags need both sources in one row; names follow M4.1 |
| `budgetary_resources` | `total_budgetary_resources` | M3.1 name |
| `obligation_rate` | `execution_rate` (File A) and `execution_rate_b` (tooltip) | M3.4 |
| `outlay_rate` | **dropped** | no outlay rate in v1 (M3.4a); remove it from types.ts |
| `file_b_gap: boolean` | `obligations_gap_called_out`, `outlays_gap_called_out` (+ `_residual_called_out`) | M4.4 rule-based, per measure |
| `source` comment "file_b = USAspending published" | label File B "Sum of File B breakdowns" | M4.2: never "USAspending published" |
| `BreakdownRow` shared shape, `category_code = 'NOT_IN_FILE_B'` | three marts: `mart_file_b_breakdown` (row_type `reconciling`, oc_group_key `reconciling`), `mart_component`, `mart_federal_account` | the plain "not in File B" row is withdrawn; treatment (a) needs corrected columns |
| `BreakdownRow.obligations/outlays` | `obligations_b_corr` / `outlays_b_corr` (default D2) or `_b`; for component/federal account the headline is `obligations_a` / `outlays_a` | |
| `parent_component` | `component_group` (and `component` on federal accounts) | |
| `AwardAggRow` with recipient in the same row | `mart_awards` (no recipient; adds `pop_state`, `award_type_group`, `award_type_code`, `program_office`, `gross_obligations`, `deobligations`, `n_transactions`) and `mart_award_recipients` (top-N + rollup) | a single mart with recipient would exceed 5 MB |
| `AwardAggRow.award_type`, `state` | `award_type_group` / `award_type_label`; `recipient_state` / `pop_state` | M7.2, M7.4 |
| `AwardAggRow.award_count` | `n_awards` | |
| `AwardAggRow.obligations` comment "File C / transaction_obligated_amount" | `federal_action_obligation` from D1/D2 | M7.1 |
| `SubawardRow` | `mart_subaward_flows` (`prime_name`, `sub_name`, `prime_uei`, `sub_uei`, `subaward_amount`, `n_subawards`, `definition`, flags, `is_rollup`) and `mart_subaward_summary`. Default filter `NOT is_outlier` | flags and definition must be filterable |
| `SubawardRow.program` (`OJP`/`OVW`/`COPS`) | `component` (`Office of Justice Programs`, `Office on Violence Against Women`, `COPS Office`, plus contract components) | M6.2 component names |
| `Agency` | `dim_agency` (`agency_code`, `agency_name`, more) | |
| `FyMeta { latestFy, latestPeriod }` | `dim_agency.latest_account_fy` / `latest_account_period` and `mart_fiscal_years` | |
| `AwardDetail` (tier 2) | T1/T2 output columns (`award_key`, `award_id`, `recipient_name`, `obligations`, `usaspending_permalink`, ...) | |


---

## 10. Watchdog Desk (`marts/<agency>/desk/`)

The public Watchdog Desk reads only the files in this section; `desk/manifest.json` lists them (10.6). v1/v2 marts aren't part of it.

**Build:** `python sql/build_marts.py --agency 015 --desk-only` writes only `marts/<agency>/desk/`; v1, concept and v2 files aren't rewritten. Engines: `sql/desk/card4.py`, `natorg.py`, `card3.py`, `card2.py` and `publish.py` (sign-offs, manifest), which run after `sql/marts/[0-8]*.sql` in memory. The desk needs only `00_setup`, `35_subaward_base`, `40_awards`, `50_subawards`, `60_fiscal_years` and `75_new_awards` (new awards per metrics 7.7, and the transaction inputs); the other mart SQL feeds the v1 marts and the prototypes (Appendix P). Output is reproducible (byte-identical on rebuild).

**Checks:** `python sql/build_marts.py --agency 015 --check-only` runs `sql/checks/reconcile_desk.sql` and, when the Card 4 reference prototype is present, `sql/checks/desk_card4_prototype.py`, which requires identical candidates, values, triggers, statuses, flags, drivers and shares. Checks whose inputs are absent are skipped with a printed note.

**Configuration** (all of it is seed data, per agency):
- `sql/seeds/desk_card4_params.csv`: rule parameters, plus the editorial switches `gap_year_grant_status`, `one_award_status`, `excluded_states`, `natorg_rule` and `count_card_min_dollar_change`.
- `sql/seeds/desk_card4_text.csv`: every reader-facing string. Templates use `{placeholders}`. `final=true` marks the spec's exact wording; `final=false` marks build wording where the spec gives none.
- `sql/seeds/desk_card_overrides.csv`: per-card `status` / `wording` / `editorial_question`, with `decided_by` and `decided_on`.

Changing any of these needs only a rebuild, no code change.

**Size:** see 10.6.

### 10.1 Card 4: states that stand out (`card4_*`; spec docs/specs/watchdog-cards.md section 4)

**Common definitions:**
- New awards follow metrics 7.7: one row per award, attributes taken from its new-award transaction. Dollars are the initial award amount.
- Awarding-agency definition. State = recipient state of the new-award transaction; NULL state is excluded.
- `excluded_states` (DC) are removed from every comparison, in both categories.
- National organizations (spec 4.9, list in `card4_national_orgs`) are removed from grant comparisons.
- Contracts count only new awards over `contract_min_amount` ($10,000).
- Year = fiscal year of the new-award date. A grant year with a reporting gap (FY2026) compares like periods, October through the cut-off month, in both years.
- Award-cycle rows are evidence only and never make a card.
- `award_category` is `assistance` (reader word "grant") or `contract`. `measure` is `count` (new awards) or `dollars` (initial award amount, nominal $). Obligations and outlays aren't used.
- Statuses: `card` (publishable after verification), `label` (publishable with the label wording), `hold` (not published), `suppressed` (below the $1M dollar-change rule for count cards; not published). In `card4_scores`, `evidence` marks an award-cycle candidate.
- **Frontend rule:** show cards with `status IN ('card','label')`. A card shows "Verified <date>" only when its independent check is recorded in the sign-off file (joined in as `verified_on`, 10.6).

#### `card4_cards.parquet`: one row per fiscal-year candidate (DOJ: 10)

| Column | Type | Meaning |
|---|---|---|
| agency_code | VARCHAR | Toptier code |
| card_id | VARCHAR | `card4-{agency}-{fy}-{state}-{category}-{measure}`. Key for every other card4 file |
| card_type | VARCHAR | `state_anomaly` (internal; never shown) |
| fiscal_year, prior_year | INTEGER | Target year *t* and *t*−1 |
| period_label | VARCHAR | Reader period, e.g. `FY2025`, `FY2026 (provisional)`, `FY2026 so far (October–July)` |
| award_category, category_label | VARCHAR | `assistance`/`contract`; `grants`/`contracts` |
| measure | VARCHAR | `count` or `dollars` |
| basis | VARCHAR | Always `fy` |
| like_period | BOOLEAN | True when both years are cut to October through the cut-off month (grant gap year) |
| is_provisional | BOOLEAN | Target year is provisional (hatch it) |
| state, state_name | VARCHAR | USPS code and name |
| prior_value, current_value, change | DOUBLE | State value in *t*−1 and *t*; change = current − prior (awards or $) |
| pct_change | DOUBLE | Undamped `current/prior − 1`. NULL when the prior value is below the size floor ("small prior base": show no percent) |
| rest_prior, rest_current, rest_pct_change | DOUBLE | Rest of the country = national − state (leave-one-out), and its undamped change |
| national_prior, national_current | DOUBLE | Sum over compared states (excludes `excluded_states`; grants also exclude national organizations) |
| r_log, rest_r_log, gap_log, z | DOUBLE | Spec 4.3: damped log changes, gap `d_s`, cross-state robust z |
| cycle_z | DOUBLE | Award-cycle z (complete grant years only; the confirmation evidence) |
| excess | DOUBLE | `current − prior·exp(R_−s)` |
| trigger | VARCHAR | `opposite`, `far` or `opposite+far` |
| direction_case | VARCHAR | `opposite` or `same_or_far` |
| headline_case | VARCHAR | Template used: `fell_more`, `rose_more`, `opposite`, `small_base`, `same_flat` |
| gap_pts | DOUBLE | State % change minus rest-of-country % change, in percentage points (NULL for small prior base) |
| band_lo_pts, band_hi_pts | DOUBLE | 10th and 90th percentiles of `gap_pts` over floor-passing states with a prior value at the floor |
| band_pts | DOUBLE | The band edge quoted in `why_text`: \|10th\| for a fall, 90th for a rise. The spread is skewed, so one symmetric number would misstate it |
| gap_outside_band | BOOLEAN | `gap_pts` lies beyond the quoted edge (checked: never false) |
| flags | VARCHAR[] | Rule labels: `one_award`, `one_recipient`, `gap_year`, `cycle_confirmed`, `timing?`, `contractor_address`, `pop_caveat` |
| rule_status | VARCHAR | Status from the rule alone (matches the prototype) |
| status | VARCHAR | Published status after the editorial switches and overrides. **Use this one** |
| status_reasons | VARCHAR[] | Why: the label flags, `dollar_change_under_minimum`, `manual_override` |
| editorial_question, override_reason, override_wording | VARCHAR | From the overrides seed (`override_wording = contractors_based_in` changes the subject to "Contractors based in {State}") |
| driver_kind | VARCHAR | `one_award` / `one_recipient` / NULL (≥ 60% of the change, same direction) |
| driver_key, driver_recipient | VARCHAR | Award key (one_award) or recipient name; recipient name |
| driver_component, driver_award_type | VARCHAR | For one_award: component and `contract`/`grant`/`award` |
| driver_share | DOUBLE | Share of the state's change (may exceed 1) |
| driver_share_display | VARCHAR | Show this in tables: `85%`, or `100%+` when the share is over 100% |
| driver_change, driver_value, driver_year | DOUBLE, DOUBLE, INTEGER | Driver's change; its value in the dominant year (current for a gain, prior for a loss), and that year |
| driver_award_url | VARCHAR | USAspending award page (one_award) |
| state_agency_share, state_agency_dollars | DOUBLE | Grants: type-A (state government) share and dollars of the current-period new awards |
| subaward_floor, subaward_recipients | DOUBLE, INTEGER | Grants: sub-awards reported under those type-A awards (metrics 8.1 default exclusions), $ and distinct sub-recipient UEIs. Self-reported: a floor |
| contractor_address_share, contractor_address_base | DOUBLE | Contracts: share of the card's new-award dollars whose place of performance is the contractor's address, and the same over all agency contract new awards (10.10). The flag's inputs are `contractor_address_flag_share` / `_flag_base` |
| pop_in_state_share | DOUBLE | Contracts: share of the card's current-period new-award dollars recorded as performed in the state |
| ojp_missing_awards | INTEGER | Grants: OJP-listed awards for the state's year `ojp_gap_year` that aren't in USAspending. NULL for agencies without an OJP list |
| dollar_change_same_rows | DOUBLE | Count cards: dollar change on the same rows (the $1M rule) |
| headline | VARCHAR | Pre-rendered headline (spec 4.6 item 1) |
| label_text | VARCHAR | Pre-rendered label sentence naming the award or recipient (spec 4.5). Show it under the headline when present |
| why_text | VARCHAR | Pre-rendered "why it stands out" (4.6 item 2) |
| fixed_line | VARCHAR | "This compares award totals; it doesn't indicate anything improper." On every card |
| caveat_keys | VARCHAR[] | Keys of the caveats in display order; text in `card4_caveats` |
| csv_path | VARCHAR | Download path relative to `marts/<agency>/`, e.g. `desk/csv/card4-015-2026-WV-contract-dollars.csv` |
| method_ref | VARCHAR | Spec, metrics and code references for "How calculated" |
| data_as_of | TIMESTAMP | Snapshot time |

#### `card4_caveats.parquet`: grain card_id × caveat_key

Columns: agency_code, card_id, `sort` INTEGER (display order), `caveat_key` VARCHAR, `text` VARCHAR (pre-rendered), data_as_of.

Keys:
- `ojp_gap`: every grant card, when the agency has an OJP list.
- `grant_cutoff`: grant gap year.
- `pass_through`: grants with state-agency share ≥ `pass_through_min_share` (25%).
- `contractor_address`: every contract card.
- `provisional_contracts`: contract cards in a provisional year.

#### `card4_series.parquet`: the chart; grain card_id × panel × entity × year_role

| Column | Type | Meaning |
|---|---|---|
| panel, panel_label | VARCHAR | `fiscal_year` ("Fiscal year"); `award_cycle` ("Award cycle (evidence)"), complete grant years only |
| entity, entity_label | VARCHAR | `state` (state name) or `rest` ("Rest of the country") |
| year_role, year | VARCHAR, INTEGER | `prior`/`current`; FY, or award-cycle year |
| period_label | VARCHAR | e.g. `FY2025 (Oct–Jul)`, `FY2025 award cycle` |
| value | DOUBLE | Awards or $ (same measure as the card) |
| index_value | DOUBLE | 100 × value / prior value of the same entity and panel (prior = 100). NULL when the prior is 0 |
| is_provisional | BOOLEAN | Hatch this bar |
| z | DOUBLE | That panel's z for the state |

#### `card4_components.parquet` and `card4_programs.parquet`: driver tables; grain card_id × component / listing

Columns: prior_count, current_count, count_change INTEGER; prior_dollars, current_dollars, dollars_change DOUBLE; `rank` INTEGER (by \|change\| in the card's measure). Plus:
- components: `component` (metrics 6.2).
- programs (grant cards only): `listing`, `program_name`, `name_source` (`listing_names seed` = curated name from trend-signals Appendix B, else the assistance-listing title).

Both tables sum exactly to the card's state values (checked).

#### `card4_recipients.parquet`: top recipients; grain card_id × recipient_name, at most 5 rows

Same count/dollar columns, plus `recipient_name`, `recipient_uei` (min UEI under that name), `award_keys` / `award_urls` VARCHAR[] (up to 5 largest awards, USAspending links), and `rank` (by \|change\| in the card's measure). Recipients are grouped by name, as the label rule is.

#### `card4_rows.parquet` and `desk/csv/<card_id>.csv`: the rows behind each card (download)

Grain: card_id × row. `row_kind` is `award` (one row per new award, both years, the card's exact filters), or `state_total` / `rest_total` (one per year).

Columns: year_role, fiscal_year, award_key, award_id, new_award_date (DATE), component, listing, program_name (grants), recipient_name, recipient_uei, recipient_type, recipient_type_label, pop_state, `n_awards` INTEGER (1 per award; totals carry the count), `amount` DOUBLE (initial award $; totals carry dollars), usaspending_url.

Award rows sum to the card value in each year, and the total rows equal the card's state and rest values (checked).

The CSV has the same columns minus agency_code, card_id and data_as_of, with `#` header lines: headline and label, the row filter, the definition, the source and data date, the fixed line, and each caveat. Link it from the card's download button via `csv_path`.

#### `card4_scores.parquet`: every scored state (methods, verification); grain FY × category × measure × basis × state

Columns: like_period; prior_value, current_value, national_prior, national_current; r_log, rest_r_log, gap_log, median_gap, scale, n_states_scored, z, excess; passes_size, passes_excess, trigger, is_candidate; for candidates also flags, rule_status (incl. `evidence` for cycle rows), driver_kind, driver_key, driver_share, state_agency_share, contractor_address_share; card_id (fiscal-year candidates).

Not needed for the card UI. Useful for a methods page ("how far other states moved").

#### `card4_national_orgs.parquet`, `card4_params.parquet` and `card4_text.parquet`: methods-page data

- `card4_national_orgs`: recipient_uei, recipient_name, `rule_basis` (`a`, `b` or `a+b`, spec 4.9). DOJ: 146.
- `card4_params`: parameter, value (strings).
- `card4_text`: key, template (the reader-text templates in use).

### 10.2 Card 4 reconciliation

- The award rows reproduce every card value; components and programs sum to the rows; the series equal the card values; rest = national − state; national = Σ states.
- An independent contract new-award total is computed from `prime_transactions`: base record (modification 0), awarding definition, over $10K, recipient state of the largest new-award-date transaction, excluded states out. It equals `card4_scores.national_current`: FY2025 20,629 awards / $3,503,789,821.23; FY2026 19,459 / $4,559,356,497.08.
- DOJ fixtures:
  - 10 candidates;
  - statuses card 2 / label 7 / suppressed 1;
  - 146 national organizations;
  - OJP k = NY 30, ME 19, VA 39;
  - AK FY2026 performed-in-Alaska share 28.6%.

### 10.3 Changes to `card4_*` on 2026-10-17

- **Reader text is final** (spec 4.5/4.6, rev 2026-10-17). `caveat_contractor_address` was reworded into two sentences (place of performance = contractor address, then share recorded in the state) and is final too.
- **Display names in reader text:**
  - `sql/seeds/component_short_names.csv` gives component short names (FBI, DOJ headquarters offices, …).
  - `sql/seeds/recipient_display_names.csv` gives curated recipient names, falling back to the recorded name.
  - Tables and CSVs keep the recorded names.
- **New columns in `card4_cards`:**
  - `driver_display_name` VARCHAR: the name used in `label_text`.
  - `verified_on` DATE and `verified_in` VARCHAR: see 10.6.

### 10.4 National organizations (`natorg_*`; spec 4.9, rule adopted 2026-10-17)

**Definitions:**
- **Group:** every new grant (metrics 7.7, awarding definition, all states) to the 146 national organizations. The list is `natorg_members`, built by the Card 4 rule `natorg_rule = a_or_b`.
- **Everyone else:** "all other grant recipients", i.e. every other new grant except non-national recipients in the HQ state (DC). Those DC recipients are in neither group and appear only as the `hq_other` caveat and CSV total rows.
- **Rule:** damped log ratio as in Card 4; a card appears when \|r_group − r_rest\| ≥ ln 1.5 and \|excess\| ≥ the Card 4 excess floor. Count cards need a $1M dollar change.
- **Bases:** fiscal-year basis. The award cycle (like-elapsed) is evidence only and confirms complete years (otherwise `timing?`, status hold). A gap year compares like periods and gets `gap_year` (status label).

**DOJ result:**
- `natorg-015-2025-dollars`, status **card**: $299.9M → $38.6M (−87%) vs $4,336.4M → $2,632.0M (−39%). Confirmed by the cycle ($283.1M → $35.5M vs −40%).
- One more FY2025 candidate has status **hold** (`timing?`: the award cycle doesn't confirm it) and isn't published.
- FY2026 doesn't trigger.

**Files** (same shapes as `card4_*`; `card_id` = `natorg-{agency}-{fy}-{measure}`):
- `natorg_cards`. Columns:
  - agency_code, card_id, card_type `national_organizations`, fiscal_year, prior_year, measure, basis, like_period, is_provisional, period_label;
  - group_label / rest_label;
  - group_prior, group_current, rest_prior, rest_current, hq_other_prior, hq_other_current (DOUBLE), pct_change (NULL below the size floor), rest_pct_change;
  - r_log, rest_r_log, gap_log, cycle_gap_log, excess, opposite (BOOLEAN), flags VARCHAR[], status, dollar_change_same_rows;
  - ojp_missing_awards INTEGER (OJP-listed FY2025 awards not in USAspending whose legal name matches a group recipient's name);
  - headline_case, headline, why_text, fixed_line, caveat_keys VARCHAR[], csv_path, method_ref, data_as_of, verified_on DATE, verified_in.
- `natorg_caveats`: card_id, sort, caveat_key (`ojp_gap`, `grant_cutoff` or `cycle_so_far`, `hq_other`, `membership`), text.
- `natorg_series`: panel `fiscal_year` / `award_cycle` ("Award cycle (evidence)"), entity `group` / `rest`, year_role, year, period_label, value, index_value (prior = 100), is_provisional.
- `natorg_components`, `natorg_programs` and `natorg_organizations` (top 10 by \|change\|, with award_keys / award_urls): same columns as the card4 driver tables.
- `natorg_rows` and `desk/csv/<card_id>.csv`:
  - row_kind `award` (group awards, both years), `group_total`, `rest_total` or `hq_other_total`;
  - columns as `card4_rows`, with `recipient_state` instead of `pop_state`.
- `natorg_scores`: every measure × basis × year, with passes_gap, passes_excess, is_candidate, opposite.
- `natorg_members`: recipient_uei, recipient_name, rule_basis (`a`, `b`, `a+b`), recipient_state (modal).
- `natorg_text`: the templates.

**Text:** `sql/seeds/desk_natorg_text.csv`. The headline template is the spec's exact text; the rest are `final=false` because the spec gives no exact wording.

### 10.5 Card 2: contracts awarded without competition (`card2_*`; spec Card 2, 2.1–2.4)

**Universe:**
- New contract awards are base records (`modification_number = '0'`), awarding definition, FY2017 through the newest non-partial FY.
- **Small purchases are excluded by both tests.** The code test is NULL-safe: `coalesce(extent IN (F,G), false) OR coalesce(solicitation = SP1, false) OR coalesce(justification IN (SP2, MPT), false)`. The value test excludes an anticipated value (base_and_all_options_value, else the base obligation) of $250,000 or less.
- **Classes:**
  - not competed = B, C, NDO;
  - competed = A, D, E, CDO (E per FPDS convention);
  - NULL extent code = not reported (shown, outside the share).
- Dollars = initial award obligations.
- Utilities (UT) are a separate band.
- Organization type only from FY2019.
- Business flags are never added together.

**Configuration:** seeds `desk_card2_params.csv`, `desk_card2_reasons.csv` (code → label, band), `desk_card2_flags.csv` and `desk_card2_text.csv`. Title, headline and explainer are the spec's exact wording. The concentration line, statutory note, flags note and org-type note are `final=false`.

**Files:**
- `card2_summary`: one row per FY, `card_id` = `card2-{agency}-{fy}`, card_type `contracts_without_competition`, status `card`. Columns:
  - csv_path, fiscal_year, period_label, is_provisional, data_through DATE;
  - n_universe, n_not_competed, n_competed, n_not_reported, n_other_code;
  - dollars_universe, dollars_not_competed, dollars_competed, dollars_not_reported;
  - share_count, share_dollars;
  - n_utilities, dollars_utilities, n_not_competed_excl_utilities, dollars_not_competed_excl_utilities, share_count_utilities, share_dollars_utilities;
  - top_award_share, show_top_awards (largest not-competed award ≥ 18% of the year's not-competed dollars);
  - headline, concentration_line (only when show_top_awards), provisional_note;
  - data_as_of, verified_on, verified_in.
  - DOJ FY2026: 555 of 2,612 (21.2%); $861.5M of $3,225.4M (26.7%). The concentration line names V2X Systems, $158.0M, 18%.
- `card2_exclusion_choices`: FY × rule (`code_only`, `value_only` with G as not competed as in the spec, `both` = default): n_not_competed, n_universe, dollars. Reproduces the spec 2.1 table.
- `card2_reasons`: FY × reason_code (NONE = not stated). Columns: reason_label, band (`utilities` / `other`), sort, n_awards, dollars, share_count_of_universe, share_dollars_of_universe. For the chart's reason bands.
- `card2_recipient_types`: FY × dimension × category, with n_awards, dollars and is_additive.
  - Dimensions: `size` (Small business / Other than small), `organization_type` (FY2019+ only), `set_aside` (e.g. 8AN), and `flag` (is_additive = false; never sum).
- `card2_top_awards`: FY × rank (top 5 not-competed awards). Columns: award_key, recipient_name, recipient_uei, amount, share_of_not_competed_dollars, reason_code, reason_label, sub_agency, psc_description, action_date, usaspending_url.
- `card2_all_actions`: FY (of the action) × competition_class, n_actions, dollars. This is the secondary "all actions" view, left-censored before about FY2021.
- `card2_rows` and `desk/csv/card2-{agency}-not-competed.csv`: one row per not-competed new award in the universe (DOJ 6,051, FY2017–26). Columns:
  - fiscal_year, award_key, transaction_key, action_date, amount, anticipated_value;
  - recipient_name, recipient_uei;
  - extent_competed_code, reason_code, reason_label, band, solicitation_procedures_code, set_aside_code, number_of_offers, business_size_code, organization_type (NULL before FY2019);
  - six flag BOOLEANs (`t`/`f` in the CSV);
  - sub_agency, office, psc, psc_description, naics, naics_description, pop_state, description (200 characters), usaspending_url.
- `card2_text` (rendered title, explainer, notes), `card2_templates`, `card2_params`.

**Size:** `card2_rows.parquet` 0.37 MB; CSV 3.3 MB.

### 10.6 Sign-offs, manifest and size

- **Sign-offs:** a CSV with columns `card_id`, `card_type`, `verified_date` (other columns are ignored). `publish.signoffs_path()` uses the review records' copy when present, otherwise `sql/seeds/desk_signoffs.csv`. It is joined into `card4_cards`, `natorg_cards`, `card3_cards` and `card2_summary` as `verified_on` (DATE). `verified_in` (VARCHAR) stays in these tables for a stable shape but is always NULL (since 2026-10-20).
  - A card_id row wins over a card_type row; the latest date wins.
  - If the file is missing the columns are NULL.
  - Rebuild after the sign-off file changes.
  - The UI shows "Verified <date>" only when `verified_on` is set.
- **Manifest:** `marts/<agency>/desk/manifest.json` has `agency_code`, `data_as_of`, `published_statuses` (`card`, `label`) and `card_types`.
  - Each card type has `parquet` (the files the UI reads), `cards` (card_id, status, csv) and `published_csvs` (CSVs of cards with status card or label).
  - The link script reads it instead of DuckDB.
  - It is written with sorted keys and no build time, so it is covered by the reproducibility check.
- **Size (DOJ):** Parquet: card4 173 KB, natorg 50 KB, card2 399 KB. CSVs: card4 0.9 MB, natorg 0.1 MB, card2 3.3 MB. Whole `desk/` folder 5.8 MB, inside the 50 MB agency budget; the largest file is the card2 CSV at 3.3 MB.

### 10.8 Card 3: grants by Justice Connection category (`card3_*`; spec section 3)

**Base:**
- New awards (metrics 7.7; `award_new`, definition awarding, assistance). Amount = initial award amount.
- Joined on listing to `docs/specs/grant-categories.csv` (12 categories, tribal-first; read only).
- **The build fails** (SystemExit) if any listing on an agency-awarded assistance transaction from FY2017 on has no category.
- **Office by rule:** the dominant metrics 6.2 component by absolute obligations. It's shown next to the scheme's office in `card3_categories`; DOJ differs only for 16.018 and 16.684, both OJP by rule.

**Scopes:** `doj` (all), `ojp` (component = OJP), `ojpx` (OJP without 16.575/16.576).

**Bases:**
- `fy`: complete FYs.
- `like`: the gap year and the year before, October to the cut-off month.
- `cycle_le`: award cycle, like-elapsed.

**SCAAP (16.606)** is a separate segment, `SCAAP`. It's in the display shares, but out of the trigger shares and never a card.

**Rules (3.3):**
- A card is a candidate when, in any scope, it passes size ≥ $25M, \|Δ\| ≥ $10M, \|Δ\| ≥ 15% of *t*−1, and \|Δ share\| ≥ 5 points in the dollar direction.
- **Timing:** the cycle share shift has the same sign and is ≥ half the FY shift; otherwise `timing?` (hold).
- **Gap year:** `gap_year`, with status from `gap_year_status` (`label`).
- **Labels:** `cvf_cap`, `earmarks`, `covid`, `ojp_gap` (agency-wide sentence; in the gap year `caveat_gap_share` replaces it) and `denominator` (f ≥ 50%, never f ≤ 0).
- **Headline scope:** the first confirmed scope in the order doj, ojp, ojpx; if none is confirmed, the first candidate scope.

**Configuration:** seeds `desk_card3_params.csv`, `desk_card3_text.csv` and `cvf_cap.csv`.
- `cvf_cap.csv`: Crime Victims Fund obligation caps FY2017–FY2025, one enacted act per year; source CRS R42672 Table 1 and R48134 (2026-10-17).
- `second_line` gives amounts in millions with one decimal. For the categories in `second_line_other_scope_categories` (DOJ: crime victim services), it adds the next confirmed scope's share, e.g. "At OJP, the share went from 36.0% to 67.9%." (spec 3.5).

**DOJ result:**
- Calibration matches spec 3.3: FY2018 3/3, FY2019 1/1, FY2020 8/4, FY2021 9/2, FY2022 2/1, FY2023 0, FY2024 4/2.
- FY2025, 5 candidates: congressionally directed (label: earmarks), victim services (label: cvf_cap, denominator, ojp_gap) and research (label); two more candidates have status hold (timing?).
- FY2026: 8 cards, all label, with the gap caveat; the late-cycle share floor is 92%.

**Files:**
- `card3_cards`: one row per (FY, category) candidate.
  - Columns: card_id `card3-{agency}-{fy}-{category-slug}`, card_type `grant_categories`, fiscal_year, prior_year, basis (`fy`/`like`), like_period, is_provisional, period_label, category, headline_scope, candidate_scopes VARCHAR[], confirmed_scopes VARCHAR[].
  - Amounts and shares: amount_prior, amount_current, change; share_prior and share_current (display shares in the headline scope); trigger_share_prior, trigger_share_current, share_shift_pts, cycle_share_shift_pts.
  - Status: flags VARCHAR[] (`confirmed` / `timing?` / `gap_year` + labels), labels VARCHAR[], status.
  - Figures behind the caveats: ojp_missing_awards, late_cycle_pct_floor, denominator_f, denominator_s_star, scope_total_prior, scope_total_current.
  - Text and links: headline, second_line, label_text (one-award concentration, Card 4 wording), fixed_line, caveat_keys VARCHAR[], csv_path, method_ref, data_as_of, verified_on, verified_in.
- `card3_caveats`: card_id, sort, caveat_key (`cvf_cap`, `earmarks`, `covid`, `denominator`, `ojp_gap`, `gap_year`, `tribal_first`), text.
- `card3_mix` (the chart): scope × basis × year × segment.
  - Columns: category, is_scaap_segment, n_awards, amount, display_share, trigger_share (NULL for SCAAP), scope_total, scope_total_excl_scaap, is_hatched.
  - Display shares sum to 1 per (scope, basis, year), and so do trigger shares without SCAAP.
- `card3_periods`: scope × three-year period × segment, with amount and voca_formula_amount. This is the spec 3.2 table: OJP FY2017–25 $33,588M, of which VOCA $16,476M.
- `card3_listings`: the card's listings in the headline scope.
  - Columns: listing, program_name (Appendix B name), program_title, subcategory, is_scaap, prior_amount, current_amount, change, prior_count, current_count, prior_share_of_scope, current_share_of_scope, rank, is_top_driver (top 3).
- `card3_categories`: the scheme. Columns: listing, program_title, category, subcategory, rationale, office_scheme, office_rule, office_matches, new_award_amount_fy_window.
- `card3_cvf_cap`: fiscal_year, cap.
- `card3_text`: templates, including the chart notes `note_scaap`, `note_gap_year` and `note_fy2017`.
- `card3_rows` and `desk/csv/<card_id>.csv`: every new award in the category for *t*−1 and *t* (all DOJ components, card basis).
  - Columns: year_role, fiscal_year, fain, award_key, listing, program_title, subcategory, component, recipient_name, recipient_uei, recipient_state, new_award_date, amount, award_cycle, like_elapsed, in_like_period, is_scaap, in_ojp_scope, in_ojp_excl_voca_scope, usaspending_url.
- `card3_scopes` (verification): every scope for every tested (FY, category).
  - Columns: the amounts and shares, pass_size, pass_abs, pass_pct, pass_share, is_candidate, timing, denominator_f, denominator_s_star.
- `card3_params`.

### 10.9 Updates on 2026-10-17 (Card 2, national organizations, manifest)

- **Card 2:**
  - Concentration rule at 15% (spec 2.1), with the exact `concentration_line` and `statutory_note`.
  - `card2_summary.why_text` is the pre-rendered `why_range`. DOJ FY2026: "…ranged from 10% (FY2024) to 25% (FY2018). FY2026 (provisional) is 27%."
  - `card2_recipient_types` gains `category_label`, from seeds `contract_set_aside_labels.csv` and `contract_org_type_labels.csv`; flags keep their column name as `category`. The build fails if a code has no label.
  - `card2_rows` gains `set_aside_label` and `organization_type_label`.
- **National organizations:** `natorg_cards.raw_ratio` (undamped ratio of the two indexes). The why-text's second sentence (`why_rule`) is shown only when raw_ratio ≥ 1.5. The DC footnote names the measure.
- **Card 4:** contractor-address caveat and "DOJ headquarters" final per spec 4.6.
- **Manifest:** lists only the Parquet files the UI reads.
  - Left out: `card4_rows`, `card4_scores`, `natorg_rows`, `natorg_scores`, `natorg_members`, `natorg_text`, `card2_rows`, `card2_all_actions`, `card2_exclusion_choices`, `card2_templates`, `card2_params`, `card3_rows`, `card3_scopes`, `card3_params`.
  - The methods-page files `card4_params`, `card4_text` and `card4_national_orgs` stay, and so does `card3_text` (the chart notes). The CSVs carry the row-level data.
- **Size (DOJ):**

  | Card | Parquet | CSVs |
  |---|---|---|
  | card4 | 168 KB | 0.9 MB |
  | natorg | 49 KB | 0.1 MB |
  | card3 | 595 KB | 9.1 MB (40 files) |
  | card2 | 395 KB | 3.3 MB |

  The `desk/` folder is 16 MB, under the 50 MB agency budget. The largest Parquet file is `card3_rows` at 0.5 MB, and the largest CSV is 1.1 MB.

### 10.10 Changes after the desk data verification (2026-10-17)

- **Card 4 contractor-address caveat.** `{cell}`, `{base}` and `{pop_in}` are now all on new-award dollars.
  - `card4_cards.contractor_address_share` is the share of the card's current-period new-award dollars whose new-award transaction has place-of-performance ZIP+4 = contractor ZIP+4.
  - `contractor_address_base` is the same share over every agency contract new award over $10,000 in that FY (DOJ: 52% FY2025, 55% FY2026).
  - The contractor_address / pop_caveat flag keeps the trend-signals definition (all contract transactions). Its inputs moved to `contractor_address_flag_share` / `contractor_address_flag_base`, and `card4_scores.contractor_address_share` is unchanged (prototype parity).
  - DOJ cells: WV 42%, AL FY2025 27%, AL FY2026 55%, AK 28%, CO 86%, NV 98%.
- **Card 2 fixed line.** `card2_summary.fixed_line`, `card2_text` key `fixed_line` and the CSV header: "Awarding a contract without competition is often lawful; this doesn't indicate anything improper."
- **National organizations: explicit ties.** A recipient passes the type test only if every tied modal business type is non-government. It passes test (a) only if every tied modal state is DC. DOJ: 145 members (Howard University and the DC Government are out); the FY2024–25 totals are unchanged.
- **Overrides seed.** `desk_card_overrides.csv` gains `label_text` and `reason_code`.
  - AK: status card, reason `editorial_decision_2026-10-17`.
  - VA FY2026: status label, the corrected label sentence, reason `analyst_label_2026-10-17`.
  - `status_reasons` carries the reason code.
- **Card 3 shares.** Card shares (`share_prior` / `share_current`, headline, second line, listing shares, denominator f and s*) now leave SCAAP out of the total, the same base as the share-shift test. The display shares stay in `display_share_prior` / `display_share_current` and in `card3_mix.display_share`, with the chart note `note_scaap_shares`.
  - FY2022 congressionally directed now reads 0.0% → 5.1%, consistent with the 5-point rule.
  - FY2024 earmarks f is 53%.
- **Card 3 gap-year headlines.** The prior period is named, e.g. "up from 8.6% in FY2025 (October–July)."
- **Card 3 CSV header.** CSV header line 1 includes `label_text`. Cards with a one-award concentration get `one_award` in `flags`; it isn't a status label.
- **Manifest.** `published_csvs` lists exactly the CSVs of cards with status card or label (DOJ: 35); held and suppressed cards' CSVs (18) stay on disk under `desk/csv/`. A static deploy should copy only the `published_csvs`.
- **Rename.** The Card 4 `card_type` and manifest key `state_anomaly` are now `state_stand_out` (`card4.CARD_TYPE`). Sign-off rows with `card_type = state_anomaly` still match through an alias in `publish.py`.

### 10.11 Public subset (`desk/public/`; held means not public)

- **Published card:** status `card` or `label`, `verified_on` set, and card_id listed in the sign-off file (10.6). DOJ: 44 cards (9 Card 4, 1 national organizations, 24 Card 3, 10 Card 2).
- **What `publish.write_public` writes:** `marts/<agency>/desk/public/<name>.parquet` for each of the 28 tables the UI reads, with the same file names and schemas as in `desk/`.
  - **Filtered by card_id:**
    - `card4_cards`, `_caveats`, `_components`, `_programs`, `_recipients`, `_series`;
    - `natorg_cards`, `_caveats`, `_components`, `_organizations`, `_programs`, `_series`;
    - `card3_cards`, `_caveats`, `_listings`.
  - **Filtered to the fiscal years of published Card 2 cards:** `card2_summary`, `_reasons`, `_recipient_types`, `_top_awards`.
  - **Kept whole** (no card-specific rows or text): `card4_national_orgs`, `card4_params`, `card4_text`, `card3_categories`, `card3_cvf_cap`, `card3_mix`, `card3_periods`, `card3_text`, `card2_text`.
- **Manifest:** `manifest.json` `card_types.*.parquet` lists only `desk/public/…` paths. `published_csvs` is unchanged (35 files).
- **Two manifests:**
  - `manifest.json`, which the app loads and deploys, lists only the published cards (DOJ 44), the 28 public files and the 35 published CSVs. It names no held or suppressed id, status or path; a check enforces this.
  - `manifest_internal.json` lists every card with its status, its CSV and a `published` flag, plus `parquet_public` and `parquet_full`. It is internal and not deployed: the link script copies only `manifest.json` and what it lists.
- **The full marts stay in `desk/`** for internal use and checks. **Deploy `desk/public/` plus `published_csvs` only.**
- **Checks** (`reconcile_desk.sql`):
  - every public card_id is in the sign-off file;
  - no held or suppressed card_id in any public file;
  - no text unique to a held card in any public text column;
  - public row counts equal the full marts filtered to published cards;
  - the manifest lists only, and all, the public files.

## Appendix P. PROTOTYPE concept marts (not part of the v1 contract)

Status: **PROTOTYPE**, built 2026-10-16 for design concepts. Not verified for publication; columns may
change without notice. Neither the v1 dashboard nor the Watchdog Desk depends on them. They are built only when
`sql/v2/` and the prototype SQL (`80_concepts.sql`, `85_v2.sql`, `86_v2_issues.sql`) are present; otherwise
`sql/build_marts.py` skips them with a printed note.

- **Path:** `marts/<agency>/concepts/<name>.parquet`. Built by the same runner from
  `sql/marts/80_concepts.sql`, with the same size budget and the same reproducible output.
- **Sources:** `prime_transactions`, joined per transaction key to the typed tables
  `contract_transactions` / `assistance_transactions` for county FIPS, congressional
  district, assistance listing, PSC, period of performance and ceiling value.
- **Attribution: per transaction.** Every dimension (geography, component, award type,
  recipient, parent, listing/PSC) is taken from each transaction, as USAspending does. So
  totals by component or type can differ slightly from v1 `mart_awards`, which uses the
  award's latest action in the FY. Grand totals per definition x FY are identical (checked).
- Both definitions are rows (`definition`); never sum across them. Money is nominal,
  `federal_action_obligation` net. FY = FY of the action date. Grant-data cut-offs from
  `mart_award_coverage` apply.

| File | Rows (015) | Size | Grain | Columns |
|---|---:|---:|---|---|
| concept_geo_county | 92,930 | 0.5 MB | definition x FY x award_category x geo_basis (`pop` \| `recipient`) x county_fips (5-digit; `unknown` if missing) | agency_code, definition, fiscal_year, award_category, geo_basis, county_fips, state_code (from the FIPS prefix), county_name, obligations, n_transactions, n_awards |
| concept_geo_district | 36,885 | 0.2 MB | definition x FY x award_category x geo_basis x congressional_district (current districts, e.g. `CA-14`; `unknown`) | agency_code, definition, fiscal_year, award_category, geo_basis, congressional_district, state_code, obligations, n_transactions, n_awards |
| concept_timeline_daily | 57,152 | 0.6 MB | definition x action_date x award_category x component | agency_code, definition, action_date, fiscal_year, action_month (first of month; group by it for monthly), award_category, component, obligations, gross_obligations, deobligations, n_transactions |
| concept_parent_recipients | 244,655 | 3.7 MB | definition x FY x award_category x parent_key | agency_code, definition, fiscal_year, award_category, parent_key (`recipient_parent_uei`, else the recipient's UEI, else `__NO_UEI__`), parent_name (latest), has_parent_uei, n_recipient_ueis, obligations, n_transactions, n_awards |
| concept_awards_1m | 35,047 | 1.2 MB | definition x award_key, for awards with net obligations >= $1M over the window (FY2017+) | agency_code, definition, award_key, award_id, award_category, award_type_group, component, recipient_uei, recipient_name, recipient_parent_name, recipient_state, pop_state, cfda_number, psc_code, first_action_date_in_window, last_action_date_in_window, period_of_performance_start, period_of_performance_current_end, potential_total_value (contracts), obligations_window, gross_obligations_window, deobligations_window, n_transactions, description_120, usaspending_permalink. Attributes = the award's latest transaction |
| concept_awards_1m_fy | 79,518 | 0.3 MB | definition x award_key x FY (same awards) | agency_code, definition, award_key, fiscal_year, obligations, n_transactions |
| concept_listing_psc | 54,236 | 0.4 MB | definition x FY x award_category x code_type (`assistance_listing` \| `psc`) x code x component | agency_code, definition, fiscal_year, award_category, code_type, code (`unknown` if missing), code_title (latest spelling), component, obligations, n_transactions, n_awards |
| concept_component_bridge | 33 | 4 KB | one row per (award_component, account_component) pair; from `sql/seeds/component_bridge.csv` | agency_code, award_component (metrics 6.2; NULL = account-only), account_component_group, account_component (6.1; NULL = award-only), relationship (`one_to_one` \| `one_to_many` \| `account_only` \| `award_only`), double_count (BOOLEAN: adding the mapped figures, or award to account, counts some money twice), note. Offices, Boards and Divisions maps to 14 account components; compensation funds, Justice Gift Fund, Independent Counsel and OBBBA 100054 are account-only |

Notes:
- `n_awards` = distinct awards with a transaction in the row. It is not additive across rows.
- Geography: DC (`DC-98`, county 11001) carries headquarters-awarded money; label it. County
  is NULL for about 4% of contract transactions by place of performance (`unknown`).
- **County × component (measured 2026-10-16, not built):** adding the award-side `component` to `concept_geo_county` gives 198,673 rows and 1.43 MB (ZSTD, sorted), well under 5 MB. Not yet replacing the existing mart.
- A check confirms every award-side component (from the lookup) and every account-side component (from `mart_component`) has a bridge row.
- `concept_parent_recipients` is complete (no top-N), at 3.7 MB. A future agency may need a
  top-N cut.
- `concept_awards_1m` threshold is on the window net per definition. An award's FY amounts
  are in `concept_awards_1m_fy`; their sum equals `obligations_window` (checked).
- Checks (in `sql/checks/reconcile_marts.sql`, prefixed "PROTOTYPE"): every concept mart's
  total per definition x FY equals base prime obligations (both geo bases separately); the
  >= $1M award count equals the base; per-FY rows sum to the window total.


### P.1a Changes after the v2 release check, spec v3.5.1

- **Component bridge** (`concept_component_bridge`, 34 rows):
  - Removed BOP → Working Capital Fund (no BOP-awarded contract links to 015-4526).
  - Removed OVW → OJP via the Crime Victims Fund (no OVW award links to 5041; OVW → OVW 015-0409 stays).
  - Added DEA, ATF and USMS → Assets Forfeiture Fund (double_count), backed by `federal_accounts_funding_this_award` ($1,520M, $1,113M, $653M). OBD → AFF stays ($1,407M).
- **`mart_data_issues`:** the 123 `pop_equals_contractor_address` rows now carry `usaspending_url`, the USAspending agency page for the FY.

### P.2 PROTOTYPE v2 marts (`marts/<agency>/v2/`, spec v3.5, 2026-10-16)

DRAFT specs: metrics 7.7 (new awards), docs/specs/trend-signals.md v3.5 (signals, events 6.1,
year-over-year 14), metrics 11.2. Not part of the v1 contract.

- **Build:** `python sql/build_marts.py --agency 015 --v2-only [--check]` writes only `marts/<agency>/v2/`; v1 and concept files are untouched. A full build writes everything. Builds are reproducible (byte-identical).
- **Engine:** `sql/v2/trend_signals.py`, a parameterized port of the reference prototype v3.5.
  - `python sql/v2/trend_signals.py --reference` runs the port on the reference tables. It must give 204 / 152 / 64 (main) and 37 / 31 / 20 (calibration).
  - Today (v3.5.1) it must give 206 / 154 / 66 (main) and 42 / 36 / 22 (calibration). It does, with 0 item-level differences (flags, rank, severity, suppression), 1 event (OJP, 26 children), 21 default items and 6 units.
- **Intermittent rule (spec 3):** a series is intermittent only if a baseline year is near zero (`near_zero_dollars` $1M, `near_zero_counts` 2), a baseline year is at or above the floor, and the median is below the floor. Only those series get `signal_kind = intermittent`, worded "It had none in {zero years}; in the other recent years it was typically …".
- **Negative dollar values:** `signal_kind = net_deobligations` (chip "Lower"), with the 9.2 net de-obligations sentence and no percent.
- **Parameters:** all in `sql/seeds/trend_signal_params.csv`:
  - spec 11 values;
  - `intermittent_low` / `intermittent_high` (0.5 / 2.0);
  - `ca_margin` 0.39, `ca_cap` 0.95, `hq_share` 0.5;
  - `event_min_children` 5, `related_share` 0.5;
  - `timing_late_share` 0.3, `cycle_offset_years`;
  - the `yoy_` floors, and `yoy_rank_basis` (`timing_robust` default; `fiscal_year`, `larger_of`).
- **Award cycle:** `sql/seeds/award_cycle_patterns.csv`, `^15[A-Z]{4,5}(\d\d)` then `^(20\d\d)` (metrics 7.7).
- **Manual demotions:** `sql/seeds/signal_overrides.csv`, with the spec 6.2 columns: agency_code, category, dimension, key, target_label, target_year, measure (empty = all), override_type, effect (`demote`), reason, evidence (row keys plus a sentence), evidence_share, decided_by, decided_on, decision_ref, verified_in.
  - **An override takes effect only when `verified_in` is set.**
  - The flag is `manual_override: {override_type}`.
  - `v2/signal_overrides` lists every seed row with `active` and `matched_item`.
  - A demoted item gets the flag `override: {label}`, a −3 rank penalty, and leaves the default feed.
  - DOJ: BOP × AK FY2026, `location_confirmed_artifact`, evidence_share 0.85, verified_in set. With it, the production default feed is 20 items in 5 units.
- **Components:** metrics 6.2 throughout. Award attributes come from each award's new-award transaction (7.7).

| File | Rows (015) | Grain / contents |
|---|---:|---|
| award_new | 85,403 | definition × award, **assistance only**. Columns: new_award_date, new_award_fy, in_like_period, award_cycle, like_elapsed_flag, component, program_office, recipient_state, pop_state, listing, listing_title, recipient_type, recipient_uei/name, new_award_amount, size_band, used_fallback, award_id, award_type_group. Contract new awards (about 900K rows) are counts only, in award_counts |
| award_counts | 77,123 | definition × FY × category × award_type_group × component × recipient_state × **pop_state**: n_awards_new, n_awards_new_counted (contracts > $10K), n_awards_new_like_period, new_award_amount (initial award amount; never add to obligations), **n_awards_active** (= v1 `mart_awards.n_awards`, renamed for v2 only), obligations, n_transactions |
| grant_count_timing | 80 | definition × component (incl. `All`) × FY, grants. Gap-year rows (FY2026) have NULL cycle columns, NULL `cycle_pct` and no timing note: fy_new, fy_new_like_period, prior FY counts, cycle_new_like_elapsed and prior (pairwise like-elapsed), has_reporting_gap, fy_pct, cycle_pct, timing_note_required, timing_note (exact 7.7 text) |
| mart_trend_signals | 204 | one row per (item, measure). Spec section 8 columns plus the frontend columns below |
| mart_yoy_changes | 802 | one row per qualifying (list, key); spec 14.5 columns plus the ranking columns below. **Program rows are keyed by listing code**; `entity_text` gives the display name (curated or current title). A gap-year tab (FY2026 grants) compares like periods only, with no cycle columns and no timing note (metrics 2.4) |
| pop_recipients | 180,982 | definition × FY × pop_state × component × award_type_group × recipient_uei. Columns: recipient_name, is_rollup, obligations, n_awards_new, n_awards_new_counted, rank_in_cell, data_as_of. Naming is decided per state-year: a recipient that ranks in the top `pop_recipients_top_n` (15) by \|obligations\| or by new awards in any cell of a (definition, FY, pop_state) is named in every cell of that state-year. That makes its totals across components and award types exact, using the same rule as mart_award_recipients. Everything else in a cell is collapsed into at most one "All other recipients" row (recipient_uei NULL, is_rollup true). A cell has no such row when every recipient in it is named (6,749 cells in the DOJ build), so each cell ties to award_counts. PoP state is award-level: the place of performance on the award's latest transaction in that fiscal year (by action_date, then transaction_key), as in mart_awards. 2.4 MB (the per-cell cap was kept; no per-state-year cap needed). DOJ check: VA FY2025 top = CGI Federal $166.2M (OBD $156.6M + FBI $9.5M + ATF $0.1M) |
| award_recipients | 212,587 | v1 `mart_award_recipients` rows (same global naming set, same columns) plus n_awards_active, n_awards_new, n_awards_new_counted, new_award_amount. A new award counts for the recipient on its new-award transaction; recipients outside the named set go to the cell's rollup row (`recipient_uei` NULL, `is_rollup`). 4.0 MB, close to the 5 MB cap |
| geo_county | 198,673 | definition × FY × category × **component** × geo_basis (`pop` \| `recipient`) × county_fips: state_code, county_name, obligations, n_transactions, n_awards_active, n_awards_new, n_awards_new_counted, new_award_amount (new awards by the new-award transaction's county) |
| signal_params | 47 | `trend_signal_params` for the methods page, long format: agency_code, parameter, value (text) |
| signal_feed_text | 3 | one row per `measure_family` (`all` \| `dollars` \| `counts`), with `family_label` ("New awards", "Dollars obligated"; "All measures" for the `all` row, which spec 9.5 doesn't define). 9.5 strings: the header is selected by the four zero/non-zero cases with singulars; `explained_text` is NULL when X = 0 and names only the explanations present. Columns: period_label, n_events, n_other_units, n_explained, header_text, explained_text, method_text |
| signal_overrides | 1 | the override seed for the methods page: item_id, action, label, reason (used in `override_text`), evidence, decided_by, decided_on, matched_item |
| data_issues | 11,088 | identical to v1 `mart_data_issues` (since v1.1) |

**mart_trend_signals: the default feed follows the dollars / new-awards switch.**
- Items, ranks, severity, flags and events are computed once over all measures (spec 6/6.1). The OJP event keeps its 26 children.
- The default feed is filtered per measure family: an item belongs to a family when it has a signal of that family (`dollars` = net obligations or initial award amounts; `counts` = new awards).
- New columns:
  - `measure_family` (of the row's measure);
  - `in_default_feed_dollars`, `in_default_feed_counts`;
  - `default_unit_rank_dollars`, `default_unit_rank_counts` (1..n over that family's default units).
- `in_default_feed` and `default_unit_rank` remain the all-measure values.
- `signal_feed_text` has one row per `measure_family` (`all`, `dollars`, `counts`).
- DOJ today (v3.5.1):
  - all = 1 event, 4 other, 43 explained;
  - counts = 1 event (OJP), 4 other, 8 explained;
  - dollars = 0 events, 3 other, 41 explained.

**mart_trend_signals: frontend columns**
- `item_id`: `{category}|{dimension}|{key}|{target_year}`, the item key.
- `event_id`: on structural children (6.1), the parent's `item_id`. Show the child inside the parent's event card, not as its own unit.
- `is_event_parent`, `event_n_children`: the event card itself.
- `related_event_id`, `related_share`: aggregates (total, award type, recipient type, state) where the event parent explains ≥ 50% of the change. Show "Related: {event}"; they stay standalone units.
- `in_default_feed`: severity high or medium, and no penalty flag. Overrides count as penalty flags.
- `default_unit_rank`: 1..n over default-feed **units** (event parents and standalone items; never event children), by rank. Cap 25.
- `feed_rank`: the rank over all shown items.
- `pop_caveat`: wording-only text for contract state items whose contractor-address share is below the base-rate threshold. No penalty.
- `override_label`, `override_evidence`: from the overrides seed.
- `flags` / `item_flags` may include:
  - `pop_caveat: …`;
  - `contractor_address: {cell}% of this cell vs {base}% DOJ-wide` (penalty);
  - `hq_effect: place-of-performance change $XM` (penalty);
  - `timing` and `timing?` (penalty);
  - `override: …` (penalty).
- `group_key`: the event parent's `item_id` for event children, otherwise the item's own `item_id`. Group feed rows by it.
- `modal_component`: on program items, the main component. Programs whose modal component has its own item get it as `parent_item_id` (6.1).
- **Section 9 text (render verbatim):**
  - `signal_kind`: `zero_so_far` \| `net_deobligations` \| `intermittent` \| `trend_break` \| `level_drop` \| `level_rise` (9.2 order).
  - Event zero list: `event_zero_programs` holds every program child that is zero so far on **any** measure. The other children are all the rest, so the two partition the event's children (DOJ: 15 + 11 = 26).
  - `chip`: "None so far", "Irregular series", "Break in trend", "Lower" or "Higher".
  - `entity_text`; `typical` (the baseline median); `baseline_range` ("FY2020–FY2024"); `slope_pct` (trend breaks only, a fraction per year).
  - `headline_text`: the 9.2 first sentence.
  - `context_keys`: every applicable 9.3 key, in priority order.
  - `context_text`: the first two 9.3 sentences.
  - `override_text`: the manual-review line, shown as a third line.
  - Event parents only: `event_title`, `event_subtitle`, `event_zero_header`, `event_zero_programs` (list), `event_other_header`, `event_show_all_text`.
  - Entity names (9.2): component name; full state name; "{Component} grants to recipients in {State}" (grants) or "{Component}, contractors based in {State}" (contracts); program = curated name plus listing number from `sql/seeds/listing_names.csv`, else the title-cased source title; recipient type = plural label from `sql/seeds/recipient_type_labels.csv`; total = "All DOJ grants" / "All DOJ contracts".
  - `listing_names.csv` carries `official_title`, the listing title as published in the award data (`program_title`), for comparison. It is not the SAM.gov Assistance Listing record, which this build can't fetch.
- Feed header counts and text (9.5): in `signal_feed_text`. E = event parents in the default feed; S = other default units; X = shown items with a penalty flag. DOJ today, with the BOP × AK override: 1 event, 4 other units, 42 explained.

**mart_yoy_changes: ranking columns**
- `rank_value`: the timing-robust value.
- `timing_tag`: BOOLEAN; show the "Timing" tag.
- `late_share`: on net-obligation rows where the positive timing test fires.
- `rank_in_list`: ordered by `rank_value`, then key.

Fiscal-year figures still display first. DOJ FY2025 component new grants: OJP 978, COPS 283, OVW 185, all tagged Timing.

**Checks** (`sql/checks/reconcile_v2.sql`, run by `--check` when v2 files exist):
- 7.7 counts, OVW FY2017/2018, and 3 assistance components;
- n_awards_active against v1;
- OJP FY2025 cycle 644 vs 3,732;
- OJP is an event with ≥ 5 children, and no event child is orphaned;
- BOP × AK has `pop_caveat` (53% vs the 56% base rate), not `contractor_address`, and is demoted by the override;
- every override matches an item;
- the 9.6 example strings exactly (OJP event title and subtitle, OVW Campus, BOP × AK), no banned words, and every signal has a kind, chip and headline;
- award_counts by PoP state, award_recipients against v1 and award_counts, geo_county totals, and program parents;
- the year-over-year component ranks (OJP 978, COPS 283, OVW 185, with timing notes);
- the grant timing note;
- the contractor-address rows;
- v2 issues identical to v1.
