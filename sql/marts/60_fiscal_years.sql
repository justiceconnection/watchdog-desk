-- 60_fiscal_years.sql
-- Mart: mart_fiscal_years. Grain: agency x fiscal_year (every FY with any data).
-- Labels and provisional / partial flags per metrics.md 2.3-2.5.

CREATE OR REPLACE TABLE mart_fiscal_years AS
WITH fys AS (
    SELECT fiscal_year FROM _latest_period
    UNION SELECT fiscal_year FROM _award_fy
    UNION SELECT fiscal_year FROM _sub_fy
), aw AS (
    SELECT fiscal_year,
           least(a.first_action_date, s.first_action_date)  AS first_action_date,
           greatest(a.last_action_date, s.last_action_date) AS last_action_date,
           a.last_action_date AS last_prime_action_date,
           s.last_action_date AS last_subaward_action_date
    FROM _award_fy a FULL OUTER JOIN _sub_fy s USING (fiscal_year)
)
SELECT
    getvariable('agency')                                        AS agency_code,
    y.fiscal_year,
    lp.fiscal_year IS NOT NULL                                   AS has_account_data,
    lp.latest_period                                             AS account_latest_period,
    lp.period_end_date                                           AS account_period_end_date,
    lp.latest_period < 12                                        AS account_is_provisional,
    CASE WHEN lp.fiscal_year IS NULL THEN NULL
         WHEN lp.latest_period < 12
         THEN 'FY' || y.fiscal_year || ' (through P' || lp.latest_period || ', ' || strftime(lp.period_end_date, '%b %Y') || ')'
         ELSE 'FY' || y.fiscal_year END                          AS account_label,
    aw.fiscal_year IS NOT NULL                                   AS has_award_data,
    aw.first_action_date                                         AS award_first_action_date,
    aw.last_action_date                                          AS award_last_action_date,
    aw.last_prime_action_date,
    aw.last_subaward_action_date,
    p.data_as_of_date BETWEEN make_date(y.fiscal_year - 1, 10, 1) AND make_date(y.fiscal_year, 9, 30)
                                                                 AS is_partial_year,
    (p.data_as_of_date BETWEEN make_date(y.fiscal_year - 1, 10, 1) AND make_date(y.fiscal_year, 9, 30))
      OR (p.data_as_of_date > make_date(y.fiscal_year, 9, 30)
          AND p.data_as_of_date - make_date(y.fiscal_year, 9, 30) < 90)
                                                                 AS award_is_provisional,
    CASE
      WHEN aw.fiscal_year IS NULL THEN NULL
      WHEN p.data_as_of_date BETWEEN make_date(y.fiscal_year - 1, 10, 1) AND make_date(y.fiscal_year, 9, 30)
      THEN 'FY' || y.fiscal_year || ' (partial: '
           || CASE WHEN date_trunc('month', aw.first_action_date) = date_trunc('month', aw.last_action_date)
                   THEN strftime(aw.first_action_date, '%b %-d') || '-' || strftime(aw.last_action_date, '%-d, %Y')
                   ELSE strftime(aw.first_action_date, '%b %-d, %Y') || '-' || strftime(aw.last_action_date, '%b %-d, %Y') END
           || ')'
      WHEN p.data_as_of_date > make_date(y.fiscal_year, 9, 30)
           AND p.data_as_of_date - make_date(y.fiscal_year, 9, 30) < 90
      THEN 'FY' || y.fiscal_year || ' (provisional, actions through ' || strftime(aw.last_action_date, '%b %-d, %Y') || ')'
      ELSE 'FY' || y.fiscal_year
    END                                                          AS award_label,
    p.data_as_of
FROM fys y
CROSS JOIN _params p
LEFT JOIN _latest_period lp USING (fiscal_year)
LEFT JOIN aw USING (fiscal_year)
ORDER BY y.fiscal_year;

-- ------------------------------------------------------------ mart_award_coverage
-- metrics.md 2.3/2.4 (revised 2026-10-16): award data cut-off per award category. Contracts
-- and grants are labelled separately because their latest action dates differ (DOJ FY2026:
-- contracts through Sep 30, grants through Jul 31).
-- Grain: agency x definition x FY x award_category ('contract' | 'assistance').
CREATE OR REPLACE TABLE mart_award_coverage AS
WITH d AS (
    SELECT definition, fiscal_year, award_category,
           min(action_date) AS min_action_date, max(action_date) AS max_action_date,
           CAST(count(*) AS INTEGER) AS n_transactions, sum(amt) AS obligations
    FROM _award_tx2 GROUP BY ALL
), g AS (
    SELECT d.*, f.is_partial_year, f.is_provisional,
           make_date(d.fiscal_year, 9, 30) AS fy_end_date,
           -- metrics 2.4 reporting-gap rule (agency-neutral)
           (make_date(d.fiscal_year, 9, 30) - d.max_action_date) > 30
             AND p.data_as_of_date > make_date(d.fiscal_year, 9, 30) AS has_reporting_gap,
           d.max_action_date - make_date(d.fiscal_year - 1, 10, 1) AS cutoff_day   -- day of FY of the cut-off
    FROM d JOIN _award_fy f USING (fiscal_year) CROSS JOIN _params p
), prior AS (
    -- For gap rows: in each earlier complete FY of the same definition and category, the share
    -- of net obligations dated after the same day-of-FY (the months still missing), and the
    -- like-period (Oct 1 to the same day) total of the immediately preceding FY.
    SELECT g.definition, g.fiscal_year, g.award_category,
           min(y.missing_share) AS prior_missing_share_min,
           max(y.missing_share) AS prior_missing_share_max,
           arg_max(y.like_period, y.fy) FILTER (WHERE y.fy = g.fiscal_year - 1) AS prior_fy_like_period_obligations
    FROM g
    JOIN (
        SELECT t.definition, t.award_category, t.fiscal_year AS fy, g2.fiscal_year AS gap_fy,
               sum(t.amt) FILTER (WHERE t.action_date - make_date(t.fiscal_year - 1, 10, 1) > g2.cutoff_day) / NULLIF(sum(t.amt), 0) AS missing_share,
               sum(t.amt) FILTER (WHERE t.action_date - make_date(t.fiscal_year - 1, 10, 1) <= g2.cutoff_day) AS like_period
        FROM _award_tx2 t
        JOIN g g2 ON g2.has_reporting_gap AND g2.definition = t.definition AND g2.award_category = t.award_category
                 AND t.fiscal_year < g2.fiscal_year
        JOIN g g3 ON g3.definition = t.definition AND g3.award_category = t.award_category AND g3.fiscal_year = t.fiscal_year
                 AND NOT g3.has_reporting_gap AND NOT g3.is_partial_year
        GROUP BY ALL
    ) y ON y.definition = g.definition AND y.award_category = g.award_category AND y.gap_fy = g.fiscal_year
    WHERE g.has_reporting_gap
    GROUP BY ALL
)
SELECT getvariable('agency') AS agency_code, g.definition, g.fiscal_year, g.award_category,
       CASE g.award_category WHEN 'contract' THEN 'contract' ELSE 'grant' END AS category_word,
       g.min_action_date, g.max_action_date, g.n_transactions, g.obligations,
       g.is_partial_year, g.is_provisional, g.fy_end_date, g.has_reporting_gap,
       CASE
         WHEN g.is_partial_year
         THEN 'FY' || g.fiscal_year || ' (partial: '
              || CASE WHEN date_trunc('month', g.min_action_date) = date_trunc('month', g.max_action_date)
                      THEN strftime(g.min_action_date, '%b %-d') || '-' || strftime(g.max_action_date, '%-d, %Y')
                      ELSE strftime(g.min_action_date, '%b %-d, %Y') || '-' || strftime(g.max_action_date, '%b %-d, %Y') END
              || ')'
         WHEN g.is_provisional
         THEN 'FY' || g.fiscal_year || ' (provisional, '
              || CASE g.award_category WHEN 'contract' THEN 'contract' ELSE 'grant' END
              || ' actions through ' || strftime(g.max_action_date, '%b %-d, %Y') || ')'
         ELSE 'FY' || g.fiscal_year
       END AS award_label,
       CASE WHEN g.has_reporting_gap THEN 'FY' || g.fiscal_year || '*' ELSE 'FY' || g.fiscal_year END AS short_label,
       pr.prior_missing_share_min, pr.prior_missing_share_max,
       CASE WHEN g.has_reporting_gap THEN g.obligations END AS like_period_obligations,
       pr.prior_fy_like_period_obligations,
       -- metrics 2.4: an agency-level override from sql/seeds/award_gap_footnotes.csv (exact reader
       -- text, e.g. DOJ FY2026 grants) wins; otherwise the agency-neutral template.
       CASE WHEN g.has_reporting_gap AND ov.gap_footnote IS NOT NULL THEN ov.gap_footnote
            WHEN g.has_reporting_gap THEN
            'FY' || g.fiscal_year || ' ' || CASE g.award_category WHEN 'contract' THEN 'contract' ELSE 'grant' END
            || ' data runs only through ' || strftime(g.max_action_date, '%B %-d, %Y') || '. '
            || coalesce((SELECT abbreviation FROM _agency_names), 'The agency') || ' has not yet reported '
            || CASE g.award_category WHEN 'contract' THEN 'contracts' ELSE 'grants' END
            || ' made after that date. The FY' || g.fiscal_year || ' total will rise when those reports arrive.'
            || CASE WHEN pr.prior_missing_share_min >= 0.25
                    THEN ' In FY' || (SELECT min(fiscal_year) FROM g WHERE NOT has_reporting_gap AND NOT is_partial_year)
                         || '–FY' || (g.fiscal_year - 1) || ', the missing months carried '
                         || round(100 * pr.prior_missing_share_min)::INTEGER || '% to ' || round(100 * pr.prior_missing_share_max)::INTEGER
                         || '% of each year''s obligations.' ELSE '' END
       END AS gap_footnote,
       CASE WHEN NOT g.has_reporting_gap THEN NULL
            WHEN ov.gap_footnote IS NOT NULL THEN 'agency override' ELSE 'template' END AS gap_footnote_source,
       CASE WHEN g.has_reporting_gap THEN
            CASE g.award_category WHEN 'contract' THEN 'Contracts' ELSE 'Grants' END || ' through '
            || strftime(g.max_action_date, '%b %-d, %Y') || ' only. '
            || strftime(g.max_action_date + 1, '%b') || '–Sep not yet reported.'
       END AS gap_tooltip,
       (SELECT data_as_of FROM _params) AS data_as_of
FROM g
LEFT JOIN prior pr USING (definition, fiscal_year, award_category)
LEFT JOIN (SELECT CAST(fiscal_year AS INTEGER) AS fiscal_year, award_category, gap_footnote
           FROM read_csv('sql/seeds/award_gap_footnotes.csv', header = true, all_varchar = true)
           WHERE agency_code = getvariable('agency')) ov USING (fiscal_year, award_category);

-- Per-category cut-offs and labels on mart_fiscal_years (awarding definition; metrics 2.4).
CREATE OR REPLACE TABLE mart_fiscal_years AS
SELECT y.*,
       c.max_action_date AS last_contract_action_date,
       g.max_action_date AS last_grant_action_date,
       c.award_label     AS contract_award_label,
       g.award_label     AS grant_award_label,
       c.has_reporting_gap AS contract_has_reporting_gap,
       g.has_reporting_gap AS grant_has_reporting_gap
FROM mart_fiscal_years y
LEFT JOIN mart_award_coverage c ON c.fiscal_year = y.fiscal_year AND c.definition = 'awarding' AND c.award_category = 'contract'
LEFT JOIN mart_award_coverage g ON g.fiscal_year = y.fiscal_year AND g.definition = 'awarding' AND g.award_category = 'assistance';
