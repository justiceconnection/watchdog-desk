-- 50_subawards.sql
-- Marts: mart_subaward_summary (complete, no recipient identities),
--        mart_subaward_flows   (prime -> sub-recipient edges, top-N + rollup).
-- metrics.md 8.1 (amount, awarding default / funding toggle, flags), 8.2 (flows),
-- 6.2 rule 1 (program = OJP / OVW / COPS from the prime's awarding office).
-- Sub-award amounts are self-reported and a floor. Never add them to prime obligations.
-- is_outlier and is_possible_duplicate are DIMENSIONS: filter on them, don't drop them.
-- Dashboard default (since 2026-10-16): exclude is_outlier rows (rule, 17 DOJ rows) and
-- is_resubmitted_duplicate rows (Option A, 7,790 DOJ rows) from totals, with toggles to include
-- them (= USAspending). Other possible duplicates (same-month, near) are flagged and counted.

CREATE OR REPLACE TABLE _sub_fy AS
SELECT s.fiscal_year,
       min(s.subaward_action_date) AS first_action_date,
       max(s.subaward_action_date) AS last_action_date,
       p.data_as_of_date BETWEEN make_date(s.fiscal_year - 1, 10, 1) AND make_date(s.fiscal_year, 9, 30)
           AS is_partial_year,
       (p.data_as_of_date BETWEEN make_date(s.fiscal_year - 1, 10, 1) AND make_date(s.fiscal_year, 9, 30))
       OR (p.data_as_of_date > make_date(s.fiscal_year, 9, 30)
           AND p.data_as_of_date - make_date(s.fiscal_year, 9, 30) < 90)
           AS is_provisional
FROM _sub_base s CROSS JOIN _params p
GROUP BY s.fiscal_year, p.data_as_of_date;

CREATE OR REPLACE TABLE _sub2 AS
SELECT s.definition, s.fiscal_year, s.award_category, s.subaward_sam_report_id,
       s.subaward_action_date, s.subaward_amount,
       l.component, l.program_office,
       s.prime_award_unique_key, s.prime_awardee_uei, s.prime_awardee_name,
       s.subawardee_uei, s.subawardee_name,
       coalesce(ps.state_code, 'Foreign / unknown')  AS prime_state,
       coalesce(ss.state_code, 'Foreign / unknown')  AS sub_state,
       coalesce(sp.state_code, 'Foreign / unknown')  AS sub_pop_state,
       s.is_outlier, s.is_outlier_registered, s.subaward_review_flag, s.is_possible_duplicate, s.is_resubmitted_duplicate, s.exceeds_prime_amount
FROM _sub_base s
JOIN _award_component_lookup l
  ON l.basis = s.basis AND l.award_category = s.award_category
 AND l.office_eff IS NOT DISTINCT FROM s.office_eff AND l.sub_agency_eff IS NOT DISTINCT FROM s.sub_agency_eff
LEFT JOIN _seed_state_codes ps ON ps.state_code = upper(s.prime_awardee_state_code)
LEFT JOIN _seed_state_codes ss ON ss.state_code = upper(s.subawardee_state_code)
LEFT JOIN _seed_state_codes sp ON sp.state_code = upper(s.subaward_primary_place_of_performance_state_code);

-- ------------------------------------------------------------ mart_subaward_summary
CREATE OR REPLACE TABLE mart_subaward_summary AS
SELECT
    getvariable('agency')                    AS agency_code,
    s.definition,
    s.fiscal_year,
    f.is_partial_year,
    f.is_provisional,
    s.award_category,
    s.component,
    s.program_office,
    s.prime_state,
    s.sub_state,
    s.sub_pop_state,
    s.is_outlier,
    s.is_outlier_registered,
    s.subaward_review_flag,
    s.is_possible_duplicate,
    s.is_resubmitted_duplicate,
    s.exceeds_prime_amount,
    sum(s.subaward_amount)                   AS subaward_amount,
    CAST(count(*) AS INTEGER)                AS n_subawards,
    CAST(count(DISTINCT s.prime_award_unique_key) AS INTEGER) AS n_prime_awards,
    (SELECT data_as_of FROM _params)         AS data_as_of
FROM _sub2 s
JOIN _sub_fy f USING (fiscal_year)
GROUP BY ALL
ORDER BY s.definition, s.fiscal_year, s.component, s.prime_state, s.sub_state;

-- ------------------------------------------------------------ mart_subaward_flows
-- Edge = (prime UEI -> sub-recipient UEI) within (definition, FY, component,
-- program office, prime state, sub state, flags). Names = latest name per UEI.
-- Kept: edges ranked <= 300 within (definition, FY, component) by amount, plus all
-- edges touching the top 300 primes of (definition, FY). The rest roll up into one
-- row per (definition, FY, component, program office, prime state, sub state, flags)
-- with is_rollup = true, so totals still reconcile.
CREATE OR REPLACE TABLE _sub_names AS
SELECT 'prime' AS role, prime_awardee_uei AS uei, arg_max(prime_awardee_name, subaward_action_date) AS name
FROM _sub2 WHERE prime_awardee_uei IS NOT NULL GROUP BY 1, 2
UNION ALL
SELECT 'sub', subawardee_uei, arg_max(subawardee_name, subaward_action_date)
FROM _sub2 WHERE subawardee_uei IS NOT NULL GROUP BY 1, 2;

CREATE OR REPLACE TABLE mart_subaward_flows AS
WITH e AS (
    SELECT definition, fiscal_year, component, program_office, prime_awardee_uei, subawardee_uei,
           prime_state, sub_state, is_outlier, is_outlier_registered, subaward_review_flag, is_possible_duplicate, is_resubmitted_duplicate,
           sum(subaward_amount) AS subaward_amount, count(*) AS n_subawards
    FROM _sub2
    GROUP BY ALL
), r AS (
    SELECT *,
           row_number() OVER (PARTITION BY definition, fiscal_year, component
                              ORDER BY subaward_amount DESC, prime_awardee_uei, subawardee_uei) AS edge_rank,
           dense_rank() OVER (PARTITION BY definition, fiscal_year
                              ORDER BY prime_total DESC, prime_awardee_uei)                       AS prime_rank
    FROM (SELECT *, sum(subaward_amount) OVER (PARTITION BY definition, fiscal_year, prime_awardee_uei) AS prime_total FROM e)
), keep AS (
    SELECT *, (prime_awardee_uei IS NOT NULL AND subawardee_uei IS NOT NULL
               AND (edge_rank <= 300 OR prime_rank <= 300)) OR is_outlier OR is_outlier_registered OR subaward_review_flag AS kept
    FROM r
), u AS (
    SELECT definition, fiscal_year, component, program_office, prime_awardee_uei, subawardee_uei,
           prime_state, sub_state, is_outlier, is_outlier_registered, subaward_review_flag, is_possible_duplicate, is_resubmitted_duplicate, subaward_amount, n_subawards,
           false AS is_rollup
    FROM keep WHERE kept
    UNION ALL
    SELECT definition, fiscal_year, component, program_office, NULL, NULL,
           prime_state, sub_state, is_outlier, is_outlier_registered, subaward_review_flag, is_possible_duplicate, is_resubmitted_duplicate,
           sum(subaward_amount), sum(n_subawards), true
    FROM keep WHERE NOT kept
    GROUP BY definition, fiscal_year, component, program_office, prime_state, sub_state, is_outlier, is_outlier_registered, subaward_review_flag, is_possible_duplicate, is_resubmitted_duplicate
)
SELECT
    getvariable('agency')                    AS agency_code,
    u.definition,
    u.fiscal_year,
    f.is_partial_year,
    f.is_provisional,
    u.component,
    u.program_office,
    u.prime_awardee_uei                      AS prime_uei,
    CASE WHEN u.is_rollup THEN 'All other prime recipients' ELSE pn.name END AS prime_name,
    u.prime_state,
    u.subawardee_uei                         AS sub_uei,
    CASE WHEN u.is_rollup THEN 'All other sub-recipients' ELSE sn.name END   AS sub_name,
    u.sub_state,
    u.is_outlier,
    u.is_outlier_registered,
    u.subaward_review_flag,
    u.is_possible_duplicate,
    u.is_resubmitted_duplicate,
    u.subaward_amount,
    CAST(u.n_subawards AS INTEGER)           AS n_subawards,
    u.is_rollup,
    (SELECT data_as_of FROM _params)         AS data_as_of
FROM u
JOIN _sub_fy f USING (fiscal_year)
LEFT JOIN _sub_names pn ON pn.role = 'prime' AND pn.uei = u.prime_awardee_uei
LEFT JOIN _sub_names sn ON sn.role = 'sub'   AND sn.uei = u.subawardee_uei
ORDER BY u.definition, u.fiscal_year, u.component, u.is_rollup, u.subaward_amount DESC;

-- ------------------------------------------------------------ mart_subaward_outliers
-- Every sub-award flagged by the outlier rule OR in the verified register, for the
-- visible note and links. Default totals exclude is_outlier.
CREATE OR REPLACE TABLE mart_subaward_outliers AS
SELECT getvariable('agency') AS agency_code, s.definition, s.fiscal_year, s.subaward_sam_report_id,
       s.subaward_number, s.subaward_amount, s.subaward_action_date, s.prime_award_unique_key,
       s.prime_award_fain, s.prime_award_amount, s.prime_awardee_name, s.subawardee_name,
       s.prime_award_awarding_office_name,
       s.subaward_amount / NULLIF(s.prime_award_amount, 0) AS ratio_to_prime,
       s.is_outlier, s.is_outlier_registered, s.subaward_review_flag,
       (SELECT rule_id FROM _seed_subaward_outlier_rule LIMIT 1) AS outlier_rule_id,
       o.reason, o.source, s.usaspending_permalink
FROM _sub_base s
LEFT JOIN _seed_subaward_outliers o
  ON o.agency_code = s.agency_code AND o.subaward_sam_report_id = s.subaward_sam_report_id
WHERE s.is_outlier OR s.is_outlier_registered OR s.subaward_review_flag
ORDER BY s.definition, s.fiscal_year;
