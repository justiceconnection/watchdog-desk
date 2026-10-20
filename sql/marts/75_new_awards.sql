-- 75_new_awards.sql: award-level inputs shared by the Watchdog Desk cards (sql/desk/*.py).
--   _v2_tx_all     one row per prime transaction x definition, with award attributes
--   _v2_award_new  metrics 7.7: one row per award x definition with its new-award date, amount and award cycle
--   _v2_tx         awarding-definition transactions (contractor-address flag, recipient type, place of performance)
-- In-memory tables only; nothing here is exported. The "_v2_" prefix is historical (the tables were first
-- built for the trend-signal prototype) and is kept so the card code does not change.
-- Rules live in seeds (award_cycle_patterns, trend_signal_params) so they can change without SQL edits.

-- ------------------------------------------------------------ per-transaction extras
CREATE OR REPLACE TABLE _v2_extra AS
SELECT assistance_transaction_unique_key AS transaction_key,
       business_types_code AS recipient_type,
       period_of_performance_start_date AS pop_start_date,
       NULL::BOOLEAN AS pop_is_contractor_address
FROM assistance_transactions WHERE agency_code = getvariable('agency')
UNION ALL
-- metrics 7.4 / 11.2: place of performance ZIP+4 = contractor ZIP+4 (both 9 digits)
SELECT contract_transaction_unique_key, NULL, NULL,
       length(regexp_replace(coalesce(recipient_zip_4_code, ''), '[^0-9]', '', 'g')) = 9
       AND regexp_replace(coalesce(recipient_zip_4_code, ''), '[^0-9]', '', 'g')
         = regexp_replace(coalesce(primary_place_of_performance_zip_4, ''), '[^0-9]', '', 'g')
FROM contract_transactions WHERE agency_code = getvariable('agency');

CREATE OR REPLACE TABLE _v2_tx_all AS
SELECT t.*, p.award_id, p.action_type, p.modification_number, p.program_code AS listing, p.program_title,
       p.recipient_state_code AS recipient_state_raw,
       x.recipient_type, x.pop_start_date, x.pop_is_contractor_address
FROM _award_tx2 t
JOIN prime_transactions p ON p.transaction_key = t.transaction_key AND p.agency_code = getvariable('agency')
LEFT JOIN _v2_extra x ON x.transaction_key = t.transaction_key;

-- ------------------------------------------------------------ award cycle (seed patterns)
CREATE OR REPLACE TABLE _v2_cycle_patterns AS
SELECT CAST(priority AS INTEGER) AS priority, regex, year_format
FROM read_csv('sql/seeds/award_cycle_patterns.csv', header = true, all_varchar = true)
WHERE agency_code = getvariable('agency');

-- ------------------------------------------------------------ new-award date (metrics 7.7)
CREATE OR REPLACE TABLE _v2_new_dt AS
WITH g AS (   -- assistance: first 'New Award'; fallback base record with FAIN-year or PoP-start test
    SELECT definition, award_key,
           min(action_date) FILTER (WHERE action_type = 'New Award') AS a1_dt,
           min(action_date) FILTER (WHERE modification_number IN ('0', '00')
                AND (TRY_CAST(left(award_id, 4) AS INTEGER) BETWEEN year(action_date) - 1 AND year(action_date) + 1
                     OR pop_start_date >= action_date - INTERVAL 365 DAY)) AS fb_dt
    FROM _v2_tx_all WHERE award_category = 'assistance' GROUP BY 1, 2
)
SELECT definition, award_key, coalesce(a1_dt, fb_dt) AS new_dt, a1_dt IS NULL AS used_fallback
FROM g WHERE coalesce(a1_dt, fb_dt) IS NOT NULL
UNION ALL   -- contracts and IDVs: the base record (modification 0)
SELECT definition, award_key, min(action_date), false
FROM _v2_tx_all WHERE award_category = 'contract' AND modification_number = '0' GROUP BY 1, 2;

CREATE OR REPLACE TABLE _v2_award_new AS
WITH r AS (   -- the new-award transaction: largest |amount| on the new-award date, then lowest key
    SELECT t.*, d.new_dt, d.used_fallback,
           row_number() OVER (PARTITION BY t.definition, t.award_key ORDER BY abs(t.amt) DESC, t.transaction_key) AS rn,
           sum(t.amt) OVER (PARTITION BY t.definition, t.award_key) AS new_award_amount
    FROM _v2_tx_all t JOIN _v2_new_dt d
      ON d.definition = t.definition AND d.award_key = t.award_key AND t.action_date = d.new_dt
), cyc AS (
    SELECT r.definition, r.award_key,
           arg_min(CASE p.year_format WHEN 'yy' THEN 2000 + TRY_CAST(regexp_extract(r.award_id, p.regex, 1) AS INTEGER)
                                      ELSE TRY_CAST(regexp_extract(r.award_id, p.regex, 1) AS INTEGER) END, p.priority)
               FILTER (WHERE regexp_extract(r.award_id, p.regex, 1) <> '') AS award_cycle
    FROM r CROSS JOIN _v2_cycle_patterns p
    WHERE r.rn = 1 AND r.award_category = 'assistance'
    GROUP BY 1, 2
), cut AS (   -- latest action date per definition x category (metrics 2.3 cut-off of the newest FY)
    SELECT definition, award_category, max(max_action_date) AS cutoff
    FROM mart_award_coverage WHERE NOT is_partial_year GROUP BY 1, 2
), params AS (
    SELECT CAST(cycle_offset_years AS INTEGER) AS cyc_off, CAST(contract_count_min_amount AS DOUBLE) AS cmin
    FROM read_csv('sql/seeds/trend_signal_params.csv', header = true, all_varchar = true)
    WHERE agency_code = getvariable('agency')
)
SELECT getvariable('agency') AS agency_code, r.definition, r.award_key, r.award_id, r.award_category,
       r.award_type_group, r.new_dt AS new_award_date,
       year(r.new_dt) + CASE WHEN month(r.new_dt) >= 10 THEN 1 ELSE 0 END AS new_award_fy,
       -- like period (2.3/2.4): same day-of-FY window as the newest FY's cut-off for the category
       -- leap-safe: the cut-off's calendar date moved to the award's FY
       r.new_dt <= CAST(c.cutoff + to_years((year(r.new_dt) + CASE WHEN month(r.new_dt) >= 10 THEN 1 ELSE 0 END)
                                            - (year(c.cutoff) + CASE WHEN month(c.cutoff) >= 10 THEN 1 ELSE 0 END)) AS DATE) AS in_like_period,
       y.award_cycle,
       -- like-elapsed (7.7): counted through the same calendar point after the cycle start as the
       -- newest data (e.g. Jul 31 of cycle + 1)
       CASE WHEN y.award_cycle IS NULL THEN NULL
            ELSE r.new_dt <= make_date(y.award_cycle + pr.cyc_off, month(c.cutoff), day(c.cutoff)) END AS like_elapsed_flag,
       r.component, r.program_office,
       r.recipient_state, r.pop_state, r.listing, r.program_title AS listing_title,
       r.recipient_type, r.recipient_uei, r.recipient_name,
       r.transaction_key AS new_award_transaction_key,
       r.recipient_state_raw,
       r.new_award_amount,
       CASE WHEN r.award_category = 'contract'
            THEN CASE WHEN r.new_award_amount > pr.cmin THEN 'over_10k' ELSE '10k_or_less' END END AS size_band,
       r.used_fallback,
       (SELECT data_as_of FROM _params) AS data_as_of
FROM r
LEFT JOIN cyc y USING (definition, award_key)
LEFT JOIN cut c ON c.definition = r.definition AND c.award_category = r.award_category
CROSS JOIN params pr
WHERE r.rn = 1;

-- ------------------------------------------------------------ awarding-definition transactions
CREATE OR REPLACE TABLE _v2_tx AS
SELECT transaction_key, award_key, award_category, award_id, fiscal_year, action_date, action_type, modification_number,
       amt, recipient_state_raw AS st, listing, program_title, component,
       award_type_group AS type_group, CASE WHEN award_category = 'assistance' THEN recipient_type END AS recip_type,
       CASE WHEN pop_state <> 'Foreign / unknown' THEN pop_state ELSE recipient_state_raw END AS pop_st,
       pop_is_contractor_address,
       recipient_name
FROM _v2_tx_all WHERE definition = 'awarding';

