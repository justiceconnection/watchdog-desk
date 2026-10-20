# Metric definitions: Federal Spending Dashboard (v1)

Status: Current as of 2026-10-20. What has been independently checked:
- Sections 1-10: the DOJ figures and worked examples were reproduced on 2026-10-16 with separate queries against the database, OMB's SF-133 and USAspending's published totals. The new-award definition in 7.7, which every Watchdog Desk card uses, was reproduced again on 2026-10-16 and 2026-10-17.
- Section 11 (data issues register): checked against the built data-issues table on 2026-10-16. Status by issue type is in 11.5; types marked "not yet verified" there have had their totals checked but not a row-by-row recount.

Not verified, or only partly:
- The count-toggle parts of 7.7 (marked "earlier dashboard") were reviewed as a draft only.
- SF-133 reconciliation is incomplete for FY2017 and FY2019-FY2022, because the OMB extracts are incomplete (3.6).
Last updated: 2026-10-15 · Data snapshot: `data/fedspend.duckdb` built 2026-10-15/16 (accounts through FY2026 P11; awards through 2026-10-13)

This file is the spec that `sql/marts/` implements and that the dashboard
shows in each "how this is calculated" note. Every metric here takes an
`agency_code` parameter (written `$agency` below). Nothing may hard-code `015`.
DOJ examples are illustrations only.

Contents
1. Conventions used by every metric
2. Fiscal year, period and provisional labelling (incl. FY2027)
3. Account metrics (Overview): budgetary resources, obligations, outlays, execution rate, unobligated balance
4. File A vs File B: the two totals, the gap, the toggle
5. Breakdowns from File B: object class, program activity, and the reconciliation row
6. Component mapping (account side and award side)
7. Award metrics: obligations, awarding vs funding, award type groups, recipients, states
8. Sub-award metrics
9. Traceability links
10. Decisions and remaining open questions

---

## 1. Conventions used by every metric

| Rule | Detail |
|---|---|
| Obligations vs outlays | Separate measures. Never added together. Each chart names which one it shows. |
| Gross outlays | Every outlay figure is **gross outlays**: File A `gross_outlay_amount`, File B `gross_outlay_amount_FYB_to_period_end`. Offsetting collections are not netted out. This matches USAspending. |
| File A/B amounts | Fiscal-year-to-date (FYTD) snapshots. The build keeps one snapshot per FY, the latest period revealed (`submission_period_num`). **Sum across accounts. Never sum across periods.** If a future build loads several periods per FY, every account metric must first filter to `submission_period_num = max(submission_period_num)` for that `(agency_code, fiscal_year)`. |
| Award amounts | `federal_action_obligation` on each transaction (D1/D2). It's a per-action change, so summing is correct. |
| Sub-award amounts | `subaward_amount` as self-reported in FSRS/SAM. A floor, not a census (section 8). |
| Money | Nominal dollars. No inflation adjustment in v1. |
| Agency definition | Account data covers Treasury accounts **owned** by the agency (`pull_role = 'owner'`). Award data defaults to the **awarding** agency, with **funding** as a toggle. |
| Rounding | Store full precision. Display $B to 1 decimal ($51.5B) in headlines, and $M to 1 decimal in tables. Percentages to 1 decimal. |

Parameter style: DuckDB named parameters (`$agency`, `$fy`). Views referenced
are in `sql/models.sql` or are base tables built by `scripts/build.py`.

---

## 2. Fiscal year, period and provisional labelling

### 2.1 Fiscal year semantics by source

| Source | `fiscal_year` means | Grain |
|---|---|---|
| File A `account_balances`, File B `account_activity` | The submission fiscal year. Amounts are FYTD as of `submission_period_num`. | One snapshot per FY (latest period) |
| D1/D2 `prime_transactions` | FY of `action_date` (Oct 1 to Sep 30). Not the appropriation year. | One row per transaction |
| F `subawards` | FY of `subaward_action_date` (checked: 0 rows disagree with `subaward_action_date_fiscal_year`). It is **not** the prime award's fiscal year. | One row per SAM sub-award report |

Periods: P1 = October ... P12 = September. Agencies report P1 together with P2
(there is no standalone P1 snapshot). FY2017-FY2019 were quarterly submissions
(the snapshot label reads `FY2019Q4`). The P12 equivalent is stored as
`submission_period_num = 12`.

### 2.2 Latest period per FY (account data)

```sql
SELECT agency_code, fiscal_year, max(submission_period_num) AS latest_period
FROM account_balances
WHERE agency_code = $agency
GROUP BY 1, 2;
```

### 2.3 Provisional flags

An **account FY is provisional** when `latest_period < 12`. For DOJ today that is
FY2026, through P11 (period ending Aug 31, 2026). P12 should be revealed around
mid-November 2026. See `data/raw/<agency>/reference/submission_periods.json`.

An **award FY is provisional** when either:
- it is the fiscal year containing the data snapshot date (today that is FY2027), or
- it ended fewer than 90 days before the snapshot date. FY2026 ended 2026-09-30, so it is provisional until about 2026-12-29. Late FABS/FPDS reporting and corrections land in that window.

**Coverage cut-off per award category.** The label must use `max(action_date)` per
(agency, FY, `award_category`), not the FY end date or the overall maximum. In the
current DOJ data, FY2026 contract actions run to 2026-09-30, but **assistance (grant)
actions stop at 2026-07-31**. August and September grant reporting hasn't arrived, and
USAspending's own FY2026 grant total ($868M) has the same gap. Those two months
normally carry most of DOJ's grant obligations: $1.96B–$5.79B, or 66% to 100% of the
full-year net, in FY2017–FY2025. Rules:
- A grant-year comparison that includes a year with an incomplete cut-off must either compare the same months in every year (e.g. October–July), or show the incomplete year hatched, with the cut-off in the label.
- Never compute a full-year change against a year whose grant data stops before September.

The snapshot date is `fetched_at` in `reference/snapshot_info.json`. The
data contract should expose it as `data_as_of`, and should also
expose `max_action_date` per (agency, FY, award_category).

### 2.4 Labels (exact strings)

| Case | Label | Example |
|---|---|---|
| Account FY, closed | `FY2025` | FY2025 |
| Account FY, provisional | `FY{fy} (through P{p}, {Mon} {yyyy})`. The month is the period's end month. | `FY2026 (through P11, Aug 2026)` |
| Award FY, provisional | `FY{fy} (provisional, {category} actions through {max action_date for that award_category})`. Contracts and grants are labelled **separately**, because their cut-offs differ. | `FY2026 (provisional, contract actions through Sep 30, 2026)`; `FY2026 (provisional, grant actions through Jul 31, 2026)` |
| Award FY, partial (current FY) | `FY{fy} (partial: {min date}-{max date})` | `FY2027 (partial: Oct 1-13, 2026)` |
| Charts mixing both | The footnote names both cut-offs: "Account data through P11 (Aug 2026); award data through Oct 13, 2026." | |
| Award FY with a **reporting gap** (a category's latest `action_date` is more than 30 days before the FY end, and the FY has ended) | Axis/legend label: `FY{fy}*`. Bar or point drawn hatched. Footnote (exact text below) | `FY2026*` |

**Reporting-gap rule** (agency-neutral): for each (agency, FY, `award_category`), set
`has_reporting_gap = (fy_end_date − max(action_date)) > 30 days AND snapshot date > fy_end_date`.
For DOJ, only FY2026 assistance is flagged (latest action 2026-07-31; FY end 2026-09-30).
Contracts aren't flagged (2026-09-30).

**Exact reader-facing text for DOJ FY2026 grants** (decided 2026-10-16: label the gap; DOJ is not contacted). The bracketed values are computed by the template:

- **Short label** (axes, legends, table headers): `FY2026*`
- **Footnote** (every chart, table or KPI that includes FY2026 grant or assistance award amounts):
  > *FY2026 grant data runs only through July 31, 2026. DOJ has not yet reported grant awards made in August or September, the months when most DOJ grants are awarded (66% to 100% of each year's grant obligations in FY2017–FY2025). The FY2026 grant total will rise when those reports arrive. Compare like periods: October–July grant obligations were $0.87 billion in FY2026, versus $0.71 billion in FY2025.*
- **Tooltip** on the FY2026 grant bar: `Grants through Jul 31, 2026 only. Aug–Sep not yet reported.`
- **Template** for any agency: "FY{fy} {category_plural} data runs only through {max_action_date:%B %-d, %Y}. {agency_short} has not yet reported {category_plural} made after that date. The FY{fy} total will rise when those reports arrive." Append the seasonality sentence only when the share of the missing months, measured over the agency's prior complete years, is 25% or more.
- Sub-award charts don't get this footnote, because FY2026 sub-awards run to 2026-09-30. They still carry the floor caption.
- Year-over-year changes involving a flagged year are suppressed in KPIs. They are shown only as an explicit like-period comparison (October–July).

Charts that put a provisional year next to closed years must mark it visually,
for example with a hatched bar or dashed line, and never compute a year-over-year
change against a closed year without saying so. The one exception is the
same-period comparison in section 3.4.

### 2.5 FY2027 (award data for a few days only)

DOJ award data exists for FY2027: Oct 1-13, 2026. On the awarding basis that's
**589 transactions and $64.5M** ($64,506,394.77, matching USAspending's $0.0645B).
Including the 29 funding-only rows it's 618 transactions and $64.6M. Sub-awards are
$8.7M (Oct 1-9). There is no FY2027 account data, and
none will exist until P2 is revealed (about mid-December 2026).

Handling:
- **Overview and "Where it goes":** exclude FY2027. Account data doesn't exist for it.
- **Award trend charts:** exclude FY2027 by default. Thirteen days is not a year.
- **Awards explorer:** FY2027 is selectable in the FY filter with the partial label above. It is not the default selection.
- **Marts:** keep FY2027 rows, but carry `is_partial_year = true` and `period_end_date`, so the dashboard can filter on them.
- **General rule:** an award FY is "partial" when the snapshot date falls inside it. This works for any agency and any year.

---

## 3. Account metrics (Overview)

All from **File A** (`account_balances`, typed base table; `account_year` and
`federal_account_year` are views over it). Grain: Treasury account symbol (TAS) ×
FY, at the latest period.

### 3.1 Total budgetary resources (TBR)

- **Meaning:** All the money the agency could obligate this fiscal year. That's new appropriations, plus unobligated balances carried in from prior years, plus offsetting collections, transfers and other authority.
- **Formula:** `sum(total_budgetary_resources)` over the agency's TAS for the FY.
- **Source:** `account_balances.total_budgetary_resources`. Components are in `budget_authority_unobligated_balance_brought_forward`, `adjustments_to_unobligated_balance_brought_forward_cpe`, `budget_authority_appropriated_amount`, `borrowing_authority_amount`, `contract_authority_amount`, `spending_authority_from_offsetting_collections_amount`, `total_other_budgetary_resources_amount`.
- **Filters:** `agency_code = $agency`, `fiscal_year = $fy`.
- **Check:** `total_budgetary_resources = status_of_budgetary_resources_total` (holds for DOJ in every FY). It matches USAspending `agency_budgetary_resources` exactly in every FY.
- **Caveats:**
  - TBR is **not** "the budget" or the appropriation. It includes multi-year and no-year balances that may not be obligated this year. DOJ's FY2025-26 jump ($67.1B in FY2024, $79.5B in FY2025, $88.1B in FY2026 P11) is largely new multi-year money and growing balances: the One Big Beautiful Bill Act BRIDGE fund 015-0410 ($3.5B, $0 obligated in FY2025), OBBBA section 100054 activities 015-0140 ($3.57B in FY2026), and the RECA trust fund 015-8116 ($2.57B in FY2026), plus the large standing balances of the Assets Forfeiture Fund and the USVSST Fund.
  - It includes child accounts that DOJ owns but another agency spends (allocation transfers: HHS `075-015-...` about $110M a year; Interior `014-015-...` under $5M).
- **DOJ example:** FY2025 = $79.484B; FY2026 (through P11) = $88.149B.

### 3.2 Obligations (File A): default headline

- **Meaning:** Binding commitments the agency made during the FY (contracts signed, grants awarded, payroll earned), net of current-year deobligations.
- **Formula:** `sum(obligations_incurred)` over the agency's TAS for the FY.
- **Source:** `account_balances.obligations_incurred`.
- **Filters:** as in 3.1.
- **Caveats:**
  - Gross of intra-agency flows. When one DOJ account pays another, both obligations are counted. Examples are reimbursable work by the Working Capital Fund 015-4526 (about $2.2B a year), and the FY2026 $2.18B payment from 015-0333 into the RECA Trust Fund 015-8116, which then obligates claims. USAspending and SF-133 count the same way. v1 doesn't net these out (2026-10-15).
  - Obligations can be negative for an account in a year when deobligations exceed new obligations.
- **DOJ example:** FY2025 = $51.479B; FY2026 (through P11) = $50.791B.
- **FY2024 exception:** File A is probably $98.5M low; it is footnoted, not overridden (see 3.6).

### 3.3 Outlays (File A): default headline

- **Meaning:** Cash actually paid out during the FY, against obligations from this year or earlier.
- **Formula:** `sum(gross_outlay_amount)`.
- **Source:** `account_balances.gross_outlay_amount`.
- **Caveats:** Outlays in a year can exceed that year's obligations, because they pay down earlier obligations. Never compute "obligations minus outlays" as if it were a balance. Use 3.5.
- **DOJ example:** FY2025 = $53.478B; FY2026 (through P11) = $51.705B.

### 3.4 Execution rate

- **Meaning:** The share of the money available this year that has been committed (obligated).
- **Formula:** `sum(obligations_incurred) / NULLIF(sum(total_budgetary_resources), 0)`. Numerator and denominator are both **File A**, over the same scope (agency, component or federal account). This is already the formula in `account_year` and `federal_account_year`.
- **Ratio of sums, never average of ratios.** For a component, sum the obligations and the TBR across its accounts, then divide.
- **Toggle behaviour:** The execution rate always uses File A, because TBR exists only in File A. When the File B toggle is primary, still show the File A rate. A tooltip can give "File B obligations / TBR" as secondary.
- **Caveats:**
  - **Provisional year:** FYTD obligations ÷ full-year resources climbs through the year. FY2026 at P11 (57.6%) is not comparable with FY2025 at P12 (64.8%). Options for a fair comparison: (a) only show it with the "through P11" label; (b) compare with prior years at the same period. Only File B obligations by period exist for prior years, in `budgetary_resources.json` → `agency_obligation_by_period` (FY2025 P11 = $43.17B File B). There's no File A by period in the database; prior-year P11 File A would have to be fetched to do this on a File A basis.
  - A low rate isn't automatically under-execution. No-year and multi-year funds (Assets Forfeiture Fund, USVSST Fund, BRIDGE fund, buildings & facilities) carry large balances by design. Show the federal-account breakdown next to the agency rate.
  - Child allocation accounts and intra-agency flows are in both numerator and denominator.
- **DOJ example (File A):** FY2017 77.4%, FY2020 85.5%, FY2024 77.4%, FY2025 64.8%, FY2026 through P11 57.6%.

### 3.4a Outlay rate: not provided (decided)

The data contract asked whether an outlay rate is wanted. **No outlay rate in v1**,
whether outlays ÷ TBR or outlays ÷ obligations:
- A year's outlays largely pay prior-year obligations. In FY2021, DOJ outlays ($46.19B) exceeded obligations ($44.31B).
- TBR includes multi-year balances, so outlays ÷ TBR (DOJ: 74.2% in FY2017, 58.7% in FY2026 P11) mixes timing effects that a reader would take as performance.
- No `outlay_rate` field is provided. Obligations and outlays are shown as separate series (3.2, 3.3). Execution rate (3.4) is the only rate.

### 3.5 Unobligated balance (supporting metric)

- **Formula:** `sum(unobligated_balance)` from File A. Identity: `TBR = obligations + unobligated_balance`. This holds when there are no rounding adjustments; an independent check should test it.
- **Use:** The tooltip on execution rate. It explains low rates (FY2026 P11: $37.4B).

### 3.6 Independent confirmation: File A vs OMB SF-133

Sources: an independent reconciliation against OMB's SF-133 (2026-10-15, monthly extracts; 2026-10-16, the "quarterly" files and the FY2017 carry-forward check).

The check used OMB SF-133 extracts downloaded from OMB, comparing at the TAS level:
- line 1910 with TBR;
- line 2190 with obligations;
- −(line 3020) with gross outlays.

The FY2019-FY2022 "quarterly" files are **the same OMB extract** as the monthly files: same `LAST_UPDATED`, and identical `Raw Data` in all 44 columns. They add no information. The TAS counts below are the corrected counts from the 2026-10-16 check.

| FY | File A vs SF-133 (TBR / obligations / outlays) | Status for the dashboard |
|---|---|---|
| 2017 | **Not testable** for TBR, obligations or outlays. The only extract (`1187284015.xlsx`, extracted 2017-09-20) has no September (P12) data and covers 82 of 197 TAS. **Partial check passed:** File A's FY2017 closing unobligated balance equals the FY2018 SF-133 line 1000 (balance brought forward) for 169 of the 170 TAS carried forward ($12,070,126,483.25 vs $12,070,077,899.83; the only difference is 015-X-0136, +$48,583.42; the 27 TAS not carried forward have $0 unobligated balance). This supports File A's closing balances but doesn't confirm obligations or outlays. | Footnote: "Not independently reconciled (OMB extract incomplete)." |
| 2018 | Equal to the cent on all three measures, 196 of 196 TAS | Confirmed |
| 2019 | +$11.36M / +$26.82M / +$3.13M. 189 of 197 TAS exact. Mostly small real differences (Working Capital Fund 015-X-4526 +$21.0M obligations; 015-2017/2017-1060 +$6.18M). +$3.48M of the outlays difference is a cancelling TAS blank at P12. | Partly reconciled (footnote) |
| 2020 | +$826.41M / +$736.97M / +$702.63M. 187 of 199 TAS exact. 99% is Prison Industries 015-X-4500, which is **blank at P12 in the extract**. Real differences: obligations +$1.05M, outlays +$0.10M. | Not fully reconciled: extract gap |
| 2021 | +$7,623.71M / +$7,456.57M / +$6,512.59M. 186 of 197 TAS exact. Almost all is BOP S&E 015-2021/2021-1060, **blank at P12 in the extract**. Real differences: TBR +$79.22M, obligations $4,004, outlays +$7.98M. | Not fully reconciled: extract gap |
| 2022 | +$1,324.79M / +$69.26M / +$109.63M. 196 of 198 TAS exact. **Every TAS other than the two blank-P12 ones (BOP Buildings & Facilities 015-X-1003 and BOP S&E 015-2020/2020-1060) is exact.** See the note on 015-2020/2020-1060 below. | Not fully reconciled: extract gap |
| 2023 | Equal to the cent, 204 of 204 TAS | Confirmed |
| 2024 | −$99.2M / **−$98.5M** / **−$100.0M**. Almost entirely 015-X-1060, where **SF-133 equals File B** (see below) | Exception (below) |
| 2025 | Obligations and outlays equal to the cent; TBR −$153,900 (015-X-4500, immaterial) | Confirmed |
| 2026 P11 | Equal to the cent, 226 of 226 TAS | Confirmed |

The check also corrected one erratum: FY2020 015-2018/2018-0134-000 has −$5,680.00 obligations and outlays in File A and no SF-133 row. It's immaterial.

**Caveat to show (methodology note):** "Account totals were checked against OMB's
SF-133 and match to the cent for FY2018, FY2023, FY2025 and FY2026. FY2017 and
FY2019-FY2022 could not be fully reconciled, because the OMB extracts available to
us are incomplete: they are missing September data for some large accounts. This
reflects the OMB extracts, not a known error in the account totals. For FY2017, the
closing balances do match the balances OMB carried into FY2018."

**Closing the gap** (not yet decided). Re-downloading the same
files won't help. Two options:
1. A **later** OMB SF-133 extract, whose `LAST_UPDATED` is after 2017-11-15 (FY2017), 2019-10-18, 2020-10-18, 2021-10-19 or 2022-11-07 respectively, and which contains September data.
2. As a fallback, the "Actual" column of the President's Budget Appendix at the federal-account level: the FY2019 Budget for FY2017 actuals, and the FY2022, FY2023 and FY2024 Budgets for FY2020, FY2021 and FY2022. It's in $ millions, so it can confirm the large gaps (Prison Industries, BOP S&E, B&F) but not to the cent.

**SF-133 confirms File A in every A vs B gap account**, to the cent and with
positive signs:
- ATF 0700 (FY2018/19), OCDETF 0323, U.S. Trustee 5073;
- Assets Forfeiture Fund 5042 outlays (FY2018/19; in FY2019 its obligations also equal File A, with File B $0.90M lower);
- Prison Industries 4500 (FY2025/26).

In **FY2019 the ATF sign flip is on obligations only.** SF-133 line 2190 for 015-2019/2019-0700 is +$1,345,699,269.85, equal to File A. File B shows −$1,345,563,448.80: reversed, and also $135,821.05 lower in magnitude. ATF outlays aren't flipped: SF-133 and File A are $1,139,722,278.43, and File B is +$1,138,218,881.47, positive but $1.50M lower. That matches the register in 5.3 (obligations only for ATF).

This is the independent basis for treatment (a) in 5.3.

**Note: FY2022 BOP 015-2020/2020-1060-000 (expired FY2020 Salaries & Expenses).**
- File A's year-end obligations are **$7,097,036.40**. That's below the SF-133's August (P11) cumulative figure of **$36,628,044.34**. The SF-133 extract is blank at P12 for this TAS.
- File B is $31,005,373.49, higher than File A and closer to the SF-133.
- Outlays are consistent: File A $21,078,444.10 = File B; SF-133 P11 $20,045,535.98.
- Cumulative fiscal-year-to-date obligations (line 2190) normally don't fall from P11 to P12. So File A is probably understated for this account, by roughly $24–30M (File B or the SF-133 P11 figure as the reference). This is an interpretation; the P12 SF-133 value isn't available to confirm it.
- The same pattern as FY2024 015-X-1060, where SF-133 sided with File B, makes it more plausible.
- Size: about 0.05–0.06% of DOJ's FY2022 obligations ($49.6B).
- **Recommendation: a data issue row, not a headline footnote.** Add a manual `file_a_sf133_difference` seed row:

  | Field | Value |
  |---|---|
  | `issue_id` | `015-SF133-2022-015-2020/2020-1060-000-obligations` |
  | measure | obligations |
  | `amount_as_reported` | 31,005,373.49 (File B) |
  | `amount_used` | 7,097,036.40 (File A) |
  | `dollar_impact` | −23,908,337.09 |
  | treatment | `note` |
  | severity | low (note) |

  - Evidence text: "File A year-end obligations ($7.10M) are below the SF-133 August figure ($36.63M) and below File B ($31.01M); SF-133 September data is blank in the available extract, so File A can't be confirmed. Likely understated by $24–30M."
  - `verified_in`: the 2026-10-16 SF-133 reconciliation (check of FY2022 015-2020/2020-1060).
- Why not a footnote on headline figures: the amount is below the 0.1% materiality used elsewhere, and it can't be confirmed. The rule-based `file_b_residual` row for the same TAS and year (−$23.9M, File B above File A) must cross-reference this row in its evidence. The BOP component and federal account 015-1060 show the data-issue badge for FY2022.

**The FY2024 exception: 015-X-1060 (BOP S&E, no-year).**
- SF-133 shows obligations of $220,821,833.28 and outlays of $246,828,290.37. **Both equal File B.**
- File A shows $120,821,833.28 and $146,828,290.37, about $100.0M lower on obligations, outlays and TBR. On the SF-133, TBR rose from $130.0M at P11 to $221.0M at P12, while File A shows $121.0M.
- This is the only material case where OMB sides with File B. The likely cause is a late P12 adjustment that reached GTAS and File B but not File A. That's an interpretation.
- Effect: DOJ's FY2024 File A headline obligations of $51.908B are probably $98.5M low. OMB, File B and USAspending's chart all show $52.006B.

**Decision (2026-10-16): footnote only. No overrides of File A.**
- Keep File A for FY2024 ($51.908B obligations, $52.286B outlays, $67.061B TBR).
- Attach this footnote to every FY2024 account total, the FY2024 A vs B gap, and the BOP component and 015-1060 federal account in FY2024: "OMB's SF-133 shows $100M more for BOP's no-year Salaries & Expenses account (015-X-1060) than the agency's account balances (File A), matching File B. DOJ FY2024 obligations and outlays may be understated by about $100M (0.19%)."
- The FY2024 A vs B gap (−$98.5M obligations, −$100.0M outlays) and the treatment (a) residual stay as computed, shown negative per 5.3, with the same footnote in the tooltip.
- No `file_a_overrides` table exists. If the same pattern turns up for another agency or year, it is decided case by case; there is no automatic override.

---

## 4. File A vs File B: the two totals

Background: the File A vs File B gap was found in the data and checked independently,
including against OMB's SF-133.
Justice Connection's editorial choice (2026-10-15): File A is the default headline,
the File B sum is shown alongside, and a toggle switches which one is primary.

### 4.1 Definitions

| Metric | Formula | Source |
|---|---|---|
| `obligations_a` | `sum(obligations_incurred)` | `account_balances` (File A) |
| `obligations_b` | `sum(obligations_incurred)` | `account_activity` (File B) |
| `outlays_a` | `sum(gross_outlay_amount)` | `account_balances` |
| `outlays_b` | `sum(gross_outlay_amount_FYB_to_period_end)` | `account_activity` |
| `obligations_gap` | `obligations_a - obligations_b` | derived |
| `outlays_gap` | `outlays_a - outlays_b` | derived |
| `gap_pct` | `gap / abs(measure_a)` | derived |

Both are summed over the same scope (agency, component, federal account or TAS),
the same `agency_code` and the same FY. Every TAS in File A also appears in File B
and vice versa in every DOJ year (checked: 0 orphans either way). An implementation
must still use a FULL OUTER JOIN at TAS level with `coalesce(…, 0)`, so that a
future orphan shows up as gap and doesn't disappear.

```sql
WITH a AS (
  SELECT agency_code, fiscal_year, treasury_account_symbol,
         any_value(federal_account_symbol) AS federal_account_symbol,
         sum(obligations_incurred) AS ob_a, sum(gross_outlay_amount) AS out_a
  FROM account_balances WHERE agency_code = $agency GROUP BY 1, 2, 3),
b AS (
  SELECT agency_code, fiscal_year, treasury_account_symbol,
         any_value(federal_account_symbol) AS federal_account_symbol,
         sum(obligations_incurred) AS ob_b,
         sum(gross_outlay_amount_FYB_to_period_end) AS out_b
  FROM account_activity WHERE agency_code = $agency GROUP BY 1, 2, 3)
SELECT agency_code, fiscal_year, treasury_account_symbol,
       coalesce(a.federal_account_symbol, b.federal_account_symbol) AS federal_account_symbol,
       coalesce(ob_a, 0) AS obligations_a, coalesce(ob_b, 0) AS obligations_b,
       coalesce(ob_a, 0) - coalesce(ob_b, 0) AS obligations_gap,
       coalesce(out_a, 0) AS outlays_a, coalesce(out_b, 0) AS outlays_b,
       coalesce(out_a, 0) - coalesce(out_b, 0) AS outlays_gap
FROM a FULL OUTER JOIN b USING (agency_code, fiscal_year, treasury_account_symbol);
```

This TAS-level table should be materialized (suggested name
`account_ab_reconciliation`). Every reconciliation row in section 5 rolls up from it.

### 4.2 Naming the two measures by source (never "USAspending published")

USAspending publishes **both** numbers, in different places. An independent
check of both API endpoints confirmed this.
- **File A** is the basis of the **agency list and profile header** (API `/api/v2/references/toptier_agencies/`, which sums `AppropriationAccountBalances`). For FY2026 it shows obligations of **$50,791,077,566.03** and outlays of **$51,705,305,343.23**, equal to `obligations_a` and `outlays_a` to the cent. File A also **equals GTAS** obligations to the cent for FY2018, FY2019 and FY2026 (USAspending `/api/v2/reporting/agencies/overview/`, `gtas_obligation_total`). FY2025 is the exception; see 4.6.
- **File B** is the basis of the **budgetary-resources chart endpoint** (`/api/v2/agency/<code>/budgetary_resources/`, which sums `FinancialAccountsByProgramActivityObjectClass`). It's also what every object class and program activity breakdown adds up to.

So the dashboard must **never** label either series "USAspending published".
Exact labels:

| Measure | Series label | Tooltip |
|---|---|---|
| `*_a` | **"Account totals (File A, matches GTAS and USAspending's agency page)"**. Short form: "Account totals (File A)" | "Sum of agency account balances (DATA Act File A). Matches Treasury GTAS and the total on USAspending's agency list." |
| `*_b` | **"Sum of File B breakdowns"** | "Sum of the agency's program activity × object class detail (File B). This is what USAspending's agency budgetary-resources chart shows. Our download differs from that chart by up to $2.2M (FY2025: +$2.20M; FY2026: +$0.95M)." |

The small FY2025/26 difference between our File B sum and USAspending's endpoint
(+$2.20M, +$0.95M; equal to the cent for FY2018/19) is not explained yet. It's
probably refresh timing, or USAspending's `FileBCalculations` excluding some rows.
Our own sum is the one shown, because it's the one that reconciles to the
breakdowns. Link the endpoint figure from the reference JSON in the tooltip.

### 4.3 The gap: same issue for outlays? Yes, with partly different accounts

DOJ, latest period per FY, $M:

| FY | Oblig. A | Oblig. B | Gap | Gap % | Outlays A | Outlays B | Gap | Gap % |
|---|---|---|---|---|---|---|---|---|
| 2017 | 41,392.0 | 41,400.9 | -8.9 | -0.02 | 39,689.0 | 39,698.0 | -9.1 | -0.02 |
| **2018** | 43,648.6 | 39,970.4 | **3,678.2** | **8.43** | 40,193.6 | 38,018.8 | **2,174.8** | **5.41** |
| **2019** | 45,172.6 | 42,341.2 | **2,831.4** | **6.27** | 43,239.9 | 42,150.1 | **1,089.8** | **2.52** |
| 2020 | 47,428.1 | 47,420.5 | 7.7 | 0.02 | 46,275.4 | 46,274.4 | 1.0 | 0.00 |
| 2021 | 44,311.4 | 44,310.5 | 0.8 | 0.00 | 46,185.6 | 46,156.2 | 29.5 | 0.06 |
| 2022 | 49,607.9 | 49,684.1 | -76.2 | -0.15 | 45,874.0 | 45,873.8 | 0.3 | 0.00 |
| 2023 | 55,567.6 | 55,576.2 | -8.6 | -0.02 | 51,455.9 | 51,449.6 | 6.3 | 0.01 |
| 2024 | 51,907.8 | 52,006.3 | -98.5 | -0.19 | 52,285.5 | 52,385.5 | -100.0 | -0.19 |
| **2025** | 51,478.9 | 50,456.4 | **1,022.5** | **1.99** | 53,478.0 | 52,346.3 | **1,131.7** | **2.12** |
| **2026 (P11)** | 50,791.1 | 49,365.8 | **1,425.3** | **2.81** | 51,705.3 | 50,305.2 | **1,400.1** | **2.71** |

Headline roundings: obligations gap FY2018 $3.68B, FY2019 $2.83B, FY2025 $1.02B,
**FY2026 $1.43B** ($1,425,318,467.37). Outlays gap FY2018 $2.175B, FY2019 $1.090B,
FY2025 $1.132B, FY2026 $1.400B.

**Outlays.** The outlay gap is in the same four years and is about the same size,
but the accounts behind it are partly different:

| FY | Obligation gap is mainly | Outlay gap is mainly |
|---|---|---|
| 2018 | ATF S&E 015-0700: `obligations_incurred` sign reversed in File B on all 10 non-zero 0700 TAS (5 of them above $1M; $2.79B swing). OCDETF 015-0323 ($588M) and U.S. Trustee 015-5073 ($233M) **reported as $0** (one placeholder row each). JIST 015-0134 $52M also reported as $0. | **Assets Forfeiture Fund 015-X-5042: $1,377M** (A $2,623.4M vs B $1,246.4M; its obligations agree). OCDETF $513M and U.S. Trustee $210M reported as $0. **ATF outlays agree** (only ATF obligations are flipped). |
| 2019 | ATF 015-0700 sign reversed on all 10 non-zero 0700 TAS (3 above $1M; $2.82B swing on those 3, $2.83B on all, i.e. the whole gap) | **Assets Forfeiture Fund 015-X-5042: $1,071M** (A $2,428.7M vs B $1,358.0M; obligations agree) |
| 2024 | BOP 015-X-1060: File B **exceeds** A by $100M | the same $100M, BOP 015-X-1060 |
| 2025 | Prison Industries Fund 015-X-4500: **whole-account sign reversal** in File B. Obligations, outlays and the unpaid/paid balance columns are all negated; all rows are reimbursable. ($1,022M) | Prison Industries Fund, same reversal ($1,132M) |
| 2026 P11 | Prison Industries Fund, same reversal ($1,417M) | Prison Industries Fund ($1,152M), plus offsetting BOP S&E TAS differences (+$546M on 2026/2026, -$332M on 2025/2029) |

Evidence that File A is right and File B is wrong (independent check): in the raw FY2018
File B, ATF's `obligations_incurred` is negative, but the same rows' component
columns (undelivered and delivered orders, paid and unpaid) are positive and sum
to the File A magnitude. `deobligations_or_recoveries_or_refunds_from_prior_year`
is 0. USAspending's own per-TAS differences endpoint
(`/api/v2/reporting/agencies/<code>/differences/`) lists the same TAS and amounts.

The account-level query is 4.1 above; independent queries reproduced its results.

### 4.4 When to call the gap out (materiality rule)

Don't hard-code years. A gap is **called out** for a given scope, FY and measure when
`abs(gap) >= 0.005 * abs(measure_a)` (0.5%, the same tolerance validate.py uses for
account totals) **and** `abs(gap) >= $1M`, so tiny accounts don't trigger it.
At the DOJ agency level this rule selects exactly FY2018, FY2019, FY2025 and
FY2026, for both obligations and outlays: the years where the File A and File B
totals differ by 1.99% to 8.43%, against 0.19% or less in every other year (section 4.3; mainly ATF and Prison Industries amounts
reported with reversed sign in File B, accounts reported as $0, and Assets
Forfeiture Fund outlays). The largest
non-flagged gap is 0.19% (FY2024).

- Called out: show both figures side by side, the gap in $ and %, and a footnote naming the top accounts (top 3 TAS by `abs(gap)`).
- Not called out: show the File B figure in the tooltip only. The reconciliation row (section 5) is still shown, but it's small.

### 4.5 Toggle

`primary_source ∈ {'A', 'B'}`, default `'A'`. It switches which series is the
headline number and the solid line. The other source is always visible as a
secondary line or tooltip value. The toggle doesn't change TBR (File A only),
execution rate (section 3.4) or award metrics.

### 4.6 USAspending's FY2025 GTAS figure is doubled (flag; don't use)

USAspending's reporting overview (`/api/v2/reporting/agencies/overview/`) shows DOJ
FY2025 P12 `gtas_obligation_total` = **$102,957,812,056.98**. That is exactly 2 ×
File A ($51,478,906,028.49). In FY2018, FY2019 and FY2026 the same field equals
File A to the cent. This is very likely a double count on USAspending's side, not
a File A problem. Rules:
- The dashboard never shows USAspending's GTAS field as a series.
- **Confirmed against OMB's SF-133** (independent reconciliation, 2026-10-15): FY2025 P12 line 2190 sums to **$51,478,906,028.49**, equal to File A to the cent. USAspending's $102.96B GTAS figure is therefore unsupported by OMB's own report.
- Footnote text wherever FY2025 obligations are compared with an external total: "OMB's SF-133 confirms FY2025 obligations of $51.48B, equal to the account total shown. USAspending's reporting page lists a GTAS figure of $102.96B, exactly double; that figure is not supported by the SF-133 and appears to be a USAspending error."

---

## 5. Breakdowns from File B and the reconciliation row

### 5.1 Object class groups

Source: `account_activity.object_class_code` (format `NN.N`; OMB Circular A-11
section 83). Two levels:

**Level 1: dashboard groups (4 + Unknown + reconciliation).**

| Group (display) | `group_key` | Object class codes | Notes |
|---|---|---|---|
| Payroll & benefits | `payroll` | 11.1, 11.3, 11.5, 11.6, 11.7, 11.8, 12.1, 12.2, 13.0 (all `1x.x`) | Includes military personnel (USPHS officers at BOP) and benefits for former personnel |
| Contracts, services & purchases | `contracts` | 21.0-26.0 (all `2x.x`) and 31.0, 32.0 (all `3x.x`) | Includes GSA rent (23.1), utilities (23.3), and goods and services from **federal** sources (25.3, intragovernmental). Also equipment (31.0) and land & structures (32.0). This is **not** the same as contract award obligations (section 7). |
| Grants | `grants` | 41.0 only | Grants, subsidies and contributions |
| Other | `other` | 42.0, 43.0, 44.0, 91.0, 92.0, 93.0, 94.0, 99.x | Insurance claims and indemnities (42.0: 9/11 VCF, USVSST, RECA claims), interest, refunds, unvouchered, financial transfers |
| Unknown object class | `unknown` | 00.0, NULL, or any code not matched above | Shown as its own row, never folded silently. $361M in FY2025 (RECA payment account); **$6.5B in FY2026** (RECA accounts, see 5.4) |
| Reconciling / residual row | `reconciling` | n/a | Section 5.3, treatment (a) (the default) |

Mapping expression (works with or without the dot):

```sql
CASE
  WHEN object_class_code IS NULL                                   THEN 'unknown'
  WHEN left(replace(object_class_code, '.', ''), 1) = '1'          THEN 'payroll'
  WHEN left(replace(object_class_code, '.', ''), 1) IN ('2', '3')  THEN 'contracts'
  WHEN left(replace(object_class_code, '.', ''), 2) = '41'         THEN 'grants'
  WHEN left(replace(object_class_code, '.', ''), 1) IN ('4', '9')  THEN 'other'
  ELSE 'unknown'   -- includes 00.0
END
```

**Level 2: OMB major classes**, for drill-down. These are the same as the
`object_class_major` in `object_class_year`: 1 Personnel compensation & benefits;
2 Contractual services & supplies; 3 Acquisition of assets; 4 Grants & fixed
charges; 9 Other; 0 Unknown. Level 3 is the individual object class code.

Implementation note: `object_class_year` currently maps `0` to
`'Unknown'` through the ELSE branch, which is fine, but the label for `4` is "Grants
& fixed charges", which includes 42-44. The dashboard's "Grants" group is 41.0
only. Keep the two levels distinct in the marts.

**Formula (per group, per scope):**
`obligations_b_group = sum(obligations_incurred)` and
`outlays_b_group = sum(gross_outlay_amount_FYB_to_period_end)` from
`account_activity`, grouped by `group_key`, filtered to `agency_code = $agency`,
`fiscal_year = $fy`, and the scope's federal accounts.

**DOJ FY2025 obligations, $M:** payroll 22,557.1; contracts 21,766.4; grants 3,498.9;
other + unknown 2,634.1; sum (File B as reported) 50,456.4; reconciling row 1,022.5; **total
51,478.9 = File A**. Under treatment (a) (5.3), the Prison Industries flip moves +$1,022.5M
into payroll and contracts and the residual becomes $0.0M.

### 5.2 Program activity

- **Source:** `account_activity.program_activity_code`, `program_activity_name`, within `federal_account_symbol`. A program activity is only meaningful inside its federal account, so always key on `(federal_account_symbol, program_activity_code)`.
- **Formula:** as in 5.1, grouped by program activity.
- **FY2026 break:** for FY2026, File B carries **no program activity code or name** for any row (100% NULL). Instead it carries `program_activity_reporting_key` (PARK, e.g. `5ZCB0ZVD70G`), the new OMB key. Until a PARK-to-name reference is loaded, FY2026 program activity can only be shown as raw PARK codes. Codes from FY2025 and earlier don't map one-to-one to PARKs, so there's **no continuous program-activity time series across FY2025/FY2026**. The dashboard should show program activity for one FY at a time in v1. (Data request in OPEN.)
- **Caveat:** 0128 General Legal Activities is the only way to see the litigating divisions separately in account data: Civil Rights Matters ($196M FY2025), Criminal, Civil, ENRD, Tax, OSG, OLC, INTERPOL, Pardon Attorney. That split exists through FY2025 only, until the PARK names are loaded.

### 5.3 Reconciling File B breakdowns to the File A total

Purpose: every File B breakdown (object class, program activity) must add up to the
File A headline for the same scope. A plain "not reported in File B" row (A − B) is
**not enough**, for two reasons found in independent review:

1. **Sign-flipped accounts.** For ATF S&E 015-0700 (FY2018, FY2019) and the Prison Industries Fund 015-X-4500 (FY2025, FY2026), File B did not omit the account. It reported it **with the sign reversed**. Shown as reported, the object-class chart has negative ATF payroll. One example: ATF object class 11.1 is -$417.9M on a single row (TAS 2018/2018, Direct, Law Enforcement Operations), and -$486.2M across all ATF TAS in FY2018. In the File B view, ATF's payroll group is -$860M (FY2018) and -$873M (FY2019), and contracts & purchases are -$551M and -$540M. The agency's payroll group is understated by about $1.7B and contracts by about $1.1B. An A − B row then adds back **twice** the account (+$3.68B in FY2018) in no object class at all. So the total reconciles but the composition is wrong. For Prison Industries the effect is -$361M/-$585M on contracts and -$150M/-$123M on payroll (FY2025/FY2026).
2. **Negative residuals.** File B exceeds File A in some years: obligations -$76.2M (FY2022) and -$98.5M (FY2024); FY2024 outlays -$100.0M (BOP 015-X-1060). Smaller cases are FY2017 and FY2023. Any reconciling row must be allowed to go negative.

Two treatments follow. **Justice Connection chose (a)** (2026-10-15). It is the
dashboard default. (b) stays available as the "as reported" view. Both use the
TAS-level table from 4.1.

#### Shared definitions

**Sign-flip register.** A seed table `file_b_sign_flips(agency_code, fiscal_year,
treasury_account_symbol, measure, verified_by, verified_on, evidence)`, where
`measure ∈ {'obligations', 'outlays'}`. A pair goes in only after it is verified.
The detection rule below proposes candidates. Each one is confirmed by an independent check, for
example against the raw File B component columns or USAspending's
`/reporting/agencies/<code>/differences/` endpoint.

Candidate rule, per (FY, TAS, measure):
`abs(m_A) >= 1e6 AND sign(m_A) <> sign(m_B) AND abs(m_A + m_B) <= greatest(1000, 0.001 * abs(m_A))`.

For DOJ it selects exactly these pairs. All are confirmed by independent raw-file checks, and by OMB SF-133 (positive signs, magnitudes equal to File A). The ATF reversal actually covers all 10 non-zero 0700 TAS in each year. The rule's $1M floor admits 5 (FY2018) and 3 (FY2019); the rest are below $1M and stay in the residual. Registering them too is optional (about $7.3M in FY2019).

| FY | TAS | Measures flipped |
|---|---|---|
| 2018 | 015-2015/2015-0700-000, 015-2016/2016-0700-000, 015-2017/2017-0700-000, 015-2018/2018-0700-000, 015-X-0700-000 | obligations only (ATF outlays agree with A) |
| 2019 | 015-2018/2018-0700-000, 015-2019/2019-0700-000, 015-X-0700-000 | obligations only |
| 2025 | 015-X-4500-000 | obligations and outlays |
| 2026 | 015-X-4500-000 | obligations and outlays |

The flip is **per measure**. Flipping a TAS for obligations negates
`obligations_incurred` on every File B row of that TAS and FY. Flipping it for
outlays negates `gross_outlay_amount_FYB_to_period_end`.

**Scope.** As in 4.1: the set of TAS selected by the agency, component and
federal-account filters. Every row below is a sum over TAS, so agency = Σ components
= Σ federal accounts.

**When a reconciling row exists.** Only when the breakdown is **unfiltered within
File B dimensions** (all object classes, all program activities, direct and
reimbursable). When a File B dimension is filtered (e.g. "Payroll only"), File A has
no matching slice. Hide the row and show the footnote "File B detail; does not
reconcile to the File A total."

#### Treatment (a), the default (Justice Connection's choice): sign-corrected File B plus a residual row

```
m_B_corr(TAS,y)  = -m_B(TAS,y) if (y, TAS, m) is in the sign-flip register, else m_B(TAS,y)
residual(S,y,m)  = sum over TAS in S of [ m_A(TAS,y) - m_B_corr(TAS,y) ]
```

- Breakdown rows use `m_B_corr` at row level (object class, program activity).
- One reconciling row, **"Other difference from account totals"**, equals `residual`. It is signed and can be negative.
- Every chart, table and export that includes a corrected (FY, TAS) carries a visible note, not tooltip-only: **"Sign corrected: [account] reported [obligations/outlays] with reversed sign in File B for FY[y]; shown here with the sign reversed back to match File A."** The mart carries `sign_corrected boolean` at row level and `n_sign_corrected_tas` at scope level.
- Resulting DOJ residuals, in $M (obligations / outlays): FY2017 -8.9 / -9.1; **FY2018 885.8 / 2,174.8**; FY2019 10.9 / 1,089.8; FY2020 7.7 / 1.0; FY2021 0.8 / 29.5; FY2022 -76.2 / 0.3; FY2023 -8.6 / 6.3; FY2024 -98.5 / -100.0; FY2025 0.0 / 0.0; FY2026 8.1 / 248.4.
- What stays in the residual after correction:
  - **FY2018 obligations ($885.8M):**
    - OCDETF 0323, $588.2M across 2 TAS
    - U.S. Trustee 5073, $233.1M
    - JIST 0134, $51.5M
    - Fees & Expenses of Witnesses 015-X-0311, **+$32.2M** (partly reported: A $296.4M vs B $264.2M; not $0)
    - General Administration 0129, +$7.3M
    - Working Capital Fund 4526, **−$27.5M** (File B higher)
    - small items
  - **FY2019 obligations ($10.9M):** about $7.3M of small ATF TAS that are sign-reversed but below the rule's thresholds (e.g. 015-2017/2017-0700 +$3.4M), plus small items.
  - **FY2018/19 outlays:** mostly the Assets Forfeiture Fund ($1,377.1M / $1,070.7M, confirmed by SF-133), plus OCDETF ($513.5M) and Trustee ($210.3M) in FY2018.
  - **FY2026 outlays ($248.4M):** offsetting BOP S&E TAS differences (+$545.6M / −$332.2M) plus small items.
  - **FY2024 (−$98.5M / −$100.0M):** BOP 015-X-1060, where SF-133 sides with File B (3.6). It is footnoted, not overridden (2026-10-16), so this residual stays.
  - The tooltip lists the top 3 contributors by absolute value, with sign.
- Label of the residual row: positive → **"Not in File B detail (reported as $0 or lower)"**; negative → **"File B detail exceeds account totals"**.
- Why chosen: the composition (payroll, contracts) is right for the affected years. The evidence for the flip is strong: the magnitudes equal File A, and in the raw files `obligations_incurred` contradicts File B's own component columns. The correction is narrow (8 TAS-years, all verified) and disclosed.
- Risk: we are publishing numbers that differ from the agency's own File B and from USAspending's breakdowns. The note must say so, and the "as reported" view (b) should remain one click away.

#### Treatment (b), the alternate "as reported" view: File B as reported plus a reconciling row

```
reconciling(S,y,m) = sum over TAS in S of [ m_A(TAS,y) - m_B(TAS,y) ]   -- = m_A(S) - m_B(S)
```

- Breakdown rows are File B as reported, including negative ATF and Prison Industries rows.
- One reconciling row, **"Difference from account totals (not reported, or reported with reversed sign, in File B)"**, signed.
- DOJ values = the gap column in 4.3 (e.g. obligations FY2018 +$3,678.2M, FY2022 -$76.2M, FY2024 -$98.5M, FY2026 +$1,425.3M).
- Each affected chart carries a note naming the flipped accounts, e.g.: "ATF S&E obligations appear negative because the agency reported them with reversed sign; the reconciling row adds back twice that amount."
- Pros: every bar matches the agency submission and USAspending. Cons: object-class composition is visibly wrong in FY2018, FY2019, FY2025 and FY2026, which invites misreading (e.g. "DOJ payroll fell $1.7B in FY2018").

#### Display rules (both treatments)

1. The reconciling/residual row is always last, visually distinct (grey, hatched), and never sorted in among the object classes.
2. It is shown whenever `abs(row) >= $0.5M` at that scope. It is **called out** (footnote listing the top 3 TAS by absolute contribution) under the 4.4 materiality rule. Under (a) the materiality test uses the residual, so FY2018/19 outlays and FY2018 obligations would still be called out, and FY2025 would not.
3. **Negative values** are kept negative. Never floor them at zero, and never take the absolute value. In tables they show as negative numbers. In stacked bars they're drawn below the zero line (diverging stack), and the total marker stays at the File A value. Don't use treemaps or pies for File B breakdowns.
4. Mixed signs within a scope: the row is net, so the tooltip lists TAS-level contributions whenever there are both signs (e.g. DOJ FY2026 BOP S&E outlays +$546M / -$332M).
5. Toggle interplay: when the primary series is File B (4.5), the headline is the uncorrected File B sum under either treatment. Sign correction applies only to breakdowns reconciled to File A.

### 5.4 Negative values inside File B breakdowns (separate from the gap)

File B object class cells can be negative even where the account total agrees
with File A. The data shows this; it isn't a gap.
- **FY2026 RECA:** 015-0333 reports +$4,355.2M in 00.0 and −$2,177.6M in 42.0, netting to File A's $2,177.6M. 015-8116 reports +$2,177.6M in 00.0 and −$1,657.4M in 42.0, netting to File A's $520.2M. RECA's two accounts therefore carry **−$3,835.0M in 42.0**.
- Other accounts carry positive 42.0 (9/11 VCF 015-0139 +$2,116.7M; Public Safety Officers' Benefits 015-0403 +$192.1M; others about +$21M). So **agency-wide FY2026 42.0 is −$1,504.5M** (outlays −$1,549.5M).
- As a result, the agency-level **"Other" group is negative in FY2026: −$1,504.2M obligations, −$1,549.3M outlays**. It's the only negative headline-or-Other group in any year. "Unknown" was also negative once: FY2019 obligations, −$401.8M after sign correction (−$403.6M as reported), driven by the Working Capital Fund's −$542.3M; see below. All three cases are registered as `file_b_negative_group` issues (section 11). In FY2026, "Unknown" is +$6,548.2M (outlays +$6,527.5M). Unknown + Other net to +$5.04B obligations, which reconciles because the RECA entries are offsetting.
- **Chart handling for FY2026:**
  1. Draw "Other" as a negative bar below the axis (diverging stack), with no flooring.
  2. Attach a visible annotation, not tooltip-only, to both "Other" and "Unknown": "FY2026: RECA accounts (015-0333, 015-8116) report $6.5B under 'unknown' object class and −$3.8B under claims (42.0). The two offset; RECA's net obligations are $2.70B. Other being negative is an artifact of this reporting."
  3. Offer a drill-down to object class × account.
  4. Don't compute year-over-year changes for "Other" or "Unknown" across FY2025/26.
  5. In any chart that only has room for positive stacks (e.g. small multiples), merge "Other" and "Unknown" for FY2026 into one segment labelled "Other incl. unknown object class (net)", +$5.04B, and footnote it.
  - The sign-flip register (5.3) does **not** apply here. The RECA account totals agree with File A, so this is a within-account misclassification, not a sign reversal.
- **FY2019 Working Capital Fund (015-4526):** -$542M in 00.0.

Rule: object class groups are signed sums. Never drop negative rows, and never
floor a group at zero. If a group is negative for a scope and FY, show it as
negative, with a data-quality flag listing the TAS. The suggested mart column is
`has_negative_detail`.

---

## 6. Component mapping

The same reader-facing "component" (FBI, BOP, OJP, ...) is derived in two
**different** ways, and the two are not reconcilable one-to-one:
- **Account side** (budget, obligations, outlays; File A and B): component = f(federal account), from the table in 6.1.
- **Award side** (contracts, grants; D1/D2/F): component = f(awarding sub-agency, awarding office), from 6.2.

Label charts accordingly: "Component (by federal account)" vs "Component (by
awarding office)". An award total for "FBI" is not a subset of the FBI account
total in any exact sense. The award-to-account links (`federal_accounts_funding_this_award`: the list of federal accounts that funded an award; contracts FY2017+, awarding definition) show the main cross-overs.

These are **not dollars attributed to the account**. Two measures are given:
- "**Linked**": the full net obligations of contracts whose funding list *includes* the account. A contract funded by several accounts counts in full under each.
- "**Linked to this account only**": contracts whose funding list is *only* that account. This is a floor on the account's share.

Without File C, no exact attribution exists.

| Awarding component | Assets Forfeiture Fund (015-5042), linked | AFF, linked only | Working Capital Fund (015-4526), linked | WCF, linked only |
|---|---|---|---|---|
| Drug Enforcement Administration | $1,520M | $670M | — | — |
| ATF | $1,113M | $151M | — | — |
| U.S. Marshals Service | $653M | $282M | — | — |
| Offices, Boards and Divisions | $1,407M | $794M | $7,487M | $4,099M |
| FBI, BOP | none | none | none | none |

USMS "linked only" is $281.8M when filtered by awarding sub-agency 1544, which is the figure here. An independent check's $289M likely uses a different scope (e.g. $291.6M if rows only funded by USMS are included); to be reconciled.

The component bridge seed (`sql/seeds/component_bridge.csv`) follows these links (production v3.5.1): DEA, ATF and USMS → AFF added; BOP → WCF and OVW → Crime Victims Fund removed.

### 6.1 Account side: federal account to component (DOJ, `agency_code = '015'`)

Keyed on `(agency_code, federal_account_symbol)`. This table is the spec for a
seed/lookup table (suggested `sql/seeds/component_map.csv`). For agencies without a curated map, fall back to
`component = federal_account_name`. Any federal account in the data that isn't
in the map must go to `component = 'Unmapped: ' || federal_account_name`, and
validate.py should WARN on it.

| Component group | Component | Federal accounts | Notes |
|---|---|---|---|
| FBI | Federal Bureau of Investigation | 015-0200 S&E; 015-0203 Construction | |
| Bureau of Prisons | Bureau of Prisons | 015-1060 S&E; 015-1003 Buildings & Facilities; 015-8408 Commissary Funds | 1060 includes HHS child TAS `075-015-…-1060` |
| Bureau of Prisons | Federal Prison Industries (UNICOR) | 015-4500 Prison Industries Fund | Separate component because it's revolving and reimbursable, and it's the FY2025/26 File B problem account. Rolls up to the BOP group. |
| U.S. Marshals Service | U.S. Marshals Service | 015-0324 S&E; 015-0133 Construction; 015-1020 Federal Prisoner Detention; 015-4575 JPATS Fund; 015-0136 Detention Trustee (FY2017 only, predecessor of 1020) | |
| DEA | Drug Enforcement Administration | 015-1100 S&E; 015-1101 Construction; 015-5131 Diversion Control Fee Account | |
| ATF | ATF | 015-0700 S&E; 015-0720 Construction | |
| U.S. Attorneys | U.S. Attorneys (incl. EOUSA) | 015-0322 S&E | |
| Grant-making offices | Office of Justice Programs | 015-0401 Research, Evaluation & Statistics; 015-0403 Public Safety Officers' Benefits; 015-0404 and 015-0405 State & Local Law Enforcement Assistance; 015-0420 OJP S&E (to FY2021); 015-5041 Crime Victims Fund; 015-8306 Gifts, CVF; 015-5606 Domestic Trafficking Victims' Fund; 015-0334 Weed & Seed; 015-0410 BRIDGE Fund (OBBBA, FY2025+) | Account-side OJP is broader than "OJP-awarded grants". Award-to-account links tie OVW grants to 015-0409, not to the Crime Victims Fund 5041. All grants whose funding list includes 0409 total $4,700M. Of that, $4,188M are grants from the OVW office, and $512M have no OVW office recorded (independent check: $4,187M / $513M; the $1M difference is rounding or the office filter). No OVW-office grant is linked to 5041. Any CVF money for OVW programs reaches them as a transfer into 0409's resources, not as CVF-funded awards. |
| Grant-making offices | Office on Violence Against Women | 015-0409 | |
| Grant-making offices | COPS Office | 015-0406 | |
| Grant-making offices | OJP/COPS/VCRP legacy account | 015-8594 | FY2017-2020, ~$0; map to OJP |
| Litigating & legal offices | General Legal Activities (Civil, Criminal, Civil Rights, ENRD, Tax, OSG, OLC, INTERPOL, Pardon Attorney) | 015-0128 | Split by division only through File B program activity (5.2) |
| Litigating & legal offices | OBBBA sec. 100054 activities (General Legal Activities) | 015-0140 (FY2026+) | $3.57B TBR, $1.01B obligated FY2026 P11. Statutory purpose not yet confirmed from the enrolled text (OPEN). |
| Litigating & legal offices | Antitrust Division | 015-0319 | |
| Litigating & legal offices | National Security Division | 015-1300 | |
| Litigating & legal offices | U.S. Trustee Program | 015-5073 | |
| Litigating & legal offices | Fees & Expenses of Witnesses | 015-0311 | |
| Litigating & legal offices | Independent Counsel | 015-0327 | |
| Adjudication & other offices | Executive Office for Immigration Review | 015-0339 | |
| Adjudication & other offices | U.S. Parole Commission | 015-1061 | |
| Adjudication & other offices | Community Relations Service | 015-0500 | |
| Adjudication & other offices | Foreign Claims Settlement Commission | 015-0100; 015-0104 | |
| Compensation funds | September 11th Victim Compensation Fund | 015-0139; 015-0340 (to FY2020) | |
| Compensation funds | U.S. Victims of State Sponsored Terrorism Fund | 015-5608 | |
| Compensation funds | Radiation Exposure Compensation (RECA) | 015-0333 Payment to RECA Trust Fund; 015-8116 RECA Trust Fund | 0333 pays into 8116, so both count (3.2 caveat) |
| Department management & shared funds | General Administration (JMD, leadership offices) | 015-0129; 015-0132 TLEWC; 015-0134 JIST; 015-1102 NDIC (FY2017) | |
| Department management & shared funds | Office of the Inspector General | 015-0328 | |
| Department management & shared funds | Working Capital Fund | 015-4526 | Mostly reimbursable work for other DOJ components |
| Department management & shared funds | Assets Forfeiture Fund | 015-5042 | |
| Department management & shared funds | OCDETF (Interagency Crime & Drug Enforcement) | 015-0323 | |
| Department management & shared funds | Justice Gift Fund | 015-8305 | |

That's 56 federal accounts in FY2017-FY2026, and all 56 are mapped. Component and
group names are accepted for v1 (2026-10-15).

### 6.2 Award side: sub-agency and office to component

Source columns in `prime_transactions`: `awarding_sub_agency_code`,
`awarding_sub_agency_name`, `awarding_office_name`, `funding_sub_agency_name`.
There's no funding office column in the database. The funding definition is
covered in rule 5.

Rules, applied in order:
1. **Assistance (grants)**, by `awarding_office_name`:
   - `OFFICE ON VIOLENCE AGAINST WOMEN` → **OVW**
   - `COMMUNITY ORIENTED POLICING SERVICE` → **COPS**
   - `OJP …` (BJA, OVC, OJJDP, NIJ, BJS, SMART) → **OJP**. Keep the office as `program_office` for drill-down (e.g. "OJP / Bureau of Justice Assistance").
   - Office NULL, resolved in order:
     1. Fill from the same `award_key`'s most recent non-null office.
     2. If still NULL, use the assistance listing (`program_code`): take the office that awards at least 95% of that listing's rows with a known office. This can be a seed, `listing_office_map`, derived from the data. Examples: 16.575 VOCA → OVC (OJP); 16.588 and 16.017 → OVW; 16.710 → COPS if it passes 95% (8,148 COPS vs 359 BJA rows, i.e. 96%).
     3. If still NULL: **not a separate component** (decided, answering the data contract's question). Sub-agency 1550 → component **Office of Justice Programs**, with `program_office = 'OJP (office not reported)'`. Sub-agency 1501 → component **Offices, Boards and Divisions**, with `program_office = 'Office not reported'`.
     - Why: sub-agency 1550 only issues OJP-bureau awards (plus some OVW awards, which step 2 catches), so the component is known even where the bureau isn't. A separate "$0.57B unknown" component would understate OJP in FY2017-18, which is where the nulls are concentrated (FY2017 $3.36B and FY2018 $0.48B before filling).
   - **Important:** OVW and COPS awards carry sub-agency **1501 "Offices, Boards and Divisions"**, not OJP. Using `awarding_sub_agency_name` alone would put about $7B of OVW and COPS grants under "Offices, Boards and Divisions".
2. **Contracts:** by `awarding_sub_agency_name`, normalized to the component names in 6.1 (FBI; BOP; Federal Prison Industries; USMS; DEA; ATF; OIG; OJP). Sub-agency 1501 stays **Offices, Boards and Divisions**, with `awarding_office_name` as drill-down (JMD Procurement Services accounts for $14.2B of 1501's **$17.5B net ($19.2B gross)** contract obligations in the FY2017+ window; 1501's $25.2B total also includes $7.7B of assistance, mostly OVW and COPS).
3. Case-normalize names. The sub-award file has uppercase sub-agency names for contracts ("FEDERAL BUREAU OF INVESTIGATION") and mixed case for assistance.
4. **Generic fallback (any agency without a curated award-side map):** `component = awarding_sub_agency_name` (funding toggle: `funding_sub_agency_name`), case-normalized. NULL becomes "Sub-agency not reported". Rules 1-2 above are the DOJ-specific map (sub-agency codes 1550/1501 and DOJ office names). Store them as a seed keyed by `agency_code`, never as inline CASE logic.
5. **Funding definition** (decided, answering the data contract's question):
   - Rows where the **awarding agency is the same agency** (`awarding_agency_code = agency_code`, about 97-99% of DOJ-funded dollars each year): apply rules 1-3 exactly as under awarding, using the awarding office. Do **not** switch to `funding_sub_agency_name`. It is DOJ's own grant office either way, and switching would move about $7B of OVW and COPS grants into "Offices, Boards and Divisions" just by toggling the definition, which no reader would expect.
   - **Funding-only rows** (awarded by another agency, funded by DOJ; 20,453 transactions): component = `funding_sub_agency_name`, normalized as in rule 2. There's no DOJ office to use.
   - Funding sub-agency **"Department of Justice" or "JUSTICE, DEPARTMENT OF"** → **"Department of Justice (sub-agency not specified)"**. The seed mapping does this. It is mostly contracts awarded by other agencies on DOJ's behalf ($158.9M funding-only, $93.4M DOJ-awarded; 4,588 transactions).
   - Funding sub-agency **NULL** (1,374 DOJ-awarded assistance rows, net −$30.7M) → also "Department of Justice (sub-agency not specified)". Under rule 5's first bullet, though, these rows take their component from the awarding office. So the bucket only catches funding-only rows with NULL.

Alternative for grants: `federal_accounts_funding_this_award` links ≥99% of
grant dollars to a single federal account (0406 COPS, 0409 OVW, 0404 OJP ...), so
the account-side map could also be applied to awards. It is less reliable for
contracts (coverage 74-98% of dollars, and 9-20% of dollars link to several
accounts). It's not used in v1. It's noted here because it could later let award
and account views share one component definition.

---

## 7. Award metrics

Source: `prime_transactions` (D1 contracts + D2 assistance, merged and
deduplicated on `transaction_key`), with `prime_awards` for award-level rollups.

### 7.1 Award obligations

- **Meaning:** Net new obligations on prime awards, by the fiscal year of the action date.
- **Formula:** `sum(federal_action_obligation)`.
- **Default filter (awarding):** `agency_code = $agency AND awarding_agency_code = $agency`.
- **Funding toggle:** `agency_code = $agency AND funding_agency_code = $agency`.
- **FY:** `fiscal_year` (FY of `action_date`).
- **Label on every award chart:** "Awarding agency: DOJ" or "Funding agency: DOJ". The definition in use must be visible, not just in a tooltip.
- **Validation:** awarding totals match USAspending `spending_over_time` (awarding filter) to the cent for FY2017-FY2024 and FY2027. For FY2025 ours is **-$24,960** lower, and for FY2026 **-$526,270** lower (within 0.005%). This is likely snapshot timing: the award zips and the reference JSON were pulled about 6 hours apart on Oct 15. Never claim prime awards match "to the dollar". Only sub-awards match exactly in every year.
- **DOJ size of the difference:** the funding definition is $0.16-0.52B lower per year. Each year about $0.5-0.7B is awarded by DOJ but funded by another agency, and $0.13-0.34B is funded by DOJ but awarded by another agency (20,453 funding-only transactions in all).
- **Caveats:**
  - Net of de-obligations. A year with large terminations shows lower net obligations, not a separate negative bar. Section 7.6 adds the gross split.
  - Award obligations (about $11-16B a year) are a **subset** of account obligations (about $41-55B). The difference is mostly payroll, rent, intragovernmental payments, and the compensation funds' claim payments. Never show award obligations as a share of File B object class "contracts"/"grants", and never mix the two in one stack.
  - `prime_awards.obligated_in_window` is the sum of the award's transactions **within the pulled window** (FY2017 onward), not its lifetime value.

### 7.2 Award type groups

These reproduce USAspending's `spending_over_time` categories exactly (verified
FY2017-FY2024 and FY2027 to the cent; FY2025/FY2026 contracts differ by $25K and
$526K, which is consistent with refresh timing).

| Group | Rule | DOJ codes present |
|---|---|---|
| Contracts | `award_category = 'contract' AND award_key NOT LIKE 'CONT_IDV_%'` | A BPA call, B purchase order, C delivery order, D definitive contract |
| IDVs | `award_key LIKE 'CONT_IDV_%'` (`award_type_code` is NULL on these rows; the type is in `contract_transactions.idv_type_code`) | IDV_A-E |
| Grants | `award_category = 'assistance' AND award_type_code IN ('02','03','04','05')` | 02 block, 03 formula, 04 project, 05 cooperative agreement |
| Direct payments | `award_type_code IN ('06','10')` | 06: one transaction, $0 |
| Loans | `award_type_code IN ('07','08')` | none |
| Other | anything else, including `'09'`, `'11'`, `'-1'`, NULL on assistance | none |

Caveat: 10,770 assistance rows have `award_type_code` but NULL `award_type`
text. Derive display text from the code, never from `award_type`.

Note: USAspending's "Grants" category includes cooperative agreements (05). The
dashboard follows that.

### 7.3 Recipients

- **Attribution:** recipient dollars are attributed **per transaction**, to each transaction's own recipient, not to the award's latest recipient (2026-10-16). This matches USAspending's recipient pages and the tier-2 templates. Where an award changes recipient (novation), its earlier actions stay with the earlier recipient.
- **Identity:** group key = `coalesce(recipient_uei, '__NO_UEI__')`. Never group by name, because names vary across actions.
- **Display name:** for a real UEI, the most recent `recipient_name` (`arg_max(recipient_name, action_date)`). For `'__NO_UEI__'`, the fixed label **"Recipient not identified"**.
- **No-UEI rows:** there are 6 transactions, and they are **not** $0. They net **$274,548.54**: contracts +$106,023.13 and +$598.50 (Zenith Electronics); assistance +$167,939.00, −$12.09, $0 and $0. They are never dropped, and in top-recipient lists they are ranked like any other group.
- **Parent rollup:** `recipient_parent_uei`/`recipient_parent_name`, as a toggle. `recipient_parent_uei` is NULL on 40% of assistance transactions, and `recipient_parent_name` on 31% (state and local governments mostly). Fall back to the recipient's own key (UEI, or `'__NO_UEI__'`).
- **Top recipients:** rank by `sum(federal_action_obligation)` over the selected FY range and filters. Show net obligations and the number of awards. Ties go to the lower UEI.
- **Caveat:** for grants the top recipients are mostly state administering agencies that pass money through. Link to sub-award flows (section 8).

### 7.4 State

- **Default: recipient location**, `recipient_state_code` (NULL 0.3% contracts, 0% assistance; 55-56 values including DC, territories and military "states").
- **Toggle: place of performance**, `pop_state_fips` / `pop_state_name` (NULL 4.0% contracts). USAspending's map defaults to place of performance, so traceability links must say which basis they use.
- **Contract place-of-performance caveat** (always shown with the toggle on contracts): "Place of performance for contracts often repeats the contractor's address ({share}% of contract dollars in {FY}); work may be done elsewhere." The share is dollars whose place-of-performance ZIP+4 equals the contractor's ZIP+4: 20–23% in FY2017–20, 43–56% in FY2022–26. The match is the same 9-digit ZIP+4 test as the `pop_equals_contractor_address` rule (11.2).
- Foreign recipients (0.2% of contract transactions) and NULLs go to an "Foreign / unknown" bucket, never dropped.
- The default is recipient location (2026-10-15). Sub-awards follow the same rule: default `subawardee_state_code`, with sub-award place of performance as the toggle.

### 7.5 Award drill-down

Row-level via the API: transaction list for an award, keyed on `award_key`, with
`usaspending_permalink` as the traceability link. It's parameterized by `award_key`
and `agency_code`, with a row limit.

### 7.6 Gross obligations and de-obligations (supporting)

- `gross_new_obligations = sum(federal_action_obligation) FILTER (WHERE federal_action_obligation > 0)`
- `deobligations = sum(federal_action_obligation) FILTER (WHERE federal_action_obligation < 0)` (negative)
- Net = gross + deobligations = 7.1.

This is needed for any termination story. DOJ grants: deobligations were -$0.15B
in FY2025 and -$0.17B in FY2026, on 1,995 and 2,052 awards.

---

### 7.7 New awards and number of awards

Every Watchdog Desk card uses the new-award definition below: the new-award date, new-award
dollars (the initial award amount), the award cycle, the like-period rules and the attribution rule.
The count toggle is not shown on the Watchdog Desk. The parts marked "earlier dashboard"
belong to an earlier version of the dashboard, whose acceptance case was OVW's drop in the
number of grants.

**Default count: new awards** (earlier dashboard: the toggle). The toggle "Dollars obligated ⇄ Number of awards"
shows the number of **new awards made** in the period. Two alternatives are
available, each labelled:
- **Awards with activity:** awards with at least one action in the period. This is what `mart_awards.n_awards` counts today.
- **Transactions.**

Label the default as "New awards" everywhere. Never say just "awards".

| Count | Meaning | Use | Caveat |
|---|---|---|---|
| **New awards** (default) | Awards whose new-award date falls in the period | "How many grants/contracts were made" | Grants are sensitive to award timing; see award cycle |
| Awards with activity | Distinct awards with ≥1 action (any type) in the period | Workload / active portfolio | **Not comparable across FY2022–23** for assistance: DOJ reported almost no non-financial modifications those years (OVW FY2022: 750 A1, 0 EX). Counts long-running awards every year |
| Transactions | Rows in D1/D2 | Drill-down only | Coding shifts by year; never a headline |

#### New-award date (per award)

**Contracts and IDVs** (FPDS):
- New-award date = the action with `modification_number = '0'` (the base record). There is exactly one per award, and it is always the award's first action (checked for DOJ: 0 exceptions).
- Each delivery order, BPA call and purchase order is its own award, so each counts once when issued.
- **Left-censoring:** awards made before FY2017 have no base record and are never counted as new. Don't use "first seen in the window", which would overcount FY2017.
- **Size band:** contract counts include only new awards whose base-action obligation is **over $10,000**. DOJ's small-award counts break at the start of FY2019 (≤$10K base awards fell from 38,116 to 18,544; awards of $3.5K or less also fell 38%, unexplained). This is consistent with the micro-purchase threshold rising to $10,000. But the FAR change took effect only on 2020-08-31; agencies used class deviations from 2018, and DOJ's own effective date is unknown. Don't describe it as "effective FY2019". The >$10K series isn't affected. Option: a toggle for "all sizes (FY2019 onward only)".

**Assistance (grants, cooperative agreements)** (FABS). The award key is one per FAIN, and supplements reuse the FAIN.
1. New-award date = the date of the FAIN's **first** `action_type = 'New Award'` (A1) action. Later A1 actions on the same FAIN (multi-year increments, supplements; 2 to 303 a year) are **not** new awards.
2. **Fallback**, only where the FAIN has no A1 action at all (common in FY2017–18, when DOJ coded many base awards as "Other Action"): the first action with `modification_number IN ('0','00')`, where either
   - the FAIN's 4-digit year prefix is within ±1 of the action's calendar year, or
   - `period_of_performance_start_date >= action_date − 365 days`.
3. Otherwise the award is pre-window (older grant still active) and is never new. The `-n` suffix (`00-1`, `00-2`) is a sub-record or later action, not a new award.

These rules give DOJ grant new awards by fiscal year of 3,775 (FY2017, still partly censored), 4,373, 4,065, 5,054, 2,913, 8,090, 5,902, 5,197, 2,123 and 1,435 (FY2026 through July 31).

**Why FY2022 shows 8,090**. It's real award timing, not coding: three award cycles land in one fiscal year.

| FY2022 new grants by cycle | Count | When |
|---|---|---|
| FY2021 cycle (late) | 3,349 | mostly Oct–Dec 2021 |
| FY2022 cycle | 4,185 | mostly Jun–Sep 2022 |
| FY2020 cycle | 554 | 552 of them SCAAP (16.606), all in June 2022 |
| Other | 2 | |

- FY2021 is correspondingly low (2,913).
- Only 2 of the 8,090 have an earlier action on the same FAIN.
- SCAAP is awarded about two years after its cycle (the FY2021 cycle's 507 SCAAP awards came mostly in Nov 2022: 499 in Nov, 4 in Dec 2022, 4 in Feb–Mar 2023). So **like-elapsed cycle counts exclude SCAAP for cycles 2020–21**, which are awarded after the cut-off. There are no SCAAP awards for cycles 2022 and later.
- Like-elapsed counts for cycles 2020–21 therefore leave out about 500–550 SCAAP grants each (552 for 2020, 507 for 2021). Those baseline values should carry this note. The OJP cycle-2025 shortfall (644 vs a median of 3,732) is far larger than this effect.

**Continuations and supplements:**
- Not counted as new awards.
- They're counted in "awards with activity", and their dollars are in obligations as usual.
- FABS action type B (Continuation; 78 DOJ rows) and contract option exercises and funding-only actions are never new awards.

**Count is award-level; dollars are transaction-level.** A new award counts once, in the period of its new-award date. Its later actions add dollars to their own periods but never add to the count.

#### Award cycle (grants; agency-specific annotation)

Grant counts by fiscal year swing because a year's competition is often awarded
partly after September 30. DOJ examples:
- 1,607 FY2020-cycle grants were awarded in FY2021;
- 1,471 FY2024-cycle grants were awarded in FY2025 (OJP 1,395, COPS 47, OVW 29);
- 221 OVW FY2025-cycle grants were awarded in FY2026.

So for **assistance**, the dashboard also offers counts **by award cycle**, the
appropriation or solicitation year in the FAIN:
- `^(20\d\d)` through about FY2021 (e.g. `2020WFAX0012` → 2020). Don't require a letter after the year: 46 FAINs such as `202086CXK001` (cycle 2020) would be missed. The trend-signals SQL uses the same pattern;
- `^15[A-Z]{4,5}(\d\d)` from FY2022 (e.g. `15JOVW24GG…` → 2024, `15JCOPS23GG…` → 2023).

The patterns are DOJ-specific. They sit in a seed `award_cycle_patterns(agency_code, regex, year_format)`. For agencies without a pattern, the award cycle is NULL and only the fiscal-year view exists.

- **Earlier dashboard. Decided (2026-10-16): grant counts lead with the fiscal year of the new-award date**, which matches the dollar axis. An **"By award cycle" toggle** sits on every grant count chart and table.
- **Late-award timing note** (earlier dashboard; exact text). Shown whenever a grant count's fiscal-year change and award-cycle change differ by 10 percentage points or more, or have opposite signs:
  > "Part of this change is award timing: some {cycle} grants were awarded after September 30. By award cycle the change is {cycle pct}."

  For the FY2026 column it's always shown, together with the 2.4 cut-off footnote.
- **Trend signals use the cycle view for grant counts** (earlier dashboard). The year-over-year list shows both views: fiscal year of the new-award date and award cycle.

#### Provisional years and like-period counts

Counts react more to missing months than dollars do, because DOJ grants are awarded
mostly in August–September. Rules:
- **Fiscal-year view** with a reporting gap (2.4): compare only the same months in every year, e.g. "Oct–Jul" for FY2026 grants. Label it `FY2026* (Oct–Jul)`, with the 2.4 footnote. Never show a full-year FY2026 grant count next to full earlier years.
- **Cycle view:** count each cycle only through the same elapsed point (**like-elapsed**). For the current data, that's awards made by July 31 of the cycle year + 1. Label: "FY2025 cycle, awards through Jul 31, 2026 (earlier cycles counted to the same point)". A cycle whose awards aren't complete is a floor and is labelled "so far".
- **Contracts:** FY2026 is provisional but complete through September 30. No like-period rule is needed, only the provisional label.

#### Awarding vs funding

The same definitions apply under the funding toggle (7.1). Under awarding, the
new-award transaction has `awarding_agency_code = agency`; under funding,
`funding_agency_code = agency`. Never add the two.

#### Attribution to component, state, program and recipient type

**Per-transaction rule** (2026-10-16): a new award is attributed using
the attributes of **its new-award transaction**:
- component (6.2), recipient state (7.4), place-of-performance state (toggle);
- assistance listing (program);
- recipient type (assistance `business_types_code`; contracts have none in v1);
- award type group.

If several rows share the new-award date (e.g. FABS sub-records `00-1`, `00-2`), use
the row with the largest absolute obligation, then the lowest `transaction_key`. Later
changes (a new office or recipient state on a later modification) don't move the
count.

#### Dollars that go with counts

The count toggle swaps the measure; it doesn't change the dollar definition. Where a
chart shows dollars **for new awards only**, use "new-award dollars": the obligations on
the award's new-award date (the initial award amount). Label it "initial award
amount". It's never added to net obligations (7.1).

#### Mart columns (earlier dashboard)

New table `award_new` (one row per award), with:
- `new_award_date`, `new_award_fy`, `in_like_period` (per the 2.3 cut-off);
- `award_cycle`, `like_elapsed_flag`;
- `component`, `recipient_state`, `pop_state`, `listing`, `recipient_type`, `award_type_group`;
- `new_award_amount`, `size_band`, `used_fallback`.

Rename `mart_awards.n_awards` to `n_awards_active`, and add `n_awards_new` and `new_award_amount`.


## 8. Sub-award metrics

Source: `subawards` (FSRS/SAM reports, contracts and assistance merged), and the
`subaward_flows` view.

### 8.1 Sub-award amount

- **Meaning:** Dollars that prime recipients **reported** passing to sub-recipients.
- **Formula:** `sum(subaward_amount)`.
- **Default filter (awarding):** `agency_code = $agency AND prime_award_awarding_agency_code = $agency`. Funding toggle: `prime_award_funding_agency_code = $agency`.
- **FY:** `fiscal_year` = FY of `subaward_action_date`.
- **Validation:** matches USAspending `spending_over_time` (subawards) to the cent in every FY.
- **Mandatory caption wherever shown:** "Sub-award amounts are self-reported by prime recipients and incomplete. Treat them as a lower bound (a floor), not a total."
- **Caveats:**
  1. **Never add to prime obligations.** Sub-awards are money the prime already obligated, so adding them double counts.
  2. **Not a share of prime obligations in the same FY.** The sub-award FY is the sub-award's action date, and the prime may be from an earlier year. 4,938 sub-awards (3.3%) attach to primes outside the FY2017+ window.
  3. **Implausible amounts: a class of records, handled by rule.**
     - **Flag `implausible_amount`:** `prime_award_amount > 0 AND subaward_amount >= 10 * prime_award_amount AND subaward_amount >= 100000000`.
     - For DOJ this flags **17 rows, $18.33B**. All 17 were reviewed and classed as likely keying errors.
     - The largest is the FY2021 National CASA record, $10,541,201,020 under a $32.1M prime, whose amount equals the digits of its own sub-award number.
     - **Default (2026-10-16): exclude every row with the flag**, i.e. `NOT implausible_amount`, which covers all 17 DOJ rows including CASA.
     - A toggle "Include records flagged as implausible (matches USAspending)" restores them.
     - Required visible note on every sub-award total, chart and export: "Excludes N sub-award records totaling $X flagged as implausible (≥10× their prime award and ≥$100M); list available." For DOJ, N = 17 and $X = $18.33B overall; per-FY values are in the table below. The note links to the list.
     - Effect of the full rule (awarding, $M):

       | FY | Before | After | Change |
       |---|---|---|---|
       | 2017 | 3,953.1 | 2,484.8 | −37.1% |
       | 2018 | 4,377.3 | 3,390.2 | −22.5% |
       | 2019 | 2,931.3 | 2,931.3 | 0 |
       | 2020 | 5,192.3 | 3,362.2 | −35.2% |
       | 2021 | 13,767.4 | 3,226.2 | −76.6% |
       | 2022 | 3,233.0 | 3,033.0 | −6.2% |
       | 2023 | 5,086.1 | 2,864.1 | −43.7% |
       | 2024 | 3,999.1 | 2,918.6 | −27.0% |
       | 2025-2027 | unchanged | | |

     - Second tier, **flag only, not excluded** (2026-10-16) (`subaward_review_flag`): positive prime, `subaward_amount > prime_award_amount` and `>= $10M`, not already flagged. That's 28 rows and $2.05B, shown in drill-down and not excluded. The ratio is weaker evidence there, especially for contract sub-awards, where `prime_award_amount` can be a single order's obligation.
     - The validation check against USAspending must run on the **unfiltered** totals, which still match to the cent.
  4. **Duplicate sub-award reports: rule adopted (2026-10-16, Option A).**
     - **Strict duplicate group:** the same `agency_code`, `prime_award_unique_key`, `subaward_number`, exact `subaward_amount`, `subaward_action_date` and `subawardee_uei`, **and** the same normalized description (`upper(regexp_replace(coalesce(subaward_description,''), '[^A-Za-z0-9]', '', 'g'))`). Rows with a NULL number, UEI or date are never grouped.
     - **Kept copy:** the newest `subaward_sam_report_last_modified_date` (NULLs last), then the lowest `subaward_sam_report_id`. The amount and date are identical within a group, so the choice never changes totals.
     - **Excluded by default (`is_resubmitted_duplicate`):** the non-kept copies in strict groups whose copies span **two or more** SAM report months (`count(distinct report_year*100 + report_month) >= 2`). These are re-submissions: **7,790 records, $1,118,339,862.09**. These include extra copies within the same month inside multi-month groups: 2,068 rows, $234.9M. Of those, at most $3.1M (40 groups with 2 or more copies in every month) is consistent with real instalments (independent check). The evidence is that 41 of 41 sampled multi-month groups were re-submissions.
     - **Flagged, kept in totals (`is_possible_duplicate`):**
       - non-kept copies in strict groups confined to **one** report month: 2,511 records, $382,381,759.58;
       - near-duplicates that match on the first six fields but whose normalized descriptions differ: 516 records, $125,057,522.13. These are the non-kept copies under the six-field key that the strict key doesn't catch.
       - Together, 3,027 records, $507,439,281.71. With the excluded copies that makes 10,817 records, the earlier "possible duplicate" count.
     - **Toggle:** "Include duplicate sub-award reports (matches USAspending)" restores the excluded copies. It's independent of the implausible-amount toggle. With both toggles on, totals match USAspending to the cent, so validation always runs on the unfiltered totals.
     - **Required note** wherever sub-award totals are shown, next to the implausible-amount note: "Excludes N duplicate sub-award reports totaling $X that re-submit an earlier report; list available."
     - **Not duplicates, and not excluded:**
       - different amounts for the same sub-award (1,862 keys, up to about $1.15B possible overstatement if they are amendments; needs its own review);
       - different action dates (852 keys);
       - the same number under a different prime (1,311 keys).
     - **Default sub-award totals after both exclusions** (awarding, $M):

       | FY | Default total |
       |---|---|
       | 2017 | 2,263.4 |
       | 2018 | 3,133.5 |
       | 2019 | 2,807.9 |
       | 2020 | 3,225.0 |
       | 2021 | 2,981.0 |
       | 2022 | 2,972.7 |
       | 2023 | 2,818.4 |
       | 2024 | 2,890.9 |
       | 2025 | 2,279.6 |
       | 2026 | 1,955.7 |

       The as-reported (USAspending) totals are in caveat 3. Duplicate exclusion lowers each year by 0.01%–8.9% after the implausible exclusion.
  5. **Sub-award greater than its prime's amount:** 4,162 rows.
     - 3,653 of them have `prime_award_amount <= 0` (e.g. 1,425 of 1,435 in FY2026), where the comparison is meaningless.
     - **The other 509 rows, which have a positive prime, carry $20.73B.** Of that, $18.33B is the 17 implausible-amount rows (caveat 3) and $2.05B is the review tier.
     - On its own, "exceeds prime" is only a flag. Caveat 3 defines the exclusion.

### 8.2 Flows (prime → sub-recipient)

- **Edges:** `(prime_awardee_uei, subawardee_uei)` with `sum(subaward_amount)` and `count(*)`, from `subaward_flows`. Name display as in 7.3.
- **By state:** sub-recipient state = `subawardee_state_code` (NULL on 233 rows, $0.05B → "Unknown"). Prime state = `prime_awardee_state_code`. The state-to-state matrix is (prime state → sub state).
- **By program (OJP / OVW / COPS):** apply rule 6.2.1 to `prime_award_awarding_office_name` and `prime_award_awarding_sub_agency_name`. Use the assistance listing (`prime_award_cfda_numbers_and_titles`) for program-level drill-down.
- **Coverage note:** COPS has very few sub-awards ($26M lifetime). COPS hiring grants go directly to local agencies. A thin COPS flow is expected, not missing data.

---

## 9. Traceability links

| Metric | Link pattern | Notes |
|---|---|---|
| Account totals (File A): TBR, obligations, outlays | `https://www.usaspending.gov/agency` (agency list) and the profile header at `https://www.usaspending.gov/agency/{agency_slug}?fy={fy}`; API `/api/v2/references/toptier_agencies/` (current FY); GTAS via `/api/v2/reporting/agencies/overview/` (but not FY2025, see 4.6) | `agency_slug` from `toptier_agencies.json` (`department-of-justice`). Historical File A: Custom Account Data download, File A. |
| Sum of File B breakdowns | API `/api/v2/agency/{code}/budgetary_resources/` (budgetary-resources chart on the agency profile) | Our sum differs by +$2.20M (FY2025) and +$0.95M (FY2026) |
| File A vs B per-TAS gap | API `/api/v2/reporting/agencies/{code}/differences/?fiscal_year={fy}&fiscal_period={p}` (USAspending's own comparison) | |
| Federal account | `https://www.usaspending.gov/federal_account/{federal_account_symbol}` | e.g. `/federal_account/015-0200` |
| File A/B raw | Custom Account Data: `https://www.usaspending.gov/download_center/custom_account_data` | The pipeline's own zips are in `data/raw/{agency}/accounts/` |
| Award | `usaspending_permalink` column | |
| Award totals by type | API `/api/v2/search/spending_over_time/` (awarding filter); our snapshot is in `reference/spending_over_time_awarding_prime.json` | |
| Sub-awards | the prime's `usaspending_permalink`, Sub-Awards tab | |
| Object classes | OMB Circular A-11, Section 83 | |
| Field definitions | `https://www.usaspending.gov/data-dictionary`; DAIMS `https://fiscal.treasury.gov/data-transparency/DAIMS-current.html` | |
| API source code for the File A vs B point | usaspending-api `agency/v2/views/budgetary_resources.py` (File B for obligations and outlays); `references/v2/views/toptier_agencies.py` (File A) | |

Each "how this is calculated" note should contain the metric name from this
file, the formula in one line, the source file (A, B, D1/D2, F), the definition
(awarding or funding; File A or B), the period label from section 2.4, and the link.

---

## 10. Decisions and remaining open questions

Decided:
- File B breakdowns: treatment (a), sign-corrected for the verified flip register plus a signed residual row (2026-10-15).
- Groupings in 5.1 (object class) and 6.1 (component) accepted for v1 (2026-10-15).
- State: recipient location by default, place of performance as a toggle (2026-10-15).
- Intra-DOJ flows (Working Capital Fund, RECA payment to trust fund): not netted (2026-10-15).
- FY2024 015-X-1060: footnote only; no File A overrides (2026-10-16).
- Sub-awards: all 17 rule-flagged implausible-amount rows (8.1 caveat 3) excluded by default, with a visible note and a toggle to include them; the 28-row review tier flagged, not excluded (2026-10-16). Duplicates were later handled by Option A, below. This supersedes the CASA-only exclusion of 2026-10-15.
- Other calls made in this file (2026-10-16), answering the data contract's questions:
  - funding-definition components (6.2 rule 5);
  - "Department of Justice (sub-agency not specified)" bucket (6.2 rule 5);
  - null-office grants not a separate component (6.2 rule 1);
  - no outlay rate (3.4a);
  - `'__NO_UEI__'` recipient group (7.3).

- Sub-award duplicates: Option A adopted. Re-submitted copies are excluded with a toggle; same-month copies and near-duplicates are flagged (2026-10-16).
- FY2026 grant reporting gap: labelled on the dashboard (2.4); DOJ is not contacted (2026-10-16).

Still open:
- Whether to review sub-awards with amended amounts (8.1 caveat 4, "not duplicates").

---

## 11. Data issues register

The authoritative catalog behind the Data Issues page (page design approved 2026-10-16) and `mart_data_issues`.
Each issue type below has:
- a stable key;
- reader-facing wording;
- a detection rule (SQL parameterized by `$agency`, or "manual" with seed rows);
- the treatment;
- the sections and pages it affects;
- how the three amount columns are filled.

All counts and dollars are DOJ as of the 2026-10-15/16 build.

### 11.1 Conventions for every issue row

Column names follow `mart_data_issues` as built (`docs/data-contract.md` 6.3,
`sql/marts/70_data_issues.sql`). Requested changes to the mart are listed in 11.9.

**Amount columns.**
- `amount_as_reported` is the figure as the source published it.
- `amount_used` is the figure the dashboard uses by default.
- **`dollar_impact = amount_used − amount_as_reported`** (signed).
- For `footnoted` and `note` rows where we keep our own figure and another source differs, `amount_as_reported` holds the **other source's** figure (SF-133, USAspending), and the evidence names it.

**`measure`** uses the mart's values: `obligations`, `outlays`, `budgetary resources`
(new; needed for the SF-133 rows), `award obligations`, `sub-award amount`, or NULL.
Every dollar aggregate on the page (header, cards, chart, contract tables) groups by
`measure`. Obligations, outlays and sub-award amounts are never added together.

**`changes_default_number`** (the mart's column; **confirmed**) is true only for
treatments `corrected`, `excluded` and `reconciled`. The header and the impact-by-FY
chart use only these rows. Otherwise the GTAS note row (impact −$51.5B) would
dominate a figure that is not a change to any of our numbers.

**Severity**: relative to the size of the measure, so the thresholds work for any agency.
- `magnitude`:
  - `abs(dollar_impact)` for `corrected`, `excluded` and `reconciled` rows, and for `footnoted` rows with a non-zero impact (e.g. the FY2024 SF-133 footnote, $100.0M);
  - `abs(amount_as_reported)` for `footnoted` rows whose impact is 0 (e.g. `file_b_negative_group`: FY2026 "Other" at −$1.50B is 3.0% of obligations, so **high**), measured against the agency's FY total for that measure like every other row;
  - `abs(amount_as_reported)` for `flagged` rows.
- `base`: the agency's total for that `measure` and `fiscal_year`:
  - File A obligations, outlays or budgetary resources for those measures;
  - awarding-definition prime obligations for `award obligations`, **except for issue types scoped to one award category**. For those, the base is that category's total for the year. Example: `pop_equals_contractor_address` uses the year's net **contract** obligations (contracts incl. IDVs, awarding), because grants can't have the issue;
  - all reported sub-award amounts, before exclusions, for `sub-award amount`.
- `note` rows and rows with a NULL measure (`coverage_gap`) are always **low**. They don't change, flag or footnote any number we show.

| Severity | Rule |
|---|---|
| high | magnitude ≥ 1% of base |
| medium | magnitude ≥ 0.1% of base |
| low | otherwise |

Examples for DOJ:
- ATF FY2018 sign reversal: $2.71B / $43.65B = 6.2%, so **high**.
- FY2024 015-X-1060 SF-133 footnote: $100.0M / $51.91B = 0.19%, so **medium**.
- Town of Kent sub-award (excluded): $105.1M / $5.09B = 2.1%, so **high**. All 17 implausible sub-awards are high.
- A typical $50K duplicate: **low**.

This replaces the mart's provisional absolute thresholds (high ≥ $1B, medium ≥ $100M; **not adopted**). Absolute dollars don't scale to small agencies, and they make a $105M excluded sub-award "medium" in a year when it is 2% of all sub-awards. Seed rows may still override severity. The 11.4 values follow this rule.

**`issue_id`.** The mart's prefixes are **accepted**: `SIGNREV-…`, `SUBOUT-…`, `NOUEI-…`, and the seed ids `015-SF133-…`, `015-USAS-…`, `015-COVERAGE-…`. The only requirement is that an id stays the same for the same (agency, type, FY, entity, measure) across refreshes. Don't use row numbers.

**Component.**
- TAS rows: TAS → `federal_account_symbol` → the 6.1 map.
- Sub-award rows: the 6.2 rules on the prime's awarding sub-agency and office.
- Prime transaction rows: 6.2.
- Agency-level rows: NULL, displayed as "Agency-wide".

**`usaspending_url`.**
- TAS rows: `https://www.usaspending.gov/federal_account/{federal_account_symbol}`.
- Sub-award rows: the prime award page (`https://www.usaspending.gov/award/{prime_award_unique_key}/`, Sub-Awards tab).
- Prime rows: `usaspending_permalink`.
- Agency rows: `https://www.usaspending.gov/agency/{agency_slug}?fy={fy}`, or the API endpoint named in the seed.

**`verification_status`** uses the mart's values plus one more: `verified`, `rule-detected (count verified)`, `rule-detected (not yet verified)`. The initial status per type is in 11.5.

### 11.2 Rule-based issue types

The account issues are built from one TAS-level table. Run this once per agency:

```sql
-- ab_tas: one row per (fiscal_year, TAS, measure), File A vs File B (as reported).
-- One snapshot per FY is loaded. If more are loaded, filter both files to
-- max(submission_period_num) per (agency_code, fiscal_year) first (section 1).
CREATE TEMP TABLE ab_tas AS
WITH a AS (
  SELECT agency_code, fiscal_year, treasury_account_symbol AS tas, any_value(federal_account_symbol) AS fas,
         sum(obligations_incurred) AS ob, sum(gross_outlay_amount) AS ou
  FROM account_balances WHERE agency_code = $agency GROUP BY ALL),
b AS (
  SELECT agency_code, fiscal_year, treasury_account_symbol AS tas, any_value(federal_account_symbol) AS fas,
         sum(obligations_incurred) AS ob, sum(gross_outlay_amount_FYB_to_period_end) AS ou,
         sum(abs(obligations_incurred)) AS abs_ob, sum(abs(gross_outlay_amount_FYB_to_period_end)) AS abs_ou
  FROM account_activity WHERE agency_code = $agency GROUP BY ALL),
j AS (
  SELECT agency_code, fiscal_year, tas, coalesce(a.fas, b.fas) AS fas,
         coalesce(a.ob,0) a_ob, coalesce(b.ob,0) b_ob, coalesce(b.abs_ob,0) babs_ob,
         coalesce(a.ou,0) a_ou, coalesce(b.ou,0) b_ou, coalesce(b.abs_ou,0) babs_ou
  FROM a FULL JOIN b USING (agency_code, fiscal_year, tas))
SELECT agency_code, fiscal_year, tas, fas, 'obligations' AS measure, a_ob AS m_a, b_ob AS m_b, babs_ob AS b_abs FROM j
UNION ALL
SELECT agency_code, fiscal_year, tas, fas, 'outlays', a_ou, b_ou, babs_ou FROM j;

CREATE TEMP TABLE ab_class AS
SELECT *,
  (abs(m_a) >= 1e6 AND sign(m_a) <> sign(m_b) AND abs(m_a + m_b) <= greatest(1000, 0.001 * abs(m_a))) AS is_sign_reversal,
  (abs(m_a) >= 1e6 AND b_abs = 0) AS is_zero_placeholder
FROM ab_tas;

CREATE TEMP TABLE ab_resid AS     -- A minus sign-corrected B, for TAS that are not placeholders
SELECT *, m_a - CASE WHEN is_sign_reversal THEN -m_b ELSE m_b END AS d
FROM ab_class WHERE NOT is_zero_placeholder;
```

`is_sign_reversal` is the 5.3 candidate rule. In the mart, use the verified register
`file_b_sign_flips` (5.3), which for DOJ equals the rule's output exactly (12 rows).
For a new agency, rule hits that aren't in the register are `draft` issues and are
not corrected until verified.

---

#### `file_b_sign_reversal`

- **Label:** File B reported with reversed sign
- **Explanation (reader-facing):** "Agencies report their spending twice: once as account totals (File A), which match the Treasury's and OMB's books, and once broken down by program and object class (File B), which is what our breakdown charts use. For these accounts, the agency's File B reported the right amount with the wrong sign: obligations of $1.35 billion appear as −$1.35 billion. OMB's own budget-execution report (SF-133) confirms the positive figure. Our breakdown charts reverse the sign back, so payroll and contract totals for these years are not understated. You can switch to the as-reported figures."
- **Rule:** `SELECT … FROM ab_class WHERE is_sign_reversal`, restricted to rows in `file_b_sign_flips`. Entity = TAS; one row per measure.
- **Amounts:** reported = `m_b`; used = `−m_b`; **impact = `−2 × m_b`**.
- **Treatment:** `corrected`. `changes_default_number` = true.
- **Affects:** 5.1, 5.2, 5.3; pages "Where it goes" (object class, program activity) and the Overview A/B comparison.
- **Evidence template:** "File A {m_a}; File B {m_b} (same magnitude, opposite sign); OMB SF-133 {value} (positive)."
- **DOJ:**
  - Obligations: 10 rows, +$8,052,604,203.66 (ATF 015-0700: 5 TAS in FY2018, 3 in FY2019; Prison Industries 015-X-4500 in FY2025 and FY2026).
  - Outlays: 2 rows, +$2,283,469,454.78 (015-X-4500 in FY2025 and FY2026).
  - Total 12 rows.

#### `file_b_zero_placeholder`

- **Label:** Account reported as $0 in File B
- **Explanation:** "The agency's File B detail lists this account with $0, although its account totals (File A, confirmed by OMB) show real spending. Because we can't tell which object classes the money belongs to, the amount appears in the breakdown as a separate 'not in File B detail' row, so the breakdown still adds up to the account total."
- **Rule:** `is_zero_placeholder` (at least $1M in File A; every File B row for the TAS is $0.00). Entity = TAS; one row per measure.
- **Amounts:** reported = 0; used = `m_a`; impact = `m_a`.
- **Treatment:** `reconciled` (the amount is in the 5.3 residual row). `changes_default_number` = true.
- **Affects:** 5.3, 4.3, 4.4; "Where it goes"; Overview A/B comparison.
- **DOJ:** 12 rows, all FY2018.
  - Obligations: 5 rows, +$880,066,473.18 (OCDETF 2018/2018-0323 $537.8M and X-0323 $50.3M; U.S. Trustee X-5073 $233.1M; JIST X-0134 $51.5M; General Administration X-0129 $7.3M).
  - Outlays: 7 rows, +$775,419,205.93 (the same accounts plus OCDETF 2017/2017-0323 and TLEWC X-0132).
  - This is more than the spec table's two examples; the rule finds all of them.

#### `file_b_residual`

- **Label:** Other differences between File A and File B
- **Explanation:** "After the corrections above, small differences remain between the agency's account totals and its File B detail. Usually File B is lower; sometimes it is higher. We show the difference as a separate row in each breakdown, so the breakdown adds up to the account total. In FY2024 one account (BOP 015-X-1060) is $100 million higher in File B; there OMB's figures agree with File B (see the SF-133 entry)."
- **Rule:** one row per TAS with `abs(d) >= 1e6`. Plus one row per (fiscal_year, measure) with entity `ALL_OTHER_ACCOUNTS` for the sum of `d` over TAS with `abs(d) < 1e6`, created only when `abs(that sum) >= 1e6`.

  ```sql
  SELECT … , d AS dollar_impact FROM ab_resid WHERE abs(d) >= 1e6
  UNION ALL
  SELECT agency_code, fiscal_year, 'ALL_OTHER_ACCOUNTS', measure, sum(d)
  FROM ab_resid WHERE abs(d) < 1e6 GROUP BY agency_code, fiscal_year, measure HAVING abs(sum(d)) >= 1e6;
  ```

- **Amounts:**
  - TAS rows: reported = sign-corrected `m_b`; used = `m_a`; impact = `d` (signed).
  - `ALL_OTHER_ACCOUNTS` rows: reported and used are NULL; impact = the sum.
- **Treatment:** `reconciled`. `changes_default_number` = true.
- **Affects:** 5.3, 4.3, 4.4; "Where it goes"; Overview A/B comparison.
- **Identity (check):** for every (agency, FY, measure), the sum of `dollar_impact` over `file_b_sign_reversal`, `file_b_zero_placeholder` and `file_b_residual` equals `sum(m_a − m_b)` within $1M. The unissued remainder is the sum of TAS differences under $1M that didn't trigger a row; for DOJ it's at most $968,874.51 in any FY and measure.
- **DOJ:** 52 rows: 47 TAS rows and 5 `ALL_OTHER_ACCOUNTS` rows.
  - Obligations: 29 rows, net −$160,878,753.70.
  - Outlays: 23 rows, net +$2,664,997,778.86.
  - The largest are the Assets Forfeiture Fund 015-X-5042 outlays (+$1,377.1M in FY2018, +$1,070.7M in FY2019); BOP 015-2026/2026-1060 outlays (+$545.6M) and 015-2025/2029-1060 outlays (−$332.2M) in FY2026; and BOP 015-X-1060 in FY2024 (−$100.0M on each measure).

#### `file_b_negative_group`

- **Label:** Negative category in a breakdown
- **Explanation:** "In this year, one category in the agency's object-class breakdown is negative. That's because the agency recorded offsetting entries in different categories: for example, in FY2026 the RECA compensation accounts report +$6.5 billion under 'unknown object class' and −$3.8 billion under 'claims'. The account totals are right; only the split between categories is distorted. We show the bar below zero rather than hide it."
- **Rule:** an agency-level 5.1 group that is negative (−$1M or less) after sign correction, per (FY, measure). Entity = `agency|{oc_group_key}`.

  ```sql
  WITH cells AS (
    SELECT b.agency_code, b.fiscal_year, m.measure, b.treasury_account_symbol, b.object_class_code,
           <5.1 CASE expression> AS oc_group_key,
           CASE WHEN m.measure = 'obligations' THEN b.obligations_incurred
                ELSE b.gross_outlay_amount_FYB_to_period_end END
           * CASE WHEN f.is_sign_reversal THEN -1 ELSE 1 END AS v
    FROM account_activity b CROSS JOIN (VALUES ('obligations'), ('outlays')) m(measure)
    LEFT JOIN ab_class f ON f.agency_code = b.agency_code AND f.fiscal_year = b.fiscal_year
                        AND f.tas = b.treasury_account_symbol AND f.measure = m.measure
    WHERE b.agency_code = $agency)
  SELECT agency_code, fiscal_year, measure, oc_group_key, sum(v) AS amount
  FROM cells GROUP BY ALL HAVING sum(v) <= -1e6;
  ```

  The evidence lists the TAS × object-class cells of −$50M or less that drive the group.
- **Amounts:** reported = used = the group amount; impact = 0.
- **Treatment:** `footnoted`: the visible chart annotation in 5.4 is the footnote. `changes_default_number` = false. **This type is new; it isn't in the mart yet.**
- **Affects:** 5.1, 5.4; "Where it goes".
- **DOJ:** 3 rows:
  - FY2019 obligations, `unknown`: −$401,824,390.30 (Working Capital Fund 015-X-4526, 00.0, −$542.3M);
  - FY2026 obligations, `other`: −$1,504,184,939.69;
  - FY2026 outlays, `other`: −$1,549,270,816.97 (RECA 015-0333 and 015-8116, 42.0).
- Negative object-class cells in individual expired TAS are not issues; they're normal downward adjustments of prior-year obligations. Examples: BOP 015-2021/2021-1060 25.3 −$259.7M in FY2022, and FBI 015-2023/2023-0200 25.2 −$83.6M in FY2024. That is why the rule works at the agency group level, the level the chart shows.

#### `implausible_subaward`

- **Label:** Implausible sub-award amount (excluded)
- **Explanation:** "Prime recipients report their own sub-awards, and nobody checks the amounts against the federal award. These records are at least 10 times the size of the grant or contract they were paid from, and at least $100 million. The largest is a $10.5 billion record under a $32 million grant, whose amount repeats the digits of its own reference number. We exclude these records from sub-award totals by default. USAspending includes them; the toggle on the sub-award page shows the totals with them included."
- **Rule:** `prime_award_amount > 0 AND subaward_amount >= 10 * prime_award_amount AND subaward_amount >= 100000000`, on `subawards WHERE agency_code = $agency`. Entity = `subaward_sam_report_id`.
- **Amounts:** reported = `subaward_amount`; used = 0; impact = `−subaward_amount`.
- **Treatment:** `excluded` (2026-10-16). `changes_default_number` = true.
- **Affects:** 8.1 (caveat 3), 8.2; "Sub-award flows"; Overview sub-award totals.
- **Evidence:** a per-row evidence column (ratio to prime; sibling n, median and max; digit pattern; dates outside the prime's period of performance; reporter cluster). Sibling stats are computed per row.
- **DOJ:** 17 rows; reported $18,329,149,678.00; impact −$18,329,149,678.00. All are on DOJ-awarded primes.

#### `subaward_review`

- **Label:** Sub-award larger than its prime award (flagged)
- **Explanation:** "These sub-awards are larger than the federal award they came from, by less than the exclusion threshold. Some are probably errors too, but for contracts the 'prime award amount' can be a single order rather than the whole contract, so we flag them for review and keep them in the totals."
- **Rule:** `prime_award_amount > 0 AND subaward_amount > prime_award_amount AND subaward_amount >= 10000000 AND NOT <implausible rule>`.
- **Amounts:** reported = used = `subaward_amount`; impact = 0.
- **Treatment:** `flagged`.
- **Affects:** 8.1, 8.2.
- **DOJ:** 28 rows; $2,044,381,651.00 flagged.

#### `possible_duplicate_subaward`

- **Label:** see 11.10 ("Duplicate sub-award report").
- **Explanation:** "The same sub-award (same prime award, sub-award number, amount, date, recipient and description) was reported more than once. Where the copies came in later monthly reports, they are re-submissions: we count the sub-award once and exclude the extra copies from totals. USAspending counts every copy, and the toggle shows that figure. Copies within a single report, or with a different description, may be distinct, so we keep them and flag them."
- **Rule:** the strict key and kept-copy order in 8.1 caveat 4. Non-kept copies:
  - in multi-month groups → treatment **`excluded`**;
  - in same-month groups → treatment **`flagged`**;
  - non-kept under the six-field key but kept under the strict key (near-duplicates) → treatment **`flagged`**.
- **Extra column:** `duplicate_kind` ∈ {`resubmitted`, `same_month`, `near_duplicate`}.
- **Amounts:**
  - excluded: reported = `subaward_amount`; used = 0; impact = `−subaward_amount`; `changes_default_number` = true;
  - flagged: reported = used = `subaward_amount`; impact = 0.
- **Affects:** 8.1 (caveat 4), 8.2; "Sub-award flows"; Overview sub-award totals.
- **DOJ:** 10,817 rows:
  - 7,790 excluded (`resubmitted`), impact −$1,118,339,862.09;
  - 2,511 flagged (`same_month`), $382,381,759.58;
  - 516 flagged (`near_duplicate`), $125,057,522.13.

  No row is both excluded as a duplicate and excluded as implausible. If one ever is, the implausible exclusion takes precedence, and the duplicate row is set to `flagged` with impact 0, so nothing is excluded twice.
- **Size:** the mart is 0.2 MB, so keep rows at record level.
- **Header:** the page header reports the excluded duplicates as their own bullet and the flagged duplicates separately (11.7).

#### `recipient_not_identified`

- **Label:** Recipient not identified
- **Explanation:** "A few award transactions have no recipient ID (UEI). We keep them in all totals and group them as 'Recipient not identified' in recipient rankings, instead of dropping them."
- **Rule:** `prime_transactions WHERE agency_code = $agency AND recipient_uei IS NULL`. Entity = `transaction_key`.
- **Amounts:** reported = used = `federal_action_obligation`; impact = 0. `measure` = `award obligations`.
- **Treatment:** `flagged`.
- **Affects:** 7.3; "Awards explorer" (top recipients).
- **DOJ:** 6 rows, net $274,548.54. All are on the awarding pull, where DOJ is both awarding and funding.
- **Names:** `entity_name` shows the recipient name as USAspending publishes it, including private individuals on assistance rows (2026-10-16). The interim 'Individual recipient (name withheld)' substitution is withdrawn.

#### `pop_equals_contractor_address` (PROPOSED for v2; useful already in v1, which has the place-of-performance toggle)

- **Label:** Place of performance repeats the contractor's address
- **Explanation:** "For many contracts, the 'place of performance' is recorded as the contractor's own address, down to the ZIP+4. The work may really be done there, or the field may simply repeat the address. Maps and tables by place of performance can therefore put money in the contractor's home state rather than where the work happens. We keep the data as reported and add a caveat to place-of-performance views."
- **Rule:** contract transactions where both `recipient_zip_4_code` and `primary_place_of_performance_zip_4` are 9 digits after removing non-digits, and they are equal. Columns are from `contract_transactions`; the trend-signals SQL carries the same test as the flag `pop_is_contractor_address`.
- **Rows:**
  - **one per fiscal year** (agency level), with `amount_as_reported` = Σ `federal_action_obligation` of flagged transactions (net) and the share of absolute contract dollars in the evidence;
  - plus **one per (fiscal year, place-of-performance state)** where flagged dollars are ≥ $25M **and** ≥ 50% of that state's place-of-performance contract dollars. These are the cells a map would mislead on.
- **Amounts:** reported = used; impact = 0. `measure` = `award obligations`.
- **Treatment:** `footnoted`, because the caveat appears on every contract place-of-performance view (7.4). `changes_default_number` = false. The default state basis is recipient location, which isn't affected.
- **Severity (confirmed 2026-10-16):** by the 11.1 rule for footnoted zero-impact rows: `abs(amount_as_reported)` against the year's DOJ-wide net **contract** obligations (contracts incl. IDVs, awarding; e.g. FY2026 $10,492.7M). **Not** all award obligations, and **not** the state's own contract total. This applies to both agency-year and state-year rows. All DOJ agency-level rows are high (≥20%).
- **affects_views:** v1 `awards` (the place-of-performance state toggle in the Awards explorer, 7.4); v2 adds `places`. In `issue_types.csv`: `awards|places`; the v1 build ignores keys it doesn't render.
- **Header counting:** this type counts **once per agency-year** (10 for DOJ), not per row. The 113 state-year rows are listed under their agency-year row as detail (11.7).
- **Affects:** 7.4 (place-of-performance toggle), Places view, trend signals (`contractor_address` flag).
- **DOJ agency-level rows** (net $M flagged / net contract $M / share of absolute dollars):

  | FY | Flagged | All contracts | Share |
  |---|---|---|---|
  | 2017 | 1,827.2 | 8,077.3 | 22.5% |
  | 2018 | 1,790.0 | 8,201.3 | 22.3% |
  | 2019 | 1,856.0 | 8,581.9 | 21.4% |
  | 2020 | 1,770.7 | 8,938.0 | 20.3% |
  | 2021 | 2,578.1 | 9,740.9 | 27.5% |
  | 2022 | 4,032.6 | 9,200.0 | 44.1% |
  | 2023 | 4,452.7 | 10,341.2 | 42.8% |
  | 2024 | 4,341.1 | 9,506.6 | 45.4% |
  | 2025 | 4,128.1 | 8,861.6 | 47.2% |
  | 2026 | 5,921.5 | 10,492.7 | 56.2% |

  These figures cover contracts (including IDVs), awarding definition.
- **Verification:** the example ($29.9M BOP freezer/cooler award coded Anchorage) and the share trend come from exploratory analysis of the contract data. The rows were reproduced by an independent query on 2026-10-16.

### 11.3 Manual (hand-verified) issue types

These come from the seed `sql/seeds/data_issues_manual.csv`, keyed by `agency_code`. The columns match the mart. Rows are in 11.4.

#### `file_a_sf133_difference`

- **Label:** Account totals differ from OMB's SF-133
- **Explanation:** "We use the agency's account totals (File A), which normally match OMB's budget-execution report (SF-133) to the cent. For this account and year they don't: OMB and the agency's File B both show $100 million more. We keep the agency's account total and footnote it; the difference is 0.19% of DOJ's FY2024 obligations."
- **Treatment:** `footnoted` where material (2026-10-16: no overrides of File A); `note` where immaterial. `changes_default_number` = false.
- **Amounts:** reported = the SF-133 value (`comparison_source` = SF-133 line); used = File A; impact = used − reported.
- **Affects:** 3.1, 3.2, 3.3, 3.6, 4.3; Overview FY2024; "Where it goes" (BOP component, federal account 015-1060).

#### `published_figure_discrepancy`

- **Label:** USAspending shows a different figure
- **Explanation:** "USAspending.gov shows a different total from ours for this item. We explain which figure we use and why."
- **Treatment:** `note`. `changes_default_number` = false.
- **Amounts:** reported = the USAspending figure; used = ours; impact = used − reported.
- **Affects:** 4.2, 4.6; Overview tooltips.

#### `timing_difference`

- **Label:** Small difference from USAspending (timing)
- **Explanation:** "Our award totals were downloaded a few hours before USAspending's published totals, and recent records changed in between. The difference is tiny and will disappear at the next refresh."
- **Treatment:** `note`. Same amount conventions as `published_figure_discrepancy`. `measure` = `award obligations`.
- **Affects:** 7.1, 7.2; "Awards explorer".
- **Semi-automatic:** these rows may be generated by comparing each award type group per FY with `reference/spending_over_time_awarding_prime.json` (rows where `abs(diff) >= 0.01`). If so, the generated rows must equal the seed rows below for DOJ.

#### `coverage_gap`

- **Label:** Not independently checked / incomplete reference data
- **Explanation:** "We could not fully check these figures against an independent source, or a reference list we need is missing. This doesn't mean the numbers are wrong; it limits what we can confirm."
- **Treatment:** `note`. All amount columns are NULL. Severity is always **low**.
- **Affects:** 3.6 (SF-133 years) and 5.2 (program activity names).

### 11.4 Seed rows (DOJ, agency_code `015`)

All amounts are in dollars. Ids follow the mart's existing seed (`sql/seeds/data_issues_manual.csv`). Rows marked **new** are not in the seed yet.

| issue_id | issue_type | FY | entity | measure | amount_as_reported (other source) | amount_used | dollar_impact | treatment | severity | source / evidence | verified_in |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `015-SF133-2024-015-X-1060-000-obligations` | file_a_sf133_difference | 2024 | tas 015-X-1060-000 | obligations | 220,821,833.28 | 120,821,833.28 | −100,000,000.00 | footnoted | medium (seed currently says medium) | SF-133 line 2190, AMT4 (P12), `reference/sf133/2438300613.xlsx` (RPT_YR 2024). SF-133 = File B. | SF-133 reconciliation (2026-10-15), BOP 015-X-1060 check |
| `015-SF133-2024-015-X-1060-000-outlays` | file_a_sf133_difference | 2024 | tas 015-X-1060-000 | outlays | 246,828,290.37 | 146,828,290.37 | −100,000,000.00 | footnoted | medium | −(SF-133 line 3020), AMT4, same file. SF-133 = File B. | same |
| `015-SF133-2024-015-X-1060-000-budgetary_resources` **new** | file_a_sf133_difference | 2024 | tas 015-X-1060-000 | budgetary resources | 221,010,730.63 | 121,010,730.63 | −100,000,000.00 | footnoted | medium | SF-133 line 1910, AMT4 (P11 value 130,030,885.19). Exact values re-read from the file. | same |
| `015-SF133-2025-015-X-4500-000-budgetary_resources` **new** | file_a_sf133_difference | 2025 | tas 015-X-4500-000 | budgetary resources | 741,029,249.42 | 740,875,349.42 | −153,900.00 | note | low | SF-133 line 1910, AMT4, `reference/sf133/FY2025_SF133_MONTHLY_Department_of_Justice.xlsx`. Immaterial. | SF-133 reconciliation (2026-10-15) |
| `015-USAS-GTAS-2025` | published_figure_discrepancy | 2025 | agency 015 | obligations | 102,957,812,056.98 | 51,478,906,028.49 | −51,478,906,028.49 | note | low (seed: low ✓) | USAspending `gtas_obligation_total`, `/api/v2/reporting/agencies/overview/?fiscal_year=2025&fiscal_period=12&filter=justice`. Exactly 2× File A; OMB SF-133 line 2190 = 51,478,906,028.49. Likely a USAspending double count. | SF-133 reconciliation; File A vs B gap check (2026-10-15) |
| `015-USAS-FILEB-2025-obligations` **new** | published_figure_discrepancy | 2025 | agency 015 | obligations | 50,454,183,477.60 | 50,456,384,308.82 | +2,200,831.22 | note | low | USAspending `agency_total_obligated`, `/api/v2/agency/015/budgetary_resources/` (a File B sum) vs our File B sum (4.2). Cause not established. | metrics re-check (2026-10-15), USAspending File B endpoint |
| `015-USAS-FILEB-2025-outlays` **new** | published_figure_discrepancy | 2025 | agency 015 | outlays | 52,345,326,420.10 | 52,346,317,918.26 | +991,498.16 | note | low | same endpoint, `agency_total_outlayed` | same |
| `015-USAS-FILEB-2026-obligations` **new** | published_figure_discrepancy | 2026 | agency 015 | obligations | 49,364,805,795.61 | 49,365,759,098.66 | +953,303.05 | note | low | same endpoint (FY2026 through P11) | same |
| `015-USAS-FILEB-2026-outlays` **new** | published_figure_discrepancy | 2026 | agency 015 | outlays | 50,304,246,724.99 | 50,305,160,645.88 | +913,920.89 | note | low | same endpoint | same |
| `015-USAS-TIMING-2025-contracts` | timing_difference | 2025 | agency 015 (award type group contracts) | award obligations | 8,550,943,345.35 | 8,550,918,385.35 | −24,960.00 | note | low | `Contract_Obligations` in `reference/spending_over_time_awarding_prime.json` (fetched 2026-10-16 03:03 UTC) vs award zips pulled 2026-10-15 | metrics re-check (2026-10-15), USAspending totals by award type |
| `015-USAS-TIMING-2026-contracts` | timing_difference | 2026 | same | award obligations | 10,175,848,931.64 | 10,175,322,661.64 | −526,270.00 | note | low | same | same |
| `015-COVERAGE-SF133-2017` | coverage_gap | 2017 | agency 015 | NULL | NULL | NULL | NULL | note | low | SF-133 extract `1187284015.xlsx` (extracted 2017-09-20) has no P3/P6/P9/P12 columns and covers 82 of 197 TAS; FY2017 File A TBR, obligations and outlays can't be reconciled. Partial check passed: closing unobligated balances equal the FY2018 SF-133 brought-forward balance for 169 of 170 TAS. | SF-133 reconciliation (2026-10-15, 2026-10-16) |
| `015-COVERAGE-SF133-2019` | coverage_gap | 2019 | agency 015 | NULL | NULL | NULL | NULL | note | low | 189 of 197 TAS exact. Totals differ by +$11.36M TBR, +$26.82M obligations, +$3.13M outlays: small real differences (e.g. Working Capital Fund +$21.0M) plus one TAS blank at P12 | SF-133 reconciliation (2026-10-15, 2026-10-16) |
| `015-COVERAGE-SF133-2020` | coverage_gap | 2020 | agency 015 | NULL | NULL | NULL | NULL | note | low | Prison Industries 015-X-4500 blank at P12 in the extract (+$735.9M of the +$737.0M obligations difference) | SF-133 reconciliation (2026-10-15, 2026-10-16) |
| `015-COVERAGE-SF133-2021` | coverage_gap | 2021 | agency 015 | NULL | NULL | NULL | NULL | note | low | BOP 015-2021/2021-1060 blank at P12 in the extract (+$7.45B of the +$7.46B obligations difference); other differences under $65M | SF-133 reconciliation (2026-10-15, 2026-10-16) |
| `015-COVERAGE-SF133-2022` | coverage_gap | 2022 | agency 015 | NULL | NULL | NULL | NULL | note | low | BOP Buildings & Facilities 015-X-1003 and 015-2020/2020-1060 blank at P12 (+$1.32B TBR, +$69.3M obligations) | SF-133 reconciliation (2026-10-15, 2026-10-16) |
| `015-SF133-2022-015-2020/2020-1060-000-obligations` **new** | file_a_sf133_difference | 2022 | tas 015-2020/2020-1060-000 | obligations | 31,005,373.49 (File B; SF-133 P11 = 36,628,044.34, P12 blank) | 7,097,036.40 | −23,908,337.09 | note | low | File A year-end obligations are below both the SF-133 August figure and File B; SF-133 September data is blank in the available extract, so File A can't be confirmed. Likely understated by $24–30M (3.6). | SF-133 reconciliation (2026-10-16), FY2022 015-2020/2020-1060 check |
| `015-COVERAGE-PARK-2026` | coverage_gap | 2026 | agency 015 | NULL | NULL | NULL | NULL | note | low | All 6,278 FY2026 File B rows carry a Program Activity Reporting Key but no program activity code or name | metrics re-check (2026-10-15) |

Notes on the seed:
- The three FY2024 015-X-1060 rows are the footnote decided 2026-10-16 (no override). The same TAS also appears in the rule-based `file_b_residual` rows (−$100.0M on each measure). Both stay, and the residual row's evidence must say "OMB SF-133 agrees with File B here; see the SF-133 entry". Footnoted rows have `changes_default_number = false`, so nothing double counts.
- Coverage-gap rows clear once complete SF-133 extracts are downloaded and the reconciliation is re-run, or once the PARK names are loaded.

### 11.5 Initial verification status per type

| issue_type | verification_status | verified_in |
|---|---|---|
| file_b_sign_reversal | verified | File A vs B gap check, raw-file sign checks and SF-133 reconciliation (2026-10-15) |
| file_b_zero_placeholder | rule-detected (not yet verified). OCDETF, Trustee and JIST are verified individually (metrics re-check and SF-133 reconciliation); 0129, 0132 and OCDETF 2017/2017 outlays are not | — |
| file_b_residual | rule-detected (not yet verified). FY totals verified (metrics re-check); per-TAS rows new | — |
| file_b_negative_group | rule-detected (not yet verified). FY2026 verified (metrics re-check) | — |
| implausible_subaward | rule-detected (count verified) | metrics re-check (count). Row classification awaits re-verification. |
| subaward_review | rule-detected (count verified) | metrics re-check (count) |
| possible_duplicate_subaward | rule-detected (not yet verified). The 10,817 total is verified (metrics re-check); the excluded/flagged split by Option A is new | — |
| recipient_not_identified | verified | metrics re-check |
| file_a_sf133_difference, published_figure_discrepancy, timing_difference, coverage_gap | verified (except the **new** seed rows: FY2024 X-1060 TBR is verified via the SF-133 reconciliation; the four FILEB rows via the metrics re-check; FY2025 X-4500 TBR via the SF-133 reconciliation) | as in 11.4 |

### 11.6 DOJ totals (expected `mart_data_issues` content after the 11.9 changes)

Dollars are given **by measure**. Don't add across measures. (The current contract
table does, e.g. sign reversal "+$10,336.1M" is obligations plus outlays. Please
restate it by measure.)

| issue_type | rows | Σ dollar_impact by measure (flagged and footnoted rows: Σ amount_as_reported) |
|---|---|---|
| file_b_sign_reversal | 12 | obligations +8,052,604,203.66; outlays +2,283,469,454.78 |
| file_b_zero_placeholder | 12 | obligations +880,066,473.18; outlays +775,419,205.93 |
| file_b_residual | 52 (47 TAS + 5 `ALL_OTHER_ACCOUNTS`) | obligations −160,878,753.70; outlays +2,664,997,778.86 |
| file_b_negative_group | 3 | (footnoted; impact 0) amounts: obligations −1,906,009,329.99 (FY2019 −401,824,390.30; FY2026 −1,504,184,939.69); outlays −1,549,270,816.97 |
| implausible_subaward | 17 | sub-award amount −18,329,149,678.00 |
| subaward_review | 28 | (flagged) sub-award amount 2,044,381,651.00 |
| possible_duplicate_subaward | 10,817 (7,790 excluded + 3,027 flagged) | excluded: sub-award amount −1,118,339,862.09; flagged: sub-award amount 507,439,281.71 |
| recipient_not_identified | 6 | (flagged) award obligations 274,548.54 |
| manual (11.4) | 18 | file_a_sf133_difference 5; published_figure_discrepancy 5; timing_difference 2; coverage_gap 6 |
| pop_equals_contractor_address (v1.1) | 123 rows = 10 agency-year + 113 state-year (FY × state) | (footnoted; impact 0) flagged award obligations, as reported: FY2017 $1,827.2M … FY2026 $5,921.5M (11.2 table) |


Excluding duplicate-report rows: **158 issues for header counting** (140 rule-based, of which 10 are `pop_equals_contractor_address` agency-years; plus 18 manual). In rows: 271 (148 + 123). Duplicate-report rows are reported separately in the header (11.7).

Per (FY, measure), sign reversal + placeholder + residual impacts equal `sum(File A − File B)` to within $1M (the unissued sub-$1M remainder). Under the mart's agency-level residual this identity is exact, because residual = full residual − placeholders. Under the per-TAS version requested in 11.9, it holds to within the threshold. For DOJ the largest unissued remainder is $968,874.51 (FY2018 obligations).

### 11.7 Page header, summary cards and impact wording

**Rule:** the page never shows a dollar figure summed across issue types, across
measures (obligations, outlays, budgetary resources, award obligations, sub-award
amounts), or as a "sum of absolute impacts". Every dollar figure is one
(issue type × measure), or one treatment × measure where that treatment has only one
type with dollars in that measure. Each figure says what it changes.

The current wording, "58 of them change a default number, by $33.43B (sum of
absolute impacts)", is **withdrawn**. It adds $18.3B of excluded sub-award records to
$12.3B of File B sign corrections and $2.6B of reconciling rows, and invites the
reading "$33B of DOJ spending is wrong". In fact, none of these adjustments changes
DOJ's headline obligation or outlay totals.

#### Header (two sentences, then a short list)

> **{N} known data issues in {agency_name}'s data, FY{min}–FY{max}.** {headline_clause} We never change a number silently; every adjustment is listed below with the figure as reported.
>
> In our default view:
> - {C} File B entries reported with the wrong sign are corrected in spending breakdowns ({link: see breakdown impact}).
> - {R} account differences between File A and File B are shown as separate reconciling rows in breakdowns.
> - {E1} sub-award records with implausible amounts are excluded from sub-award totals ({$E1} as reported).
> - {E2} duplicate sub-award reports that re-submit an earlier report are excluded from sub-award totals ({$E2} as reported).
> - {F} other items are flagged or footnoted but not changed, plus {D} possible duplicate sub-award reports that are flagged but kept.

The variables:
- `{headline_clause}`:
  - If no row with `changes_default_number` has measure `obligations`, `outlays` or `budgetary resources` in an issue type that changes headline totals: "None of them changes the agency's headline budget, obligation or outlay totals, which come from its account balances (File A)."
  - In v1, no type changes headline account totals. Sign corrections and reconciling rows change only the composition of breakdowns, and exclusions apply only to sub-awards. So for every agency, the clause is the sentence above, as long as File A overrides stay prohibited (2026-10-16).
- N = all issues **excluding** `possible_duplicate_subaward` rows, with `pop_equals_contractor_address` counted **once per agency-year** (state-year rows are detail; decided 2026-10-16, see below).
- C = `corrected` rows; R = `reconciled` rows.
- E1 and `{$E1}` = count and Σ `amount_as_reported` of `implausible_subaward` rows.
- E2 and `{$E2}` = count and Σ `amount_as_reported` of `possible_duplicate_subaward` rows with treatment `excluded`.
- **The two excluded figures are separate bullets and are never added together**, even though they share a measure, because the page never sums across issue types.
- F = all other non-duplicate rows (`flagged`, `footnoted`, `note`).
- D = `possible_duplicate_subaward` rows with treatment `flagged`.
- Drop any bullet whose count is 0.

DOJ today:

> **158 known data issues in the Department of Justice's data, FY2017–FY2026.** None of them changes the agency's headline budget, obligation or outlay totals, which come from its account balances (File A). We never change a number silently; every adjustment is listed below with the figure as reported.
>
> In our default view:
> - 12 File B entries reported with the wrong sign are corrected in spending breakdowns.
> - 64 account differences between File A and File B are shown as separate reconciling rows in breakdowns.
> - 17 sub-award records with implausible amounts are excluded from sub-award totals ($18.3 billion as reported).
> - 7,790 duplicate sub-award reports that re-submit an earlier report are excluded from sub-award totals ($1.1 billion as reported).
> - 65 other items are flagged or footnoted but not changed, plus 3,027 possible duplicate sub-award reports that are flagged but kept.

(65 = 158 − 12 − 64 − 17. The duplicate-report rows, 7,790 + 3,027, are counted separately and are not in the 158.)

**Why `pop_equals_contractor_address` counts per agency-year (10), not per row (123).**
- The 113 state-year rows are the same coding practice seen state by state. They're one problem per year, broken down geographically, not 113 separate problems.
- Counting them would raise the header from 158 to 271. The page would then suggest a broad data-quality problem when it's one practice, and it would bury the other types (sign reversals, implausible sub-awards).
- Per agency-year still shows how much it matters: up to 56% of contract dollars, and the state detail is one click away.
- Every other type already counts at the level where each row is a separate problem: a TAS, a sub-award report, an award.

#### Summary cards (one per treatment)

Each card shows the treatment label (11.10), the count, the treatment's one-sentence
description, and **one line per (issue type, measure)** that has dollars, in the form
"{issue_type_label}, {measure}: {signed amount}". Cards never show a total line.
The card's last line is the `card_footer` from the `issue_treatments` seed (11.10).
It's agency-neutral, so it holds whatever number of types or lines a card has.

The italic footers in the DOJ examples below are illustrative. The rendered text is always the seed's `card_footer`.

| Card | DOJ lines |
|---|---|
| Corrected (12) | Sign reversed in File B, obligations: +$8.05B · Sign reversed in File B, outlays: +$2.28B · *Affects breakdowns only; totals unchanged.* |
| Reconciled (64) | Account reported as $0 in File B, obligations: +$0.88B · same, outlays: +$0.78B · Other File A–File B differences, obligations: −$0.16B · same, outlays: +$2.66B · *Shown as a separate row so breakdowns add up to the account total.* |
| Excluded (17 + 7,790 duplicate reports) | Implausible sub-award amount, sub-award amount: −$18.33B · Duplicate sub-award report (re-submissions), sub-award amount: −$1.12B · *Left out of totals by published rules. Each rule has its own toggle to include it; amounts are shown per rule and never added together.* |
| Flagged (34, plus 3,027 possible duplicate reports) | Sub-award larger than its prime award: $2.04B flagged · Duplicate sub-award report (same report month or differing description): $0.51B flagged · Recipient not identified, award obligations: $274,549 flagged · *Kept in totals.* |
| Footnoted (16, plus 113 state-year details) | Account totals differ from OMB's SF-133: FY2024, $100.0M on obligations, outlays and budgetary resources (3 rows) · Negative category in a breakdown: 3 rows · Place of performance repeats the contractor's address: 10 years, 20–56% of contract dollars (state detail: 113 rows) · *Number kept; footnote added where it appears.* |
| Note only (15) | USAspending shows a different figure: 5 rows · Small timing difference: 2 rows · Not independently checked: 6 rows · Account totals differ from OMB's SF-133: 2 rows (FY2025, $153,900 on budgetary resources; FY2022 BOP 015-2020/2020-1060, $23.9M on obligations) · *No number on the dashboard changes.* |

Dollar figures in the Footnoted and Note cards are the size of the difference
(`abs(dollar_impact)` or `abs(amount_as_reported)`), shown per row or per type, never
summed. The USAspending GTAS row is shown as text ("USAspending lists $102.96B, double
the actual $51.48B"), not as an impact.

#### Impact by fiscal year chart

- **Facets:** one panel per `measure`: obligations, outlays, sub-award amount. Panels have independent y-axes. There is no combined panel.
- **Bars:** within a panel, signed `dollar_impact` for rows with `changes_default_number`, stacked by `issue_type_label`, as a diverging stack (negative values below zero).
- **Default panel:** obligations. The sub-award panel is the one that shows FY2021.
- **Title:** "How our default figures differ from the as-reported data, by fiscal year".
- **Panel subtitle:** "{measure}: breakdown detail only; headline totals unchanged" for obligations and outlays; "{measure}: excluded records" for sub-awards.
- **Axis label:** "Change from as-reported ($)".
- Footnoted and note rows aren't plotted. A text line under the chart reads: "Footnoted and note-only items don't change any figure and aren't shown here."

### 11.8 Methods text ("How we treat data issues")

> **How we treat data issues**
>
> We build every number on this dashboard from the government's own published data: the agency's DATA Act filings and the award and sub-award records on USAspending.gov. Those filings sometimes contain mistakes or disagree with each other. Our rules:
>
> 1. **We never change a number silently.** Every adjustment is listed on this page. Each entry shows the figure as reported, the figure we use, the evidence, and how to see the original.
> 2. **Account totals come from the agency's account balances (File A).** These match the Treasury's and OMB's books (GTAS and the SF-133) to the cent in every year we could check. Where an independent OMB figure disagrees (FY2024, one BOP account), we keep the agency's figure and add a footnote rather than replace it.
> 3. **Breakdowns are made to add up to the account totals.** Where the agency's detailed filing (File B) reported an account with the wrong sign, and OMB's report confirms the correct sign, we reverse it back and label it "sign corrected." Where the detail is missing or doesn't match, the difference appears as a separate row, so you can see it rather than have it disappear.
> 4. **Implausible sub-award amounts are excluded by a published rule, not case by case.** A sub-award at least 10 times larger than its prime award and at least $100 million is excluded from totals by default. A toggle shows the totals with these records included, which matches USAspending. Smaller oversized sub-awards and possible duplicate reports are flagged but kept.
> 5. **We say what we couldn't check.** Where an independent source was incomplete, the entry says so.
> 6. **Detection is automatic where possible.** Most issues are found by fixed rules that run on every data refresh and work the same way for any agency. The rest were verified by hand and are recorded with their sources. Every entry was checked by a separate reviewer before publication; entries marked "draft" are awaiting that check.
>
> Sub-award amounts are self-reported by prime recipients and are a lower bound on money passed through. Obligations and outlays are different measures and are never added together, including on this page.

### 11.9 Reconciliation with `mart_data_issues` as built (2026-10-16)

Four questions about the mart as built:

1. **Residual net of placeholders: confirmed.** Placeholder rows plus residual rows equal the full treatment-(a) residual per FY and measure, so impacts never double count. **Change requested, granularity:** emit residual rows **per TAS** when `abs(d) >= $1M`, plus one `ALL_OTHER_ACCOUNTS` row per (FY, measure) when the sub-$1M remainder is at least $1M (11.2), instead of one agency-level row per (FY, measure) at $0.5M or more. Reasons:
   - the page's component filter and the federal-account links need a TAS;
   - the material drivers become visible entities: Assets Forfeiture Fund outlays +$1,377.1M (FY2018) and +$1,070.7M (FY2019); BOP 015-X-1060 −$100.0M (FY2024); BOP FY2026 outlays +$545.6M and −$332.2M.
   - The DOJ row count goes from 17 to 52.
2. **0129, 0132 and JIST 0134 placeholders: yes, they belong in the write-up of the File B gaps, which mentions them.** The rule's full DOJ list is in 11.2. It also includes OCDETF 015-2017/2017-0323 outlays ($47.2M).
3. **`changes_default_number`: confirmed**, and adopted in this section as the canonical name.
4. **Severity thresholds (high ≥ $1B, medium ≥ $100M): not adopted.** Use the relative rule in 11.1 (≥1% / ≥0.1% of the agency's FY total for the measure; note and coverage rows always low; seed may override).

Other changes requested:
- **Issue type keys: no renames.** Section 11 uses the mart's keys (`implausible_subaward`, `subaward_review`, `possible_duplicate_subaward`, and the rest as built).
- **Add the type `file_b_negative_group`** (11.2; 3 DOJ rows, treatment `footnoted`).
- **Add the measure value `budgetary resources`**, and the 6 **new** seed rows marked in 11.4 (one FY2024 X-1060 TBR row, one FY2025 X-4500 TBR row, four USAspending File B sum rows), plus one added 2026-10-16 (FY2022 015-2020/2020-1060 obligations; 3.6). DOJ manual rows go from 11 to 18.
- **Labels and explanations:** the mart has no label column. Add a small seed, `issue_types(issue_type, label, explanation, treatment_default, affects)`, holding the text in 11.2 and 11.3 verbatim, so the page reads its wording from one place.
- **Duplicate rule ordering:** keep the most recently modified copy unflagged. That means `ORDER BY subaward_sam_report_last_modified_date DESC NULLS LAST, subaward_sam_report_id`. The contract text doesn't state the direction; the count (10,817) is the same either way, but which copy gets flagged isn't.
- **`verification_status`:** add `rule-detected (not yet verified)` for rule rows not yet covered by an independent recount (11.5).
- **Privacy:** superseded; names shown as published (2026-10-16).
- **Contract 6.3 DOJ table:** restate the dollars by measure. "+$10,336.1M" and "−$200.0M" each add obligations to outlays.

### 11.10 Reader-facing labels (for the mart's `issue_type_label`, `treatment_label` and descriptions)

The mart carries these verbatim (`issue_type_label`, `issue_type_description`,
`treatment_label`, `treatment_description`), and the page uses them as-is. The
descriptions are agency-neutral. The longer explanations in 11.2 and 11.3 are for the
expanded-row view.

**Issue types**

| issue_type | issue_type_label | issue_type_description (one sentence) |
|---|---|---|
| file_b_sign_reversal | Sign reversed in File B | The agency's detailed spending report (File B) listed this account with the right amount but the wrong sign, which OMB's own figures confirm. |
| file_b_zero_placeholder | Account reported as $0 in File B | The agency's detailed spending report (File B) listed this account at $0, although its account balances (File A) show real spending. |
| file_b_residual | Other File A–File B difference | After corrections, the agency's detailed spending report (File B) still differs from its account balances (File A) by this amount for this account. |
| file_b_negative_group | Negative category in a breakdown | Offsetting entries filed under different object classes make this category negative, even though the account totals are correct. |
| implausible_subaward | Implausible sub-award amount | This self-reported sub-award is at least 10 times its prime award and at least $100 million, which is almost certainly a reporting error. |
| subaward_review | Sub-award larger than its prime award | This self-reported sub-award is larger than the federal award it was paid from, but below the threshold at which we exclude it. |
| possible_duplicate_subaward | Duplicate sub-award report | This report repeats another report's award, number, amount, date and recipient; copies re-submitted in later months are excluded from totals, and copies within one report or with a different description are flagged. |
| recipient_not_identified | Recipient not identified | This award transaction has no recipient ID, so it's grouped as "Recipient not identified" rather than under a named recipient. |
| pop_equals_contractor_address | Place of performance repeats the contractor's address | For these contract dollars, the recorded place of performance is the contractor's own address down to the ZIP+4, so place-of-performance views may show where contractors are based rather than where the work is done. |
| file_a_sf133_difference | Account totals differ from OMB's SF-133 | For this account, the agency's account balances (File A) don't match OMB's budget-execution report (SF-133), which normally agree to the cent. |
| published_figure_discrepancy | USAspending shows a different figure | USAspending.gov displays a different total for this item than the one we use, for the reason given. |
| timing_difference | Small timing difference | Our download and USAspending's published total were taken a few hours apart, and recent records changed in between. |
| coverage_gap | Not independently checked | An independent source we would use to check these figures is incomplete or missing, so they could not be fully confirmed. |

**Treatments**

| treatment | treatment_label | treatment_description (one sentence) | card_footer |
|---|---|---|---|
| corrected | Corrected | We reversed an obvious reporting error in breakdown charts; the as-reported figure is one toggle away, and headline totals are unaffected. | Changes breakdown detail only; headline totals are unchanged. |
| reconciled | Shown as a reconciling row | The difference appears as its own row in breakdowns, so the parts add up to the account total without being assigned to a category. | Shown as separate rows so breakdowns add up to the account totals. |
| excluded | Excluded by default | The record is left out of totals by a published rule; a toggle includes it and matches USAspending. | Left out of totals by published rules. Each rule has its own toggle to include it; amounts are shown per rule and never added together. |
| flagged | Flagged, kept in totals | The record is marked for readers but still counted in every total. | Marked for review and still counted in all totals. |
| footnoted | Footnoted | The figure is kept as reported, with a footnote wherever it appears. | The figure is kept; a footnote appears wherever it's shown. |
| note | Note only | Listed for transparency; no figure on the dashboard changes. | Listed for transparency; no figure on the dashboard changes. |
