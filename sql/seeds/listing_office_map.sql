-- Generates sql/seeds/listing_office_map.csv (metrics.md 6.2 rule 1, null-office step 2).
-- For each agency x assistance listing (program_code): the awarding office that awards
-- >= 95% of the listing's agency-awarded assistance transactions with a known office.
-- Listings without such an office are omitted. Regenerate after a data refresh:
--   python sql/build_marts.py --regen-listing-map
SELECT agency_code, program_code, awarding_office_name AS office,
       n_rows AS office_rows, total_rows AS known_office_rows, round(share, 4) AS share
FROM (
    SELECT agency_code, program_code, awarding_office_name, n_rows,
           sum(n_rows) OVER (PARTITION BY agency_code, program_code) AS total_rows,
           n_rows / sum(n_rows) OVER (PARTITION BY agency_code, program_code) AS share
    FROM (SELECT agency_code, program_code, awarding_office_name, count(*) AS n_rows
          FROM prime_transactions
          WHERE award_category = 'assistance' AND awarding_agency_code = agency_code
            AND awarding_office_name IS NOT NULL AND program_code IS NOT NULL
          GROUP BY ALL)
)
WHERE share >= 0.95
ORDER BY agency_code, program_code
