-- 35_subaward_base.sql
-- Helper: one row per sub-award report per definition, with flags.
-- metrics.md 8.1. Built before 40_awards.sql because the award-side component
-- lookup covers both prime transactions and sub-awards.

-- Duplicates (metrics.md 8.1 caveat 4, Option A). Six-field key (prime key, sub-award number,
-- amount, action date, sub-recipient UEI): every copy except the most recently modified (then
-- lowest report ID) is a candidate (10,817 DOJ rows). Of those, re-submitted copies (strict key
-- incl. description, 2+ report months) are is_resubmitted_duplicate (excluded by default); the
-- rest (same-month copies, near-duplicates) are is_possible_duplicate (flagged, counted).
CREATE OR REPLACE TABLE _sub_flags AS
WITH base AS (
    SELECT subaward_sam_report_id,
           row_number() OVER (
               PARTITION BY prime_award_unique_key, subaward_number, subaward_amount,
                            subaward_action_date, subawardee_uei
               ORDER BY subaward_sam_report_last_modified_date DESC NULLS LAST, subaward_sam_report_id) > 1 AS is_possible_duplicate
    FROM subawards
    WHERE agency_code = getvariable('agency')
),
-- Re-submitted duplicate (Option A, metrics.md 8.1):
-- strict key = the five fields above plus the normalised description; the group's
-- copies span >= 2 SAM report months; every copy except the most recently modified (then lowest
-- report ID) is a re-submitted duplicate. EXCLUDED from default totals. Same-report-month copies
-- and near-duplicates keep only is_possible_duplicate (flag, counted).
d AS (
    SELECT subaward_sam_report_id, prime_award_unique_key, subaward_number, subaward_amount,
           subaward_action_date, subawardee_uei, subaward_sam_report_last_modified_date,
           subaward_sam_report_year * 100 + subaward_sam_report_month AS report_month,
           upper(regexp_replace(coalesce(subaward_description, ''), '[^A-Za-z0-9]', '', 'g')) AS desc_norm
    FROM subawards
    WHERE agency_code = getvariable('agency')
      AND subaward_number IS NOT NULL AND subawardee_uei IS NOT NULL AND subaward_action_date IS NOT NULL
),
r AS (
    SELECT subaward_sam_report_id,
           count(DISTINCT report_month) OVER w AS grp_report_months,
           row_number() OVER (w ORDER BY subaward_sam_report_last_modified_date DESC NULLS LAST, subaward_sam_report_id) AS dup_rank
    FROM d
    WINDOW w AS (PARTITION BY prime_award_unique_key, subaward_number, subaward_amount,
                              subaward_action_date, subawardee_uei, desc_norm)
)
SELECT b.subaward_sam_report_id,
       -- flagged, kept in totals (metrics 8.1 caveat 4): same-month copies and near-duplicates only
       b.is_possible_duplicate AND NOT coalesce(r.dup_rank > 1 AND r.grp_report_months >= 2, false) AS is_possible_duplicate,
       coalesce(r.dup_rank > 1 AND r.grp_report_months >= 2, false) AS is_resubmitted_duplicate,
       CASE WHEN r.dup_rank > 1 AND r.grp_report_months >= 2 THEN 'resubmitted'
            WHEN r.dup_rank > 1 AND r.grp_report_months = 1 THEN 'same_month'
            WHEN b.is_possible_duplicate THEN 'near_duplicate' END AS duplicate_kind
FROM base b LEFT JOIN r USING (subaward_sam_report_id);

CREATE OR REPLACE TABLE _office_fill AS
SELECT award_key,
       arg_max(awarding_office_name, action_date) FILTER (WHERE awarding_office_name IS NOT NULL) AS office_fill
FROM prime_transactions
WHERE agency_code = getvariable('agency')
GROUP BY 1;

CREATE OR REPLACE TABLE _sub_base AS
WITH s AS (
    SELECT s.*,
           coalesce(f.is_possible_duplicate, false)        AS is_possible_duplicate,
           coalesce(f.is_resubmitted_duplicate, false)     AS is_resubmitted_duplicate,
           f.duplicate_kind,
           -- is_outlier: rule from sql/seeds/subaward_outlier_rule.csv. DEFAULT exclusion (since 2026-10-16).
           coalesce(s.prime_award_amount > r.min_prime_award_amount_exclusive
                    AND s.subaward_amount >= r.min_ratio_to_prime * s.prime_award_amount
                    AND s.subaward_amount >= r.min_subaward_amount, false) AS is_outlier,
           -- subaward_review_flag: review tier below the rule (same seed). Flag only, never excluded.
           coalesce(s.prime_award_amount > r.min_prime_award_amount_exclusive
                    AND s.subaward_amount > r.review_min_ratio_to_prime_exclusive * s.prime_award_amount
                    AND s.subaward_amount >= r.review_min_subaward_amount
                    AND NOT (s.subaward_amount >= r.min_ratio_to_prime * s.prime_award_amount
                             AND s.subaward_amount >= r.min_subaward_amount), false) AS subaward_review_flag,
           -- is_outlier_registered: individually verified records (sql/seeds/subaward_outliers.csv).
           o.subaward_sam_report_id IS NOT NULL            AS is_outlier_registered,
           coalesce(s.subaward_amount > s.prime_award_amount, false) AS exceeds_prime_amount,
           -- metrics.md 6.2 rule 1 null-office steps 1-2 (assistance): award's latest office, then listing map
           coalesce(s.prime_award_awarding_office_name, of.office_fill,
                    CASE WHEN s.award_category = 'assistance' THEN lo.office END) AS awarding_office_eff
    FROM subawards s
    LEFT JOIN _sub_flags f USING (subaward_sam_report_id)
    LEFT JOIN _seed_subaward_outliers o
           ON o.agency_code = s.agency_code AND o.subaward_sam_report_id = s.subaward_sam_report_id
    LEFT JOIN _office_fill of ON of.award_key = s.prime_award_unique_key
    LEFT JOIN _listing_office lo
           ON lo.program_code = trim(split_part(s.prime_award_cfda_numbers_and_titles, ':', 1))
    CROSS JOIN (SELECT * FROM _seed_subaward_outlier_rule LIMIT 1) r
    WHERE s.agency_code = getvariable('agency')
)
-- basis (metrics.md 6.2 rule 5): rows awarded by the agency use the awarding office
-- rules under BOTH definitions; funding-only rows use the funding sub-agency.
SELECT 'awarding' AS definition, s.*, 'awarding_office' AS basis,
       awarding_office_eff                   AS office_eff,
       prime_award_awarding_sub_agency_name  AS sub_agency_eff
FROM s WHERE prime_award_awarding_agency_code = agency_code
UNION ALL BY NAME
SELECT 'funding' AS definition, s.*,
       CASE WHEN prime_award_awarding_agency_code = agency_code THEN 'awarding_office' ELSE 'funding_sub_agency' END AS basis,
       CASE WHEN prime_award_awarding_agency_code = agency_code THEN awarding_office_eff END AS office_eff,
       CASE WHEN prime_award_awarding_agency_code = agency_code THEN prime_award_awarding_sub_agency_name
            ELSE prime_award_funding_sub_agency_name END AS sub_agency_eff
FROM s WHERE prime_award_funding_agency_code = agency_code;
