-- 40_awards.sql
-- Marts: mart_awards (no recipient dimension, complete),
--        mart_award_recipients (top-N recipients per cell + "all other" rollup rows).
-- metrics.md 7.1 (awarding default, funding toggle), 7.2 (type groups),
-- 7.3 (recipients by UEI), 7.4 (state: recipient location default, PoP toggle),
-- 7.6 (gross / deobligations), 6.2 (award-side component), 2.3-2.5 (FY flags).
--
-- Both definitions are carried as rows (definition = 'awarding' | 'funding').
-- A transaction that is both awarded and funded by the agency appears once under
-- each definition: NEVER sum across definitions.

-- ------------------------------------------------------------ FY flags for award data
CREATE OR REPLACE TABLE _award_fy AS
WITH d AS (
    SELECT fiscal_year, min(action_date) AS first_action_date, max(action_date) AS last_action_date
    FROM prime_transactions
    WHERE agency_code = getvariable('agency')
      AND (awarding_agency_code = agency_code OR funding_agency_code = agency_code)
    GROUP BY 1
)
SELECT d.*,
       p.data_as_of_date BETWEEN make_date(d.fiscal_year - 1, 10, 1) AND make_date(d.fiscal_year, 9, 30)
           AS is_partial_year,
       (p.data_as_of_date BETWEEN make_date(d.fiscal_year - 1, 10, 1) AND make_date(d.fiscal_year, 9, 30))
       OR (p.data_as_of_date > make_date(d.fiscal_year, 9, 30)
           AND p.data_as_of_date - make_date(d.fiscal_year, 9, 30) < 90)
           AS is_provisional
FROM d CROSS JOIN _params p;

-- ------------------------------------------------------------ transactions under each definition
-- _office_fill (latest non-null awarding office per award_key) is built in 35_subaward_base.sql.

-- metrics.md 6.2 rule 5: rows awarded by the agency use the awarding-office rules under
-- BOTH definitions (basis 'awarding_office'); funding-only rows (awarded by another
-- agency) use the funding sub-agency (basis 'funding_sub_agency').
-- office_eff applies rule 1's null-office steps 1-2 (assistance): the award's latest
-- non-null office, then the listing_office_map seed.
CREATE OR REPLACE TABLE _award_tx AS
WITH t AS (
    SELECT t.*,
           coalesce(t.awarding_office_name, f.office_fill,
                    CASE WHEN t.award_category = 'assistance' THEN lo.office END) AS awarding_office_eff
    FROM prime_transactions t
    LEFT JOIN _office_fill f USING (award_key)
    LEFT JOIN _listing_office lo ON lo.program_code = t.program_code
    WHERE t.agency_code = getvariable('agency')
)
SELECT 'awarding' AS definition, t.*, 'awarding_office' AS basis,
       awarding_office_eff AS office_eff, awarding_sub_agency_name AS sub_agency_eff
FROM t WHERE awarding_agency_code = agency_code
UNION ALL BY NAME
SELECT 'funding' AS definition, t.*,
       CASE WHEN awarding_agency_code = agency_code THEN 'awarding_office' ELSE 'funding_sub_agency' END AS basis,
       CASE WHEN awarding_agency_code = agency_code THEN awarding_office_eff END AS office_eff,
       CASE WHEN awarding_agency_code = agency_code THEN awarding_sub_agency_name
            ELSE funding_sub_agency_name END AS sub_agency_eff
FROM t WHERE funding_agency_code = agency_code;

-- ------------------------------------------------------------ component lookup (metrics.md 6.2)
CREATE OR REPLACE TABLE _award_component_lookup AS
WITH combos AS (
    SELECT DISTINCT basis, award_category, office_eff, sub_agency_eff FROM _award_tx
    UNION
    SELECT DISTINCT basis, award_category, office_eff, sub_agency_eff FROM _sub_base
), office_match AS (
    SELECT c.basis, c.award_category, c.office_eff, c.sub_agency_eff,
           arg_min(r.component, r.rule_order)                 AS office_component,
           arg_min(r.program_office_from_office, r.rule_order) AS office_is_program
    FROM combos c
    JOIN _office_rules r
      ON c.basis = 'awarding_office' AND c.award_category = 'assistance'
     AND ((r.match_type = 'exact'  AND upper(c.office_eff) = r.match_value)
       OR (r.match_type = 'prefix' AND starts_with(upper(c.office_eff), r.match_value)))
    GROUP BY ALL
), sub AS (
    SELECT c.*,
           CASE WHEN c.sub_agency_eff IS NULL THEN (SELECT component FROM _null_sub_agency_rule)
                WHEN s.component IS NOT NULL THEN s.component
                WHEN (SELECT has_rules FROM _has_award_rules) THEN 'Unmapped: ' || c.sub_agency_eff
                ELSE c.sub_agency_eff END AS sub_component,
           s.null_office_program_office
    FROM combos c
    LEFT JOIN _sub_agency_rules s ON s.sub_agency_name_uc = upper(c.sub_agency_eff)
)
SELECT s.basis, s.award_category, s.office_eff, s.sub_agency_eff,
       coalesce(o.office_component, s.sub_component) AS component,
       CASE WHEN o.office_is_program THEN s.office_eff
            -- rule 1 null-office step 3: component from the sub-agency, office marked unknown
            WHEN o.office_component IS NULL AND s.basis = 'awarding_office' AND s.award_category = 'assistance'
                 AND s.office_eff IS NULL AND (SELECT count(*) FROM _office_rules) > 0
            THEN coalesce(s.null_office_program_office, 'Office not reported')
       END AS program_office
FROM sub s
LEFT JOIN office_match o
  ON o.basis = s.basis AND o.award_category = s.award_category
 AND o.office_eff IS NOT DISTINCT FROM s.office_eff AND o.sub_agency_eff IS NOT DISTINCT FROM s.sub_agency_eff;

-- ------------------------------------------------------------ per-transaction derived columns
CREATE OR REPLACE TABLE _award_tx2 AS
SELECT t.definition, t.fiscal_year, t.award_key, t.award_category, t.transaction_key, t.action_date,
       t.federal_action_obligation AS amt,
       l.component, l.program_office,
       CASE WHEN t.award_key LIKE 'CONT_IDV_%'                       THEN 'IDVs'
            WHEN t.award_category = 'contract'                       THEN 'Contracts'
            WHEN t.award_type_code IN ('02', '03', '04', '05')       THEN 'Grants'
            WHEN t.award_type_code IN ('06', '10')                   THEN 'Direct payments'
            WHEN t.award_type_code IN ('07', '08')                   THEN 'Loans'
            ELSE 'Other' END                                         AS award_type_group,
       CASE WHEN t.award_key LIKE 'CONT_IDV_%' THEN 'IDV' ELSE t.award_type_code END AS award_type_code,
       CASE WHEN rs.state_code IS NOT NULL THEN rs.state_code ELSE 'Foreign / unknown' END AS recipient_state,
       CASE WHEN ps.state_code IS NOT NULL THEN ps.state_code ELSE 'Foreign / unknown' END AS pop_state,
       t.recipient_uei, t.recipient_name, t.recipient_parent_uei, t.recipient_parent_name
FROM _award_tx t
JOIN _award_component_lookup l
  ON l.basis = t.basis AND l.award_category = t.award_category
 AND l.office_eff IS NOT DISTINCT FROM t.office_eff AND l.sub_agency_eff IS NOT DISTINCT FROM t.sub_agency_eff
LEFT JOIN _seed_state_codes rs ON rs.state_code = upper(t.recipient_state_code)
LEFT JOIN _seed_state_codes ps ON ps.state_fips = t.pop_state_fips;

-- One set of attributes per (definition, FY, award): those of the award's latest
-- action in that FY. Makes n_awards additive across cells within one FY + definition.
CREATE OR REPLACE TABLE _award_fy_attr AS
SELECT definition, fiscal_year, award_key,
       arg_max(component,        (action_date, transaction_key)) AS component,
       arg_max(program_office,   (action_date, transaction_key)) AS program_office,
       arg_max(award_category,   (action_date, transaction_key)) AS award_category,
       arg_max(award_type_group, (action_date, transaction_key)) AS award_type_group,
       arg_max(award_type_code,  (action_date, transaction_key)) AS award_type_code,
       arg_max(recipient_state,  (action_date, transaction_key)) AS recipient_state,
       arg_max(pop_state,        (action_date, transaction_key)) AS pop_state,
       -- metrics.md 7.3: group key; no-UEI transactions form the '__NO_UEI__' group
       arg_max(coalesce(recipient_uei, '__NO_UEI__'), (action_date, transaction_key)) AS recipient_uei,
       sum(amt)                                                  AS obligations,
       sum(amt) FILTER (WHERE amt > 0)                           AS gross_obligations,
       sum(amt) FILTER (WHERE amt < 0)                           AS deobligations,
       count(*)                                                  AS n_transactions
FROM _award_tx2
GROUP BY 1, 2, 3;

-- ------------------------------------------------------------ mart_awards
CREATE OR REPLACE TABLE mart_awards AS
SELECT
    getvariable('agency')                         AS agency_code,
    a.definition,
    a.fiscal_year,
    f.is_partial_year,
    f.is_provisional,
    a.award_category,
    a.award_type_group,
    a.award_type_code,
    CASE a.award_type_code
        WHEN 'A' THEN 'BPA call' WHEN 'B' THEN 'Purchase order'
        WHEN 'C' THEN 'Delivery order' WHEN 'D' THEN 'Definitive contract'
        WHEN 'IDV' THEN 'Indefinite delivery vehicle'
        WHEN '02' THEN 'Block grant' WHEN '03' THEN 'Formula grant'
        WHEN '04' THEN 'Project grant' WHEN '05' THEN 'Cooperative agreement'
        WHEN '06' THEN 'Direct payment for specified use' WHEN '07' THEN 'Direct loan'
        WHEN '08' THEN 'Guaranteed/insured loan' WHEN '09' THEN 'Insurance'
        WHEN '10' THEN 'Direct payment with unrestricted use' WHEN '11' THEN 'Other financial assistance'
        ELSE 'Not reported'
    END                                           AS award_type_label,
    a.component,
    a.program_office,
    a.recipient_state,
    a.pop_state,
    sum(a.obligations)                            AS obligations,
    coalesce(sum(a.gross_obligations), 0)         AS gross_obligations,
    coalesce(sum(a.deobligations), 0)             AS deobligations,
    CAST(sum(a.n_transactions) AS INTEGER)        AS n_transactions,
    CAST(count(*) AS INTEGER)                     AS n_awards,
    (SELECT data_as_of FROM _params)              AS data_as_of
FROM _award_fy_attr a
JOIN _award_fy f USING (fiscal_year)
GROUP BY ALL
ORDER BY a.definition, a.fiscal_year, a.component, a.award_type_group, a.recipient_state, a.pop_state;

-- ------------------------------------------------------------ mart_award_recipients
-- Recipient identity = UEI; display name = latest name for that UEI (metrics.md 7.3).
-- ATTRIBUTION: dollars go to the recipient
-- on EACH TRANSACTION, as on USAspending and in T3/T4. The cell keys component and
-- award_type_group stay award-level (the award's latest action in the FY, as in mart_awards),
-- so cell totals equal mart_awards. An award whose recipient changed within the FY (e.g. a
-- novation) is counted in n_awards once for EACH recipient that had a transaction on it, so
-- n_awards is additive across cells but NOT across recipients within a cell.
-- Kept (named): every recipient ranked <= 250 by ABSOLUTE net amount within its
-- (definition, FY, component, award type group) cell, plus every recipient ranked <= 2500
-- within (definition, FY) by absolute net amount or by net amount (largest first). Ranking by
-- absolute value keeps large net-negative recipients (terminations) named. Also named: the
-- top 2500 across all FYs (absolute and net). The naming set is global per (definition,
-- recipient), so a named recipient is named in every cell of every FY. Grain includes the
-- transaction's recipient_state, so state filters are exact too.
-- Transactions with no UEI are always kept as their own "Recipient not identified" row
-- (recipient_uei '__NO_UEI__', is_unidentified = true).
-- Everything else is rolled into one row per cell with is_rollup = true and
-- recipient_uei NULL, so the mart still sums to the full total. Row-level detail is tier 2.
CREATE OR REPLACE TABLE _recipient_names AS
SELECT recipient_uei,
       arg_max(recipient_name, (action_date, transaction_key))        AS recipient_name,
       arg_max(recipient_parent_uei, (action_date, transaction_key))  AS recipient_parent_uei,
       arg_max(recipient_parent_name, (action_date, transaction_key)) AS recipient_parent_name
FROM _award_tx2
WHERE recipient_uei IS NOT NULL
GROUP BY 1;

CREATE OR REPLACE TABLE mart_award_recipients AS
WITH tx AS (
    SELECT t.definition, t.fiscal_year, a.component, a.award_type_group, t.award_key, t.transaction_key,
           coalesce(t.recipient_uei, '__NO_UEI__') AS recipient_uei, t.recipient_state, t.amt
    FROM _award_tx2 t
    JOIN _award_fy_attr a USING (definition, fiscal_year, award_key)
), cell AS (
    SELECT definition, fiscal_year, component, award_type_group, recipient_uei, sum(amt) AS obligations
    FROM tx GROUP BY ALL
), ranked AS (
    SELECT *,
           row_number() OVER (PARTITION BY definition, fiscal_year, component, award_type_group
                              ORDER BY round(abs(obligations), 2) DESC, recipient_uei) AS cell_rank,
           dense_rank() OVER (PARTITION BY definition, fiscal_year ORDER BY round(abs(fy_total), 2) DESC, recipient_uei) AS fy_rank_abs,
           dense_rank() OVER (PARTITION BY definition, fiscal_year ORDER BY round(fy_total, 2) DESC, recipient_uei)      AS fy_rank_net
    FROM (SELECT *, sum(obligations) OVER (PARTITION BY definition, fiscal_year, recipient_uei) AS fy_total FROM cell)
), all_years AS (
    SELECT definition, recipient_uei,
           dense_rank() OVER (PARTITION BY definition ORDER BY round(abs(sum(obligations)), 2) DESC, recipient_uei) AS ay_rank_abs,
           dense_rank() OVER (PARTITION BY definition ORDER BY round(sum(obligations), 2) DESC, recipient_uei)      AS ay_rank_net
    FROM cell GROUP BY 1, 2
), keyed AS (
    -- The naming set is GLOBAL per (definition, recipient) across all FYs:
    -- a recipient named in any cell of any FY is named in every cell of every FY, so any sum
    -- of its named rows (any FY range, component, award type, state) is exact.
    SELECT r.definition, r.fiscal_year, r.component, r.award_type_group, r.recipient_uei,
           bool_or(r.recipient_uei = '__NO_UEI__' OR r.cell_rank <= 250 OR r.fy_rank_abs <= 2500 OR r.fy_rank_net <= 2500
                   OR y.ay_rank_abs <= 2500 OR y.ay_rank_net <= 2500)
               OVER (PARTITION BY r.definition, r.recipient_uei) AS keep,
           r.cell_rank
    FROM ranked r JOIN all_years y USING (definition, recipient_uei)
), k AS (
    SELECT tx.definition, tx.fiscal_year, tx.component, tx.award_type_group,
           CASE WHEN keyed.keep THEN tx.recipient_uei END            AS recipient_uei,
           NOT keyed.keep                                            AS is_rollup,
           tx.recipient_state,
           sum(tx.amt)                                               AS obligations,
           count(DISTINCT tx.award_key)                              AS n_awards,
           count(*)                                                  AS n_transactions,
           CASE WHEN keyed.keep THEN min(keyed.cell_rank) END        AS cell_rank
    FROM tx JOIN keyed USING (definition, fiscal_year, component, award_type_group, recipient_uei)
    GROUP BY tx.definition, tx.fiscal_year, tx.component, tx.award_type_group, tx.recipient_state,
             CASE WHEN keyed.keep THEN tx.recipient_uei END, NOT keyed.keep, keyed.keep
)
SELECT
    getvariable('agency')                         AS agency_code,
    k.definition,
    k.fiscal_year,
    f.is_partial_year,
    f.is_provisional,
    k.component,
    k.award_type_group,
    k.recipient_uei,
    CASE WHEN k.is_rollup THEN 'All other recipients'
         WHEN k.recipient_uei = '__NO_UEI__' THEN 'Recipient not identified'
         ELSE n.recipient_name END                AS recipient_name,
    coalesce(k.recipient_uei = '__NO_UEI__', false) AS is_unidentified,
    n.recipient_parent_uei,
    n.recipient_parent_name,
    k.recipient_state,
    k.obligations,
    CAST(k.n_awards AS INTEGER)                   AS n_awards,
    CAST(k.n_transactions AS INTEGER)             AS n_transactions,
    CAST(k.cell_rank AS INTEGER)                  AS cell_rank,
    k.is_rollup,
    (SELECT data_as_of FROM _params)              AS data_as_of
FROM k
JOIN _award_fy f USING (fiscal_year)
LEFT JOIN _recipient_names n ON n.recipient_uei = k.recipient_uei AND NOT k.is_rollup
ORDER BY k.definition, k.fiscal_year, k.component, k.award_type_group, k.is_rollup, k.cell_rank;

-- ------------------------------------------------------------ mart_award_component_lookup
-- The award-side component mapping, exported so the tier-2 API can filter row-level
-- data by the same component the marts show. Join on (basis, award_category, office_eff,
-- sub_agency_eff) computed as in _award_tx above.
CREATE OR REPLACE TABLE mart_award_component_lookup AS
SELECT getvariable('agency') AS agency_code, basis, award_category, office_eff, sub_agency_eff,
       component, program_office
FROM _award_component_lookup
ORDER BY basis, award_category, component;
