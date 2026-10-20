-- Analysis views, built on top of the typed base views created by build.py.
-- Each statement is run separately; a view whose inputs are missing is skipped.
--
-- Conventions
--   * File A/B amounts are fiscal-year-to-date as of the latest period pulled
--     (one snapshot per FY): sum across accounts, never across periods.
--   * File C transaction_obligated_amount is per period: summing is correct.
--   * Award "fiscal_year" = fiscal year of the transaction's action_date.

-- One row per prime award, rolled up from its transactions in the pulled window.
CREATE OR REPLACE VIEW prime_awards AS
SELECT
    award_category,
    award_key,
    agency_code,
    arg_max(award_id, action_date)                       AS award_id,
    arg_max(award_type, action_date)                     AS award_type,
    arg_max(awarding_sub_agency_name, action_date)       AS awarding_sub_agency_name,
    arg_max(awarding_agency_code, action_date)           AS awarding_agency_code,
    arg_max(funding_agency_code, action_date)            AS funding_agency_code,
    arg_max(funding_sub_agency_name, action_date)        AS funding_sub_agency_name,
    arg_max(recipient_name, action_date)                 AS recipient_name,
    arg_max(recipient_uei, action_date)                  AS recipient_uei,
    arg_max(recipient_parent_name, action_date)          AS recipient_parent_name,
    arg_max(recipient_state_code, action_date)           AS recipient_state_code,
    arg_max(pop_state_name, action_date)                 AS pop_state_name,
    arg_max(program_code, action_date)                   AS program_code,
    arg_max(program_title, action_date)                  AS program_title,
    arg_max(coalesce(base_description, description), action_date) AS description,
    min(action_date)                                     AS first_action_date_in_window,
    max(action_date)                                     AS last_action_date_in_window,
    count(*)                                             AS n_transactions,
    sum(federal_action_obligation)                       AS obligated_in_window,
    sum(federal_action_obligation) FILTER (WHERE federal_action_obligation < 0) AS deobligated_in_window,
    max(total_outlayed_amount_for_overall_award)         AS total_outlayed_to_date,
    arg_max(usaspending_permalink, action_date)          AS usaspending_permalink
FROM prime_transactions
GROUP BY award_category, award_key, agency_code;

-- Budget picture per Treasury account per fiscal year (File A).
CREATE OR REPLACE VIEW account_year AS
SELECT
    agency_code,
    fiscal_year,
    submission_period_num                     AS period,
    federal_account_symbol,
    federal_account_name,
    treasury_account_symbol,
    treasury_account_name,
    total_budgetary_resources,
    obligations_incurred,
    gross_outlay_amount,
    unobligated_balance,
    obligations_incurred / NULLIF(total_budgetary_resources, 0) AS execution_rate
FROM account_balances;

-- Federal-account level roll-up (e.g. "Salaries and Expenses, FBI").
CREATE OR REPLACE VIEW federal_account_year AS
SELECT
    agency_code, fiscal_year, max(period) AS period,
    federal_account_symbol, federal_account_name,
    sum(total_budgetary_resources) AS total_budgetary_resources,
    sum(obligations_incurred)      AS obligations_incurred,
    sum(gross_outlay_amount)       AS gross_outlay_amount,
    sum(obligations_incurred) / NULLIF(sum(total_budgetary_resources), 0) AS execution_rate
FROM account_year
GROUP BY ALL;

-- What the money buys: obligations by object class (File B).
CREATE OR REPLACE VIEW object_class_year AS
SELECT
    agency_code,
    fiscal_year,
    CASE left(replace(object_class_code, '.', ''), 1)
        WHEN '1' THEN 'Personnel compensation & benefits'
        WHEN '2' THEN 'Contractual services & supplies'
        WHEN '3' THEN 'Acquisition of assets'
        WHEN '4' THEN 'Grants & fixed charges'
        WHEN '9' THEN 'Other'
        ELSE 'Unknown'
    END                                AS object_class_major,
    object_class_code,
    object_class_name,
    direct_or_reimbursable_funding_source,
    sum(obligations_incurred)          AS obligations_incurred,
    sum(gross_outlay_amount_FYB_to_period_end) AS gross_outlays
FROM account_activity
GROUP BY ALL;

-- Program activity x object class, by federal account.
CREATE OR REPLACE VIEW program_activity_year AS
SELECT
    agency_code, fiscal_year,
    federal_account_symbol, federal_account_name,
    program_activity_code, program_activity_name,
    sum(obligations_incurred)                  AS obligations_incurred,
    sum(gross_outlay_amount_FYB_to_period_end) AS gross_outlays
FROM account_activity
GROUP BY ALL;

-- Money flowing from prime recipients to sub-recipients.
CREATE OR REPLACE VIEW subaward_flows AS
SELECT
    agency_code,
    fiscal_year,
    award_category,
    prime_award_awarding_sub_agency_name AS awarding_sub_agency_name,
    prime_award_unique_key,
    prime_awardee_name,
    prime_awardee_uei,
    prime_awardee_state_code,
    subawardee_name,
    subawardee_uei,
    subawardee_state_code,
    subawardee_city_name,
    count(*)            AS n_subawards,
    sum(subaward_amount) AS subaward_amount
FROM subawards
GROUP BY ALL;

-- One row per fiscal year: budget, awards, sub-awards side by side.
-- Award totals use the AWARDING-agency definition.
CREATE OR REPLACE VIEW agency_year_summary AS
WITH acct AS (
    SELECT agency_code, fiscal_year, max(submission_period_num) AS latest_period,
           sum(total_budgetary_resources) AS budgetary_resources,
           sum(obligations_incurred)      AS obligations,
           sum(gross_outlay_amount)       AS outlays
    FROM account_balances GROUP BY 1, 2
), prime AS (
    SELECT agency_code, fiscal_year,
           sum(federal_action_obligation) FILTER (WHERE award_category = 'contract')   AS contract_obligations,
           sum(federal_action_obligation) FILTER (WHERE award_category = 'assistance') AS assistance_obligations,
           count(*) AS prime_transactions
    FROM prime_transactions WHERE awarding_agency_code = agency_code GROUP BY 1, 2
), sub AS (
    SELECT agency_code, fiscal_year, sum(subaward_amount) AS subaward_amount, count(*) AS subawards
    FROM subawards WHERE prime_award_awarding_agency_code = agency_code GROUP BY 1, 2
)
SELECT *
FROM acct
FULL OUTER JOIN prime USING (agency_code, fiscal_year)
FULL OUTER JOIN sub USING (agency_code, fiscal_year)
ORDER BY agency_code, fiscal_year;
