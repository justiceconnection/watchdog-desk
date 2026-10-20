# Federal Spending Pipeline: Spec (v1, DOJ)

Owner: Justice Connection · Started: 2026-10-15 · Status: v1 in build

## Goal

Build a local, repeatable pipeline that downloads USAspending data for the
Department of Justice, stores it in an analysis-ready form, checks it against
USAspending's own published totals, and feeds dashboards and Substack charts.
Every piece is parameterized by agency code. Scaling to all of government is
the same pipeline run with more agency codes, then the same files moved to
cloud storage.

## 1. Scope

| Item | v1 decision |
|---|---|
| Agency | DOJ, toptier code `015` (abbreviation `DOJ`) |
| Fiscal years | FY2017 to the current fiscal year (account data starts FY2017, when DATA Act reporting became reliable) |
| Account data | Files A (balances), B (program activity × object class), C (award financial), at the Treasury account level, for accounts DOJ owns |
| Prime awards | Every transaction (contracts, IDVs, grants, loans, direct payments, other) where DOJ is the **awarding** *or* **funding** agency |
| Sub-awards | Contract and grant sub-awards under those DOJ prime awards |
| Reference | Agency list, submission calendar, and USAspending's published DOJ totals (used for validation) |

**Why two award pulls.** The API treats an awarding-agency filter and a
funding-agency filter as AND, not OR. To capture "DOJ awarded it or DOJ paid
for it," we pull each one separately and merge them, removing duplicates on the
transaction key. Every row keeps its `awarding_agency_code` and
`funding_agency_code`, so any analysis can choose its definition. The default
is **awarding**.

## 2. Acquisition (`scripts/fetch.py`)

- **No API key.** Uses only the Python standard library for HTTP.
- **Account data.** `POST /api/v2/download/accounts/` at the latest revealed
  submission period (Q4 for closed years), with **one request per file type**.
  Asking for A, B, and C in one request fails on USAspending's side for DOJ
  ("An error occurred" after about 165 seconds; observed 2026-10-15). Files A
  and B come back as year-to-date cumulative snapshots.
  - **File C (award financial) is opt-in** (`--with-file-c`). Even requested
    alone, File C fails for the whole agency. The flag splits it into one
    request per federal account, about 57 accounts × 10 years, so it's slow.
  - **File C structure:** it comes back as every period through the selected
    one, so its obligations can be summed.
- **Award data.** One `POST /api/v2/bulk_download/awards/` per fiscal year per
  agency role (awarding, funding). Each returns prime transactions and
  sub-awards for both contracts and assistance. The API limits each request to
  a date range of one year or less.
- **Jobs.** Downloads are generated server-side. The script keeps up to four
  jobs running at once, checks `/api/v2/download/status/` every 20 seconds,
  and streams each finished zip to disk.
- **Resumable.** `data/raw/<agency>/manifest.json` records every job. Re-running
  skips completed downloads. Account years are re-pulled only when a newer
  period has been revealed. The current fiscal year is always re-pulled.
- **Reference snapshots** saved alongside the raw files:
  - `toptier_agencies`
  - `submission_periods`
  - `agency/<code>/budgetary_resources`
  - `search/spending_over_time` (prime and sub-award, awarding agency)

## 3. Storage

```
doj-fed-spending/
  SPEC.md  README.md  requirements.txt
  scripts/   setup.sh  fetch.py  build.py  validate.py  common.py
  sql/       models.sql            # clean views (hand-written)
  data/
    raw/015/        original zips + reference JSON + manifest (never edited)
    parquet/<dataset>/agency=015/fy=YYYY/role=…/*.parquet
    fedspend.duckdb  views over the parquet files
  logs/
```

- **Parquet stores every column as text**, exactly as published. Codes such as
  `015` and ZIPs with leading zeros survive intact. Types are applied in the
  DuckDB view layer.
- **Estimated size for DOJ, FY2017 onward:** a few GB of raw zips and 1–3 GB
  of Parquet. This is an estimate; the first full pull will give the real
  figure.
- `data/` stays out of git when this moves to GitHub. It's rebuildable from
  the API.

## 4. Data model (DuckDB views)

**Base views** are typed and one-to-one with the published files:

| View | Grain | Source |
|---|---|---|
| `account_balances` | Treasury account × fiscal year (latest period) | File A |
| `account_activity` | Treasury account × program activity × object class × fiscal year | File B |
| `award_financial` | Treasury account × award × period | File C |
| `contract_transactions` | One FPDS contract action | D1, merged and deduplicated |
| `assistance_transactions` | One FABS assistance action | D2, merged and deduplicated |
| `contract_subawards` / `assistance_subawards` | One reported sub-award | F, merged and deduplicated |

**Analysis views** use common column names across contracts and assistance:

- `prime_transactions`: contracts and assistance in one table.
- `prime_awards`: rolled up to award level. Columns include total obligated in
  window, first and last action dates, and the latest recipient, description,
  and sub-agency.
- `subawards`: contract and assistance sub-awards in one table, each linked to
  its prime award key.
- `agency_year_summary`: per fiscal year, budgetary resources, obligations, and
  outlays (from File A), plus contract, assistance, and sub-award totals.

**Conventions**

- Every table carries `agency_code` and `fiscal_year`.
- Amounts are DOUBLE in dollars.
- Obligations and outlays are never summed together.
- File A and B amounts are cumulative within a year. Use the row for the
  latest period; never sum across periods.

## 5. Validation (`scripts/validate.py`)

The script runs offline against the saved reference snapshots.

**Account totals**
- File A budgetary resources and obligations per fiscal year must match
  `/agency/015/budgetary_resources` within 0.5%.

**Award totals**
- Prime obligations per fiscal year (awarding = DOJ) must match
  `spending_over_time` within 1%.
- The same check applies to sub-awards.

**Data quality**
- Unique transaction keys.
- No null award keys.
- Every fiscal year present.
- Sub-awards whose prime award isn't in the prime table are counted and
  reported, not failed. Sub-awards can attach to primes dated outside the
  window.

Each run writes a `PASS`/`WARN`/`FAIL` table to `logs/validation_<date>.md`.
Numbers don't get published from a run with a FAIL.

## 6. Refresh

| Data | Upstream refresh | Command |
|---|---|---|
| Awards and sub-awards | Monthly | `python scripts/fetch.py && python scripts/build.py && python scripts/validate.py` |
| Account data | Monthly (DOJ submits monthly; quarterly certification) | same |

A monthly scheduled run can be added later.

## 7. First outputs (after first load)

1. DOJ budget picture by fiscal year: budgetary resources, obligations, and
   outlays; execution rate by component account.
2. Where the money goes, split three ways: payroll and benefits (object class
   1x), contracts, and grants.
3. Sub-award flows: OJP, OVW, and COPS grants from prime recipient (often a
   state) to sub-recipient (often a locality), mapped by state.
4. Top contractors and grantees by component.

## 8. Path to all of government

1. Run `fetch.py --agency <code>` for each code in
   `toptier_agencies.json`. Account downloads also accept `--agency all`.
2. Same Parquet layout: new `agency=` partitions, no schema change.
3. When local disk becomes the limit, sync `data/parquet/` to S3 or R2 and
   point DuckDB at the bucket (see the cost notes in the project).

## Known limitations

- **Sub-award data is self-reported** by prime recipients through SAM.gov.
  It's incomplete and sometimes duplicated. Treat totals as lower bounds.
- **Recent periods get restated.** The current fiscal year is provisional.
- **Award "fiscal year"** means the fiscal year of the transaction's
  `action_date`, not the fiscal year of the appropriation.
- **Account data covers DOJ-owned Treasury accounts.** Money DOJ receives
  through transfers from other agencies' accounts appears under those owners.
