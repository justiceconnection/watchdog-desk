-- reconcile_desk.sql: checks for the Watchdog Desk marts (marts/<agency>/desk/), Card 4 (state anomalies).
-- Same output shape as reconcile_marts.sql. Prototype parity is checked separately by
-- sql/checks/desk_card4_prototype.py (runs the reference prototype when it is present).
WITH
cd AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet')),
cv AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_caveats.parquet')),
se AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_series.parquet')),
co AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_components.parquet')),
pg AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_programs.parquet')),
rc AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_recipients.parquet')),
rw AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_rows.parquet')),
sc AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_scores.parquet')),
pa AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_params.parquet')),
tx AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card4_text.parquet')),
c2s AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_summary.parquet')),
c2x AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_exclusion_choices.parquet')),
c2r AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_reasons.parquet')),
c2t AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_recipient_types.parquet')),
c2a AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_top_awards.parquet')),
c2w AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_rows.parquet')),
c2p AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_params.parquet')),
c2txt AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card2_text.parquet')),
nc AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet')),
nsc AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_scores.parquet')),
nrw AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_rows.parquet')),
nse AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_series.parquet')),
nco AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_components.parquet')),
npg AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_programs.parquet')),
nor AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_organizations.parquet')),
ncv AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_caveats.parquet')),
v2an AS (SELECT * FROM read_parquet(getvariable('desk_new_awards'))),   -- assistance new awards (metrics 7.7): v2/award_new.parquet, or the same rows from 75_new_awards.sql
signoffs AS (SELECT card_id FROM read_csv(getvariable('signoffs_csv'), header = true, all_varchar = true) WHERE coalesce(card_id, '') <> ''),
allcards AS (SELECT card_id, status, verified_on FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') UNION ALL SELECT card_id, status, verified_on FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet')
             UNION ALL SELECT card_id, status, verified_on FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') UNION ALL SELECT card_id, status, verified_on FROM read_parquet(getvariable('marts_dir') || '/desk/card2_summary.parquet')),
pubids AS (SELECT card_id FROM allcards WHERE status IN ('card', 'label') AND verified_on IS NOT NULL AND card_id IN (SELECT card_id FROM signoffs)),
heldids AS (SELECT card_id FROM allcards WHERE card_id NOT IN (SELECT card_id FROM pubids)),
heldonly AS (SELECT DISTINCT x FROM (SELECT c.headline AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') c UNION ALL SELECT c.label_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') c UNION ALL SELECT c.why_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') c UNION ALL SELECT c.headline AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet') c UNION ALL SELECT c.why_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet') c UNION ALL SELECT c.headline AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') c UNION ALL SELECT c.second_line AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') c UNION ALL SELECT c.label_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') c UNION ALL SELECT text, card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_caveats.parquet') UNION ALL SELECT text, card_id FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_caveats.parquet') UNION ALL SELECT text, card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_caveats.parquet')) WHERE x IS NOT NULL AND card_id IN (SELECT card_id FROM heldids)
             EXCEPT SELECT x FROM (SELECT c.headline AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') c UNION ALL SELECT c.label_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') c UNION ALL SELECT c.why_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') c UNION ALL SELECT c.headline AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet') c UNION ALL SELECT c.why_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet') c UNION ALL SELECT c.headline AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') c UNION ALL SELECT c.second_line AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') c UNION ALL SELECT c.label_text AS x, c.card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') c UNION ALL SELECT text, card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card4_caveats.parquet') UNION ALL SELECT text, card_id FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_caveats.parquet') UNION ALL SELECT text, card_id FROM read_parquet(getvariable('marts_dir') || '/desk/card3_caveats.parquet')) WHERE card_id IN (SELECT card_id FROM pubids)),
manifest_pq AS (SELECT list_concat(card_types.state_stand_out.parquet, card_types.national_organizations.parquet,
                                   card_types.grant_categories.parquet, card_types.contracts_without_competition.parquet) AS p
                FROM read_json(getvariable('marts_dir') || '/desk/manifest.json')),
c3c AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet')),
c3m AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_mix.parquet')),
c3p AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_periods.parquet')),
c3s AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_scopes.parquet')),
c3l AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_listings.parquet')),
c3r AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_rows.parquet')),
c3k AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_categories.parquet')),
c3v AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_caveats.parquet')),
c3cap AS (SELECT * FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cvf_cap.parquet')),
spec_c3_cal(fy, n, conf) AS (VALUES (2018, 3, 3), (2019, 1, 1), (2020, 8, 4), (2021, 9, 2), (2022, 2, 1), (2023, 0, 0), (2024, 4, 2)),
spec_c3_32(period, segment, m) AS (VALUES   -- watchdog-cards 3.2, OJP scope, $M
    ('FY2017–2019', 'Crime victim services', 8386), ('FY2020–2022', 'Crime victim services', 5110), ('FY2023–2025', 'Crime victim services', 4243),
    ('FY2017–2019', 'Byrne JAG and flexible justice assistance', 921), ('FY2023–2025', 'Violence reduction and prevention', 471),
    ('FY2020–2022', 'SCAAP', 210), ('FY2023–2025', 'SCAAP', 223), ('FY2023–2025', 'Congressionally directed and other', 578),
    ('FY2017–2019', 'Research, statistics and forensics', 996), ('FY2023–2025', 'Courts, prosecution and defense', 67)),
c2prm AS (SELECT max(CASE WHEN parameter = 'sap_threshold' THEN TRY_CAST(value AS DOUBLE) END) AS thr,
                 max(CASE WHEN parameter = 'concentration_share' THEN TRY_CAST(value AS DOUBLE) END) AS conc,
                 max(CASE WHEN parameter = 'org_type_first_fy' THEN TRY_CAST(value AS INTEGER) END) AS orgfy FROM c2p),
-- independent Card 2 universe (NULL-safe code test; DOJ codes as in the spec)
c2i AS (
    WITH b AS (SELECT p.fiscal_year fy, p.federal_action_obligation amt, ct.extent_competed_code ec, ct.solicitation_procedures_code sp,
                      ct.other_than_full_and_open_competition_code oth,
                      coalesce(try_cast(ct.base_and_all_options_value AS DOUBLE), p.federal_action_obligation) val
               FROM prime_transactions p JOIN contract_transactions ct ON ct.contract_transaction_unique_key = p.transaction_key
               WHERE p.agency_code = getvariable('agency') AND p.awarding_agency_code = p.agency_code
                 AND p.award_category = 'contract' AND p.modification_number = '0'),
         u AS (SELECT *, CASE WHEN ec IN ('B', 'C', 'NDO') THEN 'NC' WHEN ec IN ('A', 'D', 'E', 'CDO') THEN 'C' END cls FROM b, c2prm
               WHERE NOT (coalesce(ec IN ('F', 'G'), false) OR coalesce(sp = 'SP1', false) OR coalesce(oth IN ('SP2', 'MPT'), false))
                 AND val > c2prm.thr)
    SELECT fy, count(*) FILTER (WHERE cls = 'NC') n_nc, count(*) FILTER (WHERE cls IS NOT NULL) n_u,
           sum(amt) FILTER (WHERE cls = 'NC') d_nc, sum(amt) FILTER (WHERE cls IS NOT NULL) d_u FROM u GROUP BY 1),
spec_c2(fy, both_n, both_u, code_n, code_u, val_n, val_u, d_nc, d_u) AS (VALUES   -- watchdog-cards 2.1 (DOJ)
    (2017, 655, 2765, 6321, 34098, 779, 3331, 677.6, 3101.7), (2018, 773, 2989, 8446, 37064, 887, 3536, 756.5, 3026.9),
    (2019, 831, 3084, 7780, 27013, 932, 3569, 741.0, 3263.2), (2020, 785, 3160, 6577, 22897, 924, 3732, 748.3, 3405.8),
    (2021, 651, 3221, 4613, 22971, 829, 3853, 539.0, 3641.8), (2022, 486, 2686, 5051, 22060, 630, 3262, 406.0, 2637.6),
    (2023, 516, 2846, 5351, 21433, 680, 3445, 459.8, 3839.2), (2024, 395, 2483, 4629, 19095, 515, 3044, 319.4, 3089.5),
    (2025, 404, 2203, 4532, 16985, 525, 2759, 393.1, 2209.9), (2026, 555, 2612, 4000, 15670, 710, 3275, 861.5, 3225.4)),
prm AS (SELECT max(CASE WHEN parameter = 'size_dollars' THEN TRY_CAST(value AS DOUBLE) END) AS size_d,
               max(CASE WHEN parameter = 'size_counts' THEN TRY_CAST(value AS DOUBLE) END) AS size_c,
               max(CASE WHEN parameter = 'contract_min_amount' THEN TRY_CAST(value AS DOUBLE) END) AS cmin,
               coalesce(max(CASE WHEN parameter = 'excluded_states' THEN value END), '') AS excluded
        FROM pa),
-- value of each card in its own measure, from its award rows
rv AS (SELECT r.card_id, r.year_role, count(*) AS n, sum(r.amount) AS amt FROM rw r WHERE row_kind = 'award' GROUP BY ALL),
cardv AS (SELECT card_id, measure, 'prior' AS year_role, prior_value AS v, rest_prior AS rest FROM cd
          UNION ALL SELECT card_id, measure, 'current', current_value, rest_current FROM cd),
-- independent national total: contract new awards (metrics 7.7: base record, modification 0) from prime_transactions,
-- awarding definition, over the size band, recipient state of the largest new-award-date transaction, excluded states out
ind_c AS (
    WITH t AS (SELECT award_key, action_date, transaction_key, federal_action_obligation AS amt, recipient_state_code AS st
               FROM prime_transactions
               WHERE agency_code = getvariable('agency') AND awarding_agency_code = agency_code AND award_category = 'contract'),
         d AS (SELECT award_key, min(action_date) AS nd FROM prime_transactions
               WHERE agency_code = getvariable('agency') AND awarding_agency_code = agency_code AND award_category = 'contract'
                 AND modification_number = '0' GROUP BY 1),
         a AS (SELECT t.award_key, d.nd, sum(t.amt) AS amt, arg_min(t.st, (-abs(t.amt), t.transaction_key)) AS st
               FROM t JOIN d ON d.award_key = t.award_key AND t.action_date = d.nd GROUP BY 1, 2)
    SELECT year(nd) + CASE WHEN month(nd) >= 10 THEN 1 ELSE 0 END AS fy, count(*) AS n, sum(amt) AS amt
    FROM a, prm WHERE st IS NOT NULL AND amt > prm.cmin AND list_position(string_split(prm.excluded, ' '), st) IS NULL GROUP BY 1),
checks(check_name, fiscal_year, definition, expected, actual, is_count) AS (
    SELECT 'desk card4: card_id unique (duplicates)', NULL, NULL, 0, (SELECT count(*) - count(DISTINCT card_id) FROM cd), true
    UNION ALL SELECT 'desk card4: status is card / label / hold / suppressed; headline, why-text, fixed line present (bad rows)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE status NOT IN ('card', 'label', 'hold', 'suppressed') OR coalesce(headline, '') = ''
              OR coalesce(why_text, '') = '' OR coalesce(fixed_line, '') = ''), true
    UNION ALL SELECT 'desk card4: label cards with a driver carry label text naming it (display name; missing)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE driver_kind IS NOT NULL AND (label_text IS NULL OR position(driver_display_name IN label_text) = 0)), true
    UNION ALL SELECT 'desk card4: reader text uses short component names (recorded long names in label_text)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE label_text LIKE '%Federal Bureau of Investigation%' OR label_text LIKE '%Offices, Boards and Divisions%'), true
    UNION ALL SELECT 'desk card4: no share above 100% shown as a number (driver_share_display)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE driver_share > 1 AND driver_share_display <> '100%+'), true
    UNION ALL SELECT 'desk card4: award-cycle candidates have status evidence (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM sc WHERE basis = 'cycle' AND is_candidate AND rule_status <> 'evidence'), true
    UNION ALL SELECT 'desk card4: national organizations absent from grant scores and rows (rows)', NULL, NULL, 0,
           (SELECT count(*) FROM rw JOIN cd USING (card_id) WHERE cd.award_category = 'assistance'
              AND rw.recipient_uei IN (SELECT recipient_uei FROM read_parquet(getvariable('marts_dir') || '/desk/card4_national_orgs.parquet'))), true
    UNION ALL SELECT 'desk card4: cards = published fiscal-year candidates (symmetric difference)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT card_id FROM sc WHERE basis = 'fy' AND is_candidate EXCEPT SELECT card_id FROM cd)
            ) + (SELECT count(*) FROM (SELECT card_id FROM cd EXCEPT SELECT card_id FROM sc)), true
    UNION ALL SELECT 'desk card4: award-cycle rows never make a card (cycle rows with card_id)', NULL, NULL, 0,
           (SELECT count(*) FROM sc WHERE basis = 'cycle' AND card_id IS NOT NULL), true
    UNION ALL SELECT 'desk card4: excluded states absent from scores and cards (rows)', NULL, NULL, 0,
           (SELECT count(*) FROM sc, prm WHERE list_position(string_split(prm.excluded, ' '), sc.state) IS NOT NULL)
           + (SELECT count(*) FROM cd, prm WHERE list_position(string_split(prm.excluded, ' '), cd.state) IS NOT NULL), true
    UNION ALL SELECT 'desk card4: no percent when the prior value is below the size floor (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM cd, prm WHERE pct_change IS NOT NULL
              AND prior_value < CASE measure WHEN 'dollars' THEN prm.size_d ELSE prm.size_c END), true
    UNION ALL SELECT 'desk card4: no percent sign in headlines without pct_change (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE pct_change IS NULL AND regexp_matches(split_part(headline, ',', 1), '[0-9]%')), true
    UNION ALL SELECT 'desk card4: "anomal" never appears in reader text (rows)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE headline ILIKE '%anomal%' OR why_text ILIKE '%anomal%' OR period_label ILIKE '%anomal%')
           + (SELECT count(*) FROM cv WHERE text ILIKE '%anomal%') + (SELECT count(*) FROM tx WHERE template ILIKE '%anomal%'), true
    UNION ALL SELECT 'desk card4: every card carries the fixed "doesn''t indicate anything improper" line (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE fixed_line NOT ILIKE '%improper%'), true
    UNION ALL SELECT 'desk card4: every grant card carries the OJP gap note (missing; agencies with an OJP list)', NULL, NULL, 0,
           (SELECT count(*) FROM cd, pa WHERE pa.parameter = 'ojp_dashboard_csv' AND coalesce(pa.value, '') <> ''
              AND award_category = 'assistance' AND NOT list_contains(caveat_keys, 'ojp_gap')), true
    UNION ALL SELECT 'desk card4 (DOJ): OJP gap note k for NY / ME / VA = 30 / 19 / 39 (spec 4.6)', NULL, NULL, 301939,
           (SELECT 10000 * max(ojp_missing_awards) FILTER (WHERE state = 'NY') + 100 * max(ojp_missing_awards) FILTER (WHERE state = 'ME')
                   + max(ojp_missing_awards) FILTER (WHERE state = 'VA') FROM cd WHERE award_category = 'assistance' AND fiscal_year = 2026), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card4 (DOJ): national organizations = 145 with explicit tie handling (spec 4.9)', NULL, NULL, 145,
           (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_national_orgs.parquet')), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card4 (DOJ): AK FY2026 contracts recorded as performed in Alaska = 28.6% (spec 4.7)', 2026, NULL, 28.6,
           (SELECT round(100 * pop_in_state_share, 1) FROM cd WHERE state = 'AK' AND fiscal_year = 2026 AND award_category = 'contract'), false
           WHERE getvariable('agency') = '015' 
    UNION ALL SELECT 'desk card4: gap-year grant cards carry the cut-off caveat and gap wording (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE award_category = 'assistance' AND list_contains(flags, 'gap_year')
              AND NOT (list_contains(caveat_keys, 'grant_cutoff') AND like_period)), true
    UNION ALL SELECT 'desk card4: contract cards carry the contractor-address caveat (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE award_category = 'contract' AND NOT list_contains(caveat_keys, 'contractor_address')), true
    UNION ALL SELECT 'desk card4: caveat table matches caveat_keys (mismatched cards)', NULL, NULL, 0,
           (SELECT count(*) FROM cd LEFT JOIN (SELECT card_id, list(caveat_key ORDER BY sort) AS k FROM cv GROUP BY 1) x USING (card_id)
            WHERE x.k IS DISTINCT FROM cd.caveat_keys), true
    UNION ALL SELECT 'desk card4: pass-through caveat exactly on grant cards with state-agency share >= minimum (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM cd, (SELECT TRY_CAST(value AS DOUBLE) AS m FROM pa WHERE parameter = 'pass_through_min_share') q
            WHERE award_category = 'assistance'
              AND (coalesce(state_agency_share, 0) >= q.m) <> list_contains(caveat_keys, 'pass_through')), true
    UNION ALL SELECT 'desk card4: why-text gap lies outside the quoted band (cards inside)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE gap_outside_band = false), true
    UNION ALL SELECT 'desk card4: count cards under the dollar-change minimum are suppressed (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM cd, (SELECT TRY_CAST(value AS DOUBLE) AS m FROM pa WHERE parameter = 'count_card_min_dollar_change') q
            WHERE measure = 'count' AND q.m > 0 AND abs(dollar_change_same_rows) < q.m AND status <> 'suppressed'), true
    UNION ALL SELECT 'desk card4: change = current - prior; rest = national - state (bad rows)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE abs(change - (current_value - prior_value)) >= 0.01
              OR abs(rest_prior - (national_prior - prior_value)) >= 0.01 OR abs(rest_current - (national_current - current_value)) >= 0.01), true
    UNION ALL SELECT 'desk card4: award rows add up to the card value, each year (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM cardv c LEFT JOIN rv USING (card_id, year_role)
            WHERE abs(c.v - CASE c.measure WHEN 'dollars' THEN coalesce(rv.amt, 0) ELSE coalesce(rv.n, 0) END) >= 0.01), true
    UNION ALL SELECT 'desk card4: CSV total rows = card state and rest values (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM cardv c
            JOIN rw s ON s.card_id = c.card_id AND s.year_role = c.year_role AND s.row_kind = 'state_total'
            JOIN rw r ON r.card_id = c.card_id AND r.year_role = c.year_role AND r.row_kind = 'rest_total'
            WHERE abs(c.v - CASE c.measure WHEN 'dollars' THEN s.amount ELSE s.n_awards END) >= 0.01
               OR abs(c.rest - CASE c.measure WHEN 'dollars' THEN r.amount ELSE r.n_awards END) >= 0.01), true
    UNION ALL SELECT 'desk card4: CSV state totals (count and dollars) = award rows (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM rw s JOIN rv USING (card_id, year_role)
            WHERE s.row_kind = 'state_total' AND (s.n_awards <> rv.n OR abs(s.amount - rv.amt) >= 0.01)), true
    UNION ALL SELECT 'desk card4: components add up to the award rows (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT card_id, sum(prior_count) pc, sum(current_count) cc, sum(prior_dollars) pd, sum(current_dollars) cdl FROM co GROUP BY 1) x
            JOIN (SELECT card_id, sum(n) FILTER (WHERE year_role = 'prior') pc, sum(n) FILTER (WHERE year_role = 'current') cc,
                         coalesce(sum(amt) FILTER (WHERE year_role = 'prior'), 0) pd, coalesce(sum(amt) FILTER (WHERE year_role = 'current'), 0) cdl
                  FROM rv GROUP BY 1) y USING (card_id)
            WHERE coalesce(x.pc, 0) <> coalesce(y.pc, 0) OR coalesce(x.cc, 0) <> coalesce(y.cc, 0) OR abs(x.pd - y.pd) >= 0.01 OR abs(x.cdl - y.cdl) >= 0.01), true
    UNION ALL SELECT 'desk card4: programs add up to the award rows, grant cards (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT card_id, sum(prior_dollars) + sum(current_dollars) d, sum(prior_count) + sum(current_count) n FROM pg GROUP BY 1) x
            JOIN (SELECT card_id, coalesce(sum(amt), 0) d, sum(n) n FROM rv GROUP BY 1) y USING (card_id)
            WHERE abs(x.d - y.d) >= 0.01 OR x.n <> y.n)
           + (SELECT count(*) FROM cd WHERE award_category = 'assistance' AND card_id NOT IN (SELECT card_id FROM pg)), true
    UNION ALL SELECT 'desk card4: at most 5 recipients per card, ranked 1..n (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT card_id, count(*) n, max(rank) mx FROM rc GROUP BY 1) WHERE n > 5 OR mx <> n), true
    UNION ALL SELECT 'desk card4: chart series = card values; prior index = 100 (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM se JOIN cardv c ON c.card_id = se.card_id AND c.year_role = se.year_role
            WHERE se.panel = 'fiscal_year' AND abs(se.value - CASE se.entity WHEN 'state' THEN c.v ELSE c.rest END) >= 0.01)
           + (SELECT count(*) FROM se WHERE year_role = 'prior' AND value > 0 AND abs(index_value - 100) > 1e-9), true
    UNION ALL SELECT 'desk card4: complete-year grant cards have an award-cycle panel (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE award_category = 'assistance' AND NOT is_provisional
              AND card_id NOT IN (SELECT card_id FROM se WHERE panel = 'award_cycle')), true
    UNION ALL SELECT 'desk card4: national totals are the sum over states (bad series)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT fiscal_year, award_category, measure, basis, max(national_current) nc, sum(current_value) s,
                                         max(national_prior) np, sum(prior_value) sp
                                  FROM sc GROUP BY ALL) WHERE abs(nc - s) >= 0.01 OR abs(np - sp) >= 0.01), true
    UNION ALL SELECT 'desk card4: independent contract new-award count from prime_transactions (published, FY basis)', f.fy, 'awarding',
           i.n, (SELECT max(national_current) FROM sc WHERE basis = 'fy' AND award_category = 'contract'
                   AND measure = 'count' AND fiscal_year = f.fy), true
           FROM (SELECT DISTINCT fiscal_year AS fy FROM sc WHERE award_category = 'contract') f JOIN ind_c i ON i.fy = f.fy
    UNION ALL SELECT 'desk card4: independent contract new-award dollars from prime_transactions (published, FY basis)', f.fy, 'awarding',
           i.amt, (SELECT max(national_current) FROM sc WHERE basis = 'fy' AND award_category = 'contract'
                     AND measure = 'dollars' AND fiscal_year = f.fy), false
           FROM (SELECT DISTINCT fiscal_year AS fy FROM sc WHERE award_category = 'contract') f JOIN ind_c i ON i.fy = f.fy
    -- ---------------------------------------------------------------- Card 2
    UNION ALL SELECT 'desk card2: summary = independent NULL-safe universe from prime_transactions, card FYs (mismatching FYs)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s LEFT JOIN c2i ON c2i.fy = c2s.fiscal_year
            WHERE c2i.fy IS NULL OR c2s.n_not_competed <> c2i.n_nc OR c2s.n_universe <> c2i.n_u
               OR abs(c2s.dollars_not_competed - c2i.d_nc) >= 0.01 OR abs(c2s.dollars_universe - c2i.d_u) >= 0.01), true
    UNION ALL SELECT 'desk card2 (DOJ): exclusion-choice table and dollars = spec 2.1 (mismatching FYs)', NULL, NULL, 0,
           (SELECT count(*) FROM spec_c2 s
              LEFT JOIN c2x b ON b.fiscal_year = s.fy AND b.rule = 'both' LEFT JOIN c2x c ON c.fiscal_year = s.fy AND c.rule = 'code_only'
              LEFT JOIN c2x v ON v.fiscal_year = s.fy AND v.rule = 'value_only' LEFT JOIN c2s m ON m.fiscal_year = s.fy
            WHERE b.n_not_competed IS DISTINCT FROM s.both_n OR b.n_universe IS DISTINCT FROM s.both_u
               OR c.n_not_competed IS DISTINCT FROM s.code_n OR c.n_universe IS DISTINCT FROM s.code_u
               OR v.n_not_competed IS DISTINCT FROM s.val_n OR v.n_universe IS DISTINCT FROM s.val_u
               OR round(m.dollars_not_competed / 1e6, 1) IS DISTINCT FROM s.d_nc OR round(m.dollars_universe / 1e6, 1) IS DISTINCT FROM s.d_u), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card2: default exclusion rule = summary (mismatching FYs)', NULL, NULL, 0,
           (SELECT count(*) FROM c2x JOIN c2s USING (fiscal_year) WHERE rule = 'both'
              AND (c2x.n_not_competed <> c2s.n_not_competed OR c2x.n_universe <> c2s.n_universe)), true
    UNION ALL SELECT 'desk card2: reasons add up to not-competed awards and dollars; utilities band = UT (mismatching FYs)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s JOIN (SELECT fiscal_year, sum(n_awards) n, sum(dollars) d,
                                                  sum(n_awards) FILTER (WHERE band = 'utilities') nu, coalesce(sum(dollars) FILTER (WHERE band = 'utilities'), 0) du
                                           FROM c2r GROUP BY 1) r USING (fiscal_year)
            WHERE r.n <> c2s.n_not_competed OR abs(r.d - c2s.dollars_not_competed) >= 0.01
               OR coalesce(r.nu, 0) <> c2s.n_utilities OR abs(r.du - c2s.dollars_utilities) >= 0.01), true
    UNION ALL SELECT 'desk card2: additive recipient dimensions add up to not-competed (size, set-aside all years; org type from first FY)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s JOIN (SELECT fiscal_year, dimension, sum(n_awards) n, sum(dollars) d FROM c2t WHERE is_additive GROUP BY 1, 2) t
              USING (fiscal_year) CROSS JOIN c2prm
            WHERE (t.dimension <> 'organization_type' OR c2s.fiscal_year >= c2prm.orgfy)
              AND (t.n <> c2s.n_not_competed OR abs(t.d - c2s.dollars_not_competed) >= 0.01)), true
    UNION ALL SELECT 'desk card2: no organization type before its first FY; flags are never additive (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM c2t, c2prm WHERE dimension = 'organization_type' AND fiscal_year < c2prm.orgfy)
           + (SELECT count(*) FROM c2t WHERE dimension = 'flag' AND is_additive)
           + (SELECT count(*) FROM c2w, c2prm WHERE organization_type IS NOT NULL AND fiscal_year < c2prm.orgfy), true
    UNION ALL SELECT 'desk card2: CSV rows = not-competed awards and dollars per FY (mismatching FYs)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s LEFT JOIN (SELECT fiscal_year, count(*) n, sum(amount) d FROM c2w GROUP BY 1) w USING (fiscal_year)
            WHERE coalesce(w.n, 0) <> c2s.n_not_competed OR abs(coalesce(w.d, 0) - c2s.dollars_not_competed) >= 0.01), true
    UNION ALL SELECT 'desk card2: top awards shown exactly when the largest is >= the concentration share (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s LEFT JOIN c2a a ON a.fiscal_year = c2s.fiscal_year AND a.rank = 1 CROSS JOIN c2prm
            WHERE c2s.show_top_awards <> (a.share_of_not_competed_dollars >= c2prm.conc)
               OR (c2s.show_top_awards AND c2s.concentration_line IS NULL)), true
    UNION ALL SELECT 'desk card2: headline on every FY; provisional note on provisional FYs (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s WHERE headline IS NULL OR (is_provisional AND provisional_note IS NULL)), true
    UNION ALL SELECT 'desk card2 (DOJ): FY2026 headline numbers 555 of 2,612; $861.5M of $3,225.4M', 2026, NULL, 1,
           (SELECT count(*) FROM c2s WHERE fiscal_year = 2026 AND n_not_competed = 555 AND n_universe = 2612
              AND round(dollars_not_competed / 1e6, 1) = 861.5 AND round(dollars_universe / 1e6, 1) = 3225.4
              AND headline LIKE '%555 of 2,612%'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card2 (DOJ): FY2026 concentration line names V2X ($158.0M, 18%)', 2026, NULL, 1,
           (SELECT count(*) FROM c2s WHERE fiscal_year = 2026 AND concentration_line LIKE '%$158.0 million to V2X Systems%18%'), true
           WHERE getvariable('agency') = '015'
    -- ---------------------------------------------------------------- national organizations (spec 4.9)
    UNION ALL SELECT 'desk natorg: group + rest + other-DC = all new grants, FY basis without like period (independent: new-award table; mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM nsc JOIN (SELECT new_award_fy fy, count(*) n, sum(new_award_amount) d FROM v2an WHERE definition = 'awarding' GROUP BY 1) a
              ON a.fy = nsc.fiscal_year
            WHERE nsc.basis = 'fy' AND NOT EXISTS (SELECT 1 FROM nc WHERE nc.fiscal_year = nsc.fiscal_year AND nc.like_period)
              AND abs(nsc.group_current + nsc.rest_current + nsc.hq_other_current - CASE nsc.measure WHEN 'count' THEN a.n ELSE a.d END) >= 0.01), true
    UNION ALL SELECT 'desk natorg: cards = fiscal-year candidates (symmetric difference)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT fiscal_year, measure FROM nsc WHERE basis = 'fy' AND is_candidate EXCEPT SELECT fiscal_year, measure FROM nc))
           + (SELECT count(*) FROM (SELECT fiscal_year, measure FROM nc EXCEPT SELECT fiscal_year, measure FROM nsc WHERE basis = 'fy' AND is_candidate)), true
    UNION ALL SELECT 'desk natorg: award rows add up to the group value; total rows = scores (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM nc JOIN (SELECT card_id, year_role, count(*) n, sum(amount) d FROM nrw WHERE row_kind = 'award' GROUP BY 1, 2) r USING (card_id)
            WHERE abs(CASE r.year_role WHEN 'prior' THEN nc.group_prior ELSE nc.group_current END
                      - CASE nc.measure WHEN 'count' THEN r.n ELSE r.d END) >= 0.01)
           + (SELECT count(*) FROM nc JOIN nrw t ON t.card_id = nc.card_id AND t.row_kind = 'rest_total'
              WHERE abs(CASE t.year_role WHEN 'prior' THEN nc.rest_prior ELSE nc.rest_current END
                        - CASE nc.measure WHEN 'count' THEN t.n_awards ELSE t.amount END) >= 0.01), true
    UNION ALL SELECT 'desk natorg: components, programs and organizations tables tie to the award rows (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT card_id, sum(prior_dollars + current_dollars) d, sum(prior_count + current_count) n FROM nco GROUP BY 1) x
              JOIN (SELECT card_id, sum(amount) d, count(*) n FROM nrw WHERE row_kind = 'award' GROUP BY 1) y USING (card_id)
            WHERE abs(x.d - y.d) >= 0.01 OR x.n <> y.n)
           + (SELECT count(*) FROM (SELECT card_id, sum(prior_dollars + current_dollars) d, sum(prior_count + current_count) n FROM npg GROUP BY 1) x
              JOIN (SELECT card_id, sum(amount) d, count(*) n FROM nrw WHERE row_kind = 'award' GROUP BY 1) y USING (card_id)
            WHERE abs(x.d - y.d) >= 0.01 OR x.n <> y.n)
           + (SELECT count(*) FROM (SELECT card_id, count(*) n FROM nor GROUP BY 1) WHERE n > 10), true
    UNION ALL SELECT 'desk natorg: chart series = card values (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM nse JOIN nc USING (card_id) WHERE nse.panel = 'fiscal_year'
              AND abs(nse.value - CASE WHEN nse.entity = 'group' AND nse.year_role = 'prior' THEN nc.group_prior
                                       WHEN nse.entity = 'group' THEN nc.group_current
                                       WHEN nse.year_role = 'prior' THEN nc.rest_prior ELSE nc.rest_current END) >= 0.01), true
    UNION ALL SELECT 'desk natorg: fixed line and OJP gap note on every card (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM nc WHERE fixed_line NOT ILIKE '%improper%' OR NOT list_contains(caveat_keys, 'ojp_gap')), true
    UNION ALL SELECT 'desk natorg (DOJ): FY2025 dollars $299.9M -> $38.6M vs $4,336.4M -> $2,632.0M, status card (spec 4.9)', 2025, NULL, 1,
           (SELECT count(*) FROM nc WHERE fiscal_year = 2025 AND measure = 'dollars' AND status = 'card'
              AND round(group_prior / 1e6, 1) = 299.9 AND round(group_current / 1e6, 1) = 38.6
              AND round(rest_prior / 1e6, 1) = 4336.4 AND round(rest_current / 1e6, 1) = 2632.0
              AND headline = 'National organizations: new DOJ grant dollars fell 87% in FY2025, compared with a 39% fall for all other grant recipients.'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk natorg (DOJ): award-cycle evidence $283.1M -> $35.5M; counts 162 -> 30 and cycle 152 -> 44 (spec 4.9)', 2025, NULL, 4,
           (SELECT count(*) FROM nsc WHERE fiscal_year = 2025 AND (
                (measure = 'dollars' AND basis = 'cycle' AND round(group_prior / 1e6, 1) = 283.1 AND round(group_current / 1e6, 1) = 35.5)
             OR (measure = 'count' AND basis = 'fy' AND group_prior = 162 AND group_current = 30)
             OR (measure = 'count' AND basis = 'cycle' AND group_prior = 152 AND group_current = 44)
             OR (measure = 'dollars' AND basis = 'fy' AND round(100 * (rest_current / rest_prior - 1)) = -39))), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT '"anomal" never appears in Card 2 or national-organizations reader text (rows)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s WHERE headline ILIKE '%anomal%' OR concentration_line ILIKE '%anomal%')
           + (SELECT count(*) FROM c2txt WHERE text ILIKE '%anomal%')
           + (SELECT count(*) FROM nc WHERE headline ILIKE '%anomal%' OR why_text ILIKE '%anomal%')
           + (SELECT count(*) FROM ncv WHERE text ILIKE '%anomal%'), true
    -- ---------------------------------------------------------------- Card 3
    UNION ALL SELECT 'desk card3: DOJ-scope FY totals = all new grants (independent: new-award table; mismatching FYs)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT year, max(scope_total) t FROM c3m WHERE scope = 'doj' AND basis = 'fy' GROUP BY 1) m
              LEFT JOIN (SELECT new_award_fy fy, sum(new_award_amount) t FROM v2an WHERE definition = 'awarding' GROUP BY 1) a ON a.fy = m.year
            WHERE a.t IS NULL OR abs(a.t - m.t) >= 0.01), true
    UNION ALL SELECT 'desk card3: display shares sum to 1 and trigger shares (excl. SCAAP) sum to 1 per scope x basis x year (bad groups)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT scope, basis, year, sum(display_share) d, sum(trigger_share) t FROM c3m GROUP BY ALL)
            WHERE abs(d - 1) > 1e-9 OR abs(t - 1) > 1e-9), true
    UNION ALL SELECT 'desk card3: SCAAP never carries a trigger share; never a card category (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM c3m WHERE is_scaap_segment AND trigger_share IS NOT NULL) + (SELECT count(*) FROM c3c WHERE category = 'SCAAP'), true
    UNION ALL SELECT 'desk card3: every scheme listing present; office derived by rule (rows without an office)', NULL, NULL, 0,
           (SELECT count(*) FROM c3k WHERE office_rule IS NULL AND new_award_amount_fy_window IS NOT NULL), true
    UNION ALL SELECT 'desk card3 (DOJ): office rule differs from the scheme only for 16.018 and 16.684 (-> OJP)', NULL, NULL, 2,
           (SELECT count(*) FROM c3k WHERE NOT office_matches AND listing IN ('16.018', '16.684') AND office_rule = 'OJP')
           + 100 * (SELECT count(*) FROM c3k WHERE NOT office_matches AND listing NOT IN ('16.018', '16.684')), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3 (DOJ): OJP FY2017-25 new-award amount $33,588M; VOCA formula $16,476M (spec 3.2)', NULL, NULL, 33588016476,
           (SELECT CAST(round(sum(amount) / 1e6) AS BIGINT) * 1000000 + CAST(round(sum(voca_formula_amount) / 1e6) AS BIGINT) FROM c3p WHERE scope = 'ojp'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3 (DOJ): spec 3.2 table cells, OJP scope (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM spec_c3_32 x LEFT JOIN c3p p ON p.scope = 'ojp' AND p.period = x.period AND p.segment = x.segment
            WHERE round(p.amount / 1e6) IS DISTINCT FROM x.m), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3 (DOJ): calibration FY2018-24 candidates / confirmed (spec 3.3; mismatching years)', NULL, NULL, 0,
           (SELECT count(*) FROM spec_c3_cal x LEFT JOIN (SELECT fiscal_year, count(*) n, count(*) FILTER (WHERE list_contains(flags, 'confirmed')) cf
                                                            FROM c3c GROUP BY 1) c ON c.fiscal_year = x.fy
            WHERE coalesce(c.n, 0) <> x.n OR coalesce(c.cf, 0) <> x.conf), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3 (DOJ): FY2025 = 5 candidates; earmarks / victim / research label, policing / youth hold (spec 3.5)', 2025, NULL, 5,
           (SELECT count(*) FROM c3c WHERE fiscal_year = 2025 AND (
                (category = 'Congressionally directed and other' AND status = 'label' AND list_contains(labels, 'earmarks'))
             OR (category = 'Crime victim services' AND status = 'label' AND list_contains(labels, 'cvf_cap') AND list_contains(labels, 'ojp_gap'))
             OR (category = 'Research, statistics and forensics' AND status = 'label')
             OR (category IN ('Policing and law enforcement', 'Youth, children and juvenile justice') AND status = 'hold')))
           + 100 * (SELECT count(*) FROM c3c WHERE fiscal_year = 2025 AND category NOT IN ('Congressionally directed and other', 'Crime victim services',
                     'Research, statistics and forensics', 'Policing and law enforcement', 'Youth, children and juvenile justice')), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3 (DOJ): FY2026 = 8 label cards with the gap caveat; late share floor 92% (spec 3.5)', 2026, NULL, 8,
           (SELECT count(*) FROM c3c WHERE fiscal_year = 2026 AND status = 'label' AND list_contains(caveat_keys, 'gap_year') AND late_cycle_pct_floor = 92)
           + 100 * (SELECT count(*) FROM c3c WHERE fiscal_year = 2026 AND status <> 'label'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3 (DOJ): denominator f = 57% (FY2025 victim, OJP), 55% (FY2026 research), 58% (FY2026 youth) (spec 3.3/3.5)', NULL, NULL, 3,
           (SELECT count(*) FROM c3s WHERE (fiscal_year, category, scope, round(100 * denominator_f)) IN
              ((2025, 'Crime victim services', 'ojp', 57), (2026, 'Research, statistics and forensics', 'ojp', 55), (2026, 'Youth, children and juvenile justice', 'ojp', 58))), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card3: denominator label exactly when f >= minimum and f > 0, headline scope (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c WHERE list_contains(labels, 'denominator') <> coalesce(denominator_f >= 0.5 AND denominator_f > 0, false)), true
    UNION ALL SELECT 'desk card3: fixed line on every card; gap caveat on gap-year cards; OJP sentence on later non-gap cards (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c WHERE fixed_line NOT ILIKE '%improper%'
              OR (like_period AND NOT list_contains(caveat_keys, 'gap_year'))
              OR (NOT like_period AND list_contains(labels, 'ojp_gap') AND NOT list_contains(caveat_keys, 'ojp_gap'))), true
    UNION ALL SELECT 'desk card3: timing? cards are held; gap-year cards follow gap_year_status (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c WHERE list_contains(flags, 'timing?') AND status <> 'hold'), true
    UNION ALL SELECT 'desk card3: listing table sums to the headline-scope amounts (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c JOIN (SELECT card_id, sum(prior_amount) p, sum(current_amount) c FROM c3l WHERE NOT is_scaap GROUP BY 1) l USING (card_id)
            WHERE abs(l.p - c3c.amount_prior) >= 0.01 OR abs(l.c - c3c.amount_current) >= 0.01), true
    UNION ALL SELECT 'desk card3: CSV rows in the headline scope add up to the card amounts (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c JOIN (SELECT r.card_id, c.headline_scope,
                    sum(r.amount) FILTER (WHERE NOT r.is_scaap AND r.year_role = 'prior' AND CASE c.headline_scope WHEN 'doj' THEN true WHEN 'ojp' THEN r.in_ojp_scope ELSE r.in_ojp_excl_voca_scope END) p,
                    sum(r.amount) FILTER (WHERE NOT r.is_scaap AND r.year_role = 'current' AND CASE c.headline_scope WHEN 'doj' THEN true WHEN 'ojp' THEN r.in_ojp_scope ELSE r.in_ojp_excl_voca_scope END) c
                FROM c3r r JOIN c3c c USING (card_id) GROUP BY 1, 2) x USING (card_id)
            WHERE abs(coalesce(x.p, 0) - c3c.amount_prior) >= 0.01 OR abs(coalesce(x.c, 0) - c3c.amount_current) >= 0.01), true
    UNION ALL SELECT 'desk card3 (DOJ): cvf_cap FY2024 $1.353B and FY2025 $1.900B in seed and caveat', NULL, NULL, 3,
           (SELECT count(*) FROM c3cap WHERE (fiscal_year = 2024 AND cap = 1353000000) OR (fiscal_year = 2025 AND cap = 1900000000))
           + (SELECT count(*) FROM c3v WHERE caveat_key = 'cvf_cap' AND text LIKE '%$1.353 billion in FY2024, $1.900 billion in FY2025%'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT '"anomal" never appears in Card 3 reader text (rows)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c WHERE headline ILIKE '%anomal%' OR second_line ILIKE '%anomal%') + (SELECT count(*) FROM c3v WHERE text ILIKE '%anomal%'), true
    UNION ALL SELECT 'desk card2 (DOJ): why_text range 10% (FY2024) to 25% (FY2018); FY2026 (provisional) is 27% (2.3)', 2026, NULL, 1,
           (SELECT count(*) FROM c2s WHERE fiscal_year = 2026 AND why_text LIKE '%ranged from 10% (FY2024) to 25% (FY2018). FY2026 (provisional) is 27%.'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card2: every set-aside and organization-type row has a plain-English label (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM c2t WHERE category_label IS NULL), true
    UNION ALL SELECT 'desk card4 (DOJ): contractor-address cell share on the card''s new-award dollars WV 42 AL25 27 AL26 55 AK 28 CO 86 NV 98', NULL, NULL, 6,
           (SELECT count(*) FROM cd WHERE (state, fiscal_year, CAST(round(100 * contractor_address_share) AS INTEGER)) IN
              (('WV', 2026, 42), ('AL', 2025, 27), ('AL', 2026, 55), ('AK', 2026, 28), ('CO', 2026, 86), ('NV', 2026, 98))), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card4: contractor-address caveat quotes the new-award cell and base shares (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM cd JOIN cv ON cv.card_id = cd.card_id AND cv.caveat_key = 'contractor_address'
            WHERE position(CAST(CAST(round(100 * contractor_address_share) AS INTEGER) AS VARCHAR) || '% of these' IN cv.text) = 0
               OR position('(' || CAST(CAST(round(100 * contractor_address_base) AS INTEGER) AS VARCHAR) || '% across' IN cv.text) = 0), true
    UNION ALL SELECT 'desk card4: overridden cards carry a decision reason code, not manual_override; card_type state_stand_out (violations)', NULL, NULL, 0,
           (SELECT count(*) FROM cd WHERE list_contains(status_reasons, 'manual_override') OR card_type <> 'state_stand_out'), true
    UNION ALL SELECT 'desk card4 (DOJ): VA FY2026 label is the corrected sentence (spec 4.7)', 2026, NULL, 1,
           (SELECT count(*) FROM cd WHERE card_id = 'card4-015-2026-VA-assistance-dollars' AND label_text LIKE 'Most of the change is one $43.0 million award to the National Center for Missing & Exploited Children (16.543), made on Dec 5, 2025%'), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card2: fixed line on every card (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM c2s WHERE fixed_line NOT ILIKE '%improper%') + (1 - (SELECT count(*) FROM c2txt WHERE key = 'fixed_line')), true
    UNION ALL SELECT 'desk card3: card shares exclude SCAAP from the total (cards where share <> trigger share)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c WHERE share_prior <> trigger_share_prior OR share_current <> trigger_share_current), true
    UNION ALL SELECT 'desk card3: gap-year headlines name the October-to-cut-off prior period (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM c3c WHERE like_period AND headline NOT LIKE '%(October–%)%.'), true
    -- ---------------------------------------------------------------- public subset (desk/public/; held means not public)
    UNION ALL SELECT 'desk public: every public card_id is in the sign-off file (missing)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT DISTINCT card_id FROM (SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_cards.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_caveats.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_components.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_programs.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_recipients.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_series.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_cards.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_caveats.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_components.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_organizations.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_programs.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_series.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cards.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_caveats.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_listings.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_summary.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_reasons.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_recipient_types.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_top_awards.parquet'))) WHERE card_id NOT IN (SELECT card_id FROM signoffs)), true
    UNION ALL SELECT 'desk public: no held or suppressed card_id in any public file (rows)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_cards.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_caveats.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_components.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_programs.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_recipients.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_series.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_cards.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_caveats.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_components.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_organizations.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_programs.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_series.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cards.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_caveats.parquet') UNION ALL SELECT card_id FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_listings.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_summary.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_reasons.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_recipient_types.parquet') UNION ALL SELECT 'card2-' || getvariable('agency') || '-' || fiscal_year FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_top_awards.parquet')) WHERE card_id IN (SELECT card_id FROM heldids)), true
    UNION ALL SELECT 'desk public: no text unique to a held card in any public file (matches)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT headline AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_summary.parquet') UNION ALL SELECT why_text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_summary.parquet') UNION ALL SELECT concentration_line AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_summary.parquet') UNION ALL SELECT text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_text.parquet') UNION ALL SELECT headline AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cards.parquet') UNION ALL SELECT second_line AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cards.parquet') UNION ALL SELECT label_text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cards.parquet') UNION ALL SELECT text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_caveats.parquet') UNION ALL SELECT template AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_text.parquet') UNION ALL SELECT headline AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_cards.parquet') UNION ALL SELECT label_text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_cards.parquet') UNION ALL SELECT why_text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_cards.parquet') UNION ALL SELECT text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_caveats.parquet') UNION ALL SELECT template AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_text.parquet') UNION ALL SELECT headline AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_cards.parquet') UNION ALL SELECT why_text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_cards.parquet') UNION ALL SELECT text AS x FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_caveats.parquet')) p JOIN heldonly h ON p.x = h.x OR (length(h.x) > 40 AND position(h.x IN p.x) > 0)), true
    UNION ALL SELECT 'desk public: row counts = full marts filtered to published cards (mismatching tables)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT 'card2_reasons' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_reasons.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card2_reasons.parquet') WHERE ('card2-' || getvariable('agency') || '-' || fiscal_year) IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card2_recipient_types' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_recipient_types.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card2_recipient_types.parquet') WHERE ('card2-' || getvariable('agency') || '-' || fiscal_year) IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card2_summary' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_summary.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card2_summary.parquet') WHERE ('card2-' || getvariable('agency') || '-' || fiscal_year) IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card2_text' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_text.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card2_text.parquet') WHERE true) AS n_full UNION ALL SELECT 'card2_top_awards' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card2_top_awards.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card2_top_awards.parquet') WHERE ('card2-' || getvariable('agency') || '-' || fiscal_year) IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card3_cards' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cards.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cards.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card3_categories' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_categories.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_categories.parquet') WHERE true) AS n_full UNION ALL SELECT 'card3_caveats' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_caveats.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_caveats.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card3_cvf_cap' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_cvf_cap.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_cvf_cap.parquet') WHERE true) AS n_full UNION ALL SELECT 'card3_listings' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_listings.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_listings.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card3_mix' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_mix.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_mix.parquet') WHERE true) AS n_full UNION ALL SELECT 'card3_periods' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_periods.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_periods.parquet') WHERE true) AS n_full UNION ALL SELECT 'card3_text' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card3_text.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card3_text.parquet') WHERE true) AS n_full UNION ALL SELECT 'card4_cards' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_cards.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_cards.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card4_caveats' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_caveats.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_caveats.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card4_components' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_components.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_components.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card4_national_orgs' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_national_orgs.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_national_orgs.parquet') WHERE true) AS n_full UNION ALL SELECT 'card4_params' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_params.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_params.parquet') WHERE true) AS n_full UNION ALL SELECT 'card4_programs' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_programs.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_programs.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card4_recipients' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_recipients.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_recipients.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card4_series' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_series.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_series.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'card4_text' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/card4_text.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/card4_text.parquet') WHERE true) AS n_full UNION ALL SELECT 'natorg_cards' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_cards.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_cards.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'natorg_caveats' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_caveats.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_caveats.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'natorg_components' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_components.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_components.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'natorg_organizations' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_organizations.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_organizations.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'natorg_programs' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_programs.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_programs.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full UNION ALL SELECT 'natorg_series' AS t, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/public/natorg_series.parquet')) AS n_pub, (SELECT count(*) FROM read_parquet(getvariable('marts_dir') || '/desk/natorg_series.parquet') WHERE card_id IN (SELECT card_id FROM pubids)) AS n_full) WHERE n_pub <> n_full), true
    UNION ALL SELECT 'desk public: manifest lists only desk/public/ Parquet files, all of them (mismatches)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT unnest(p) AS f FROM manifest_pq) WHERE f NOT LIKE 'desk/public/%')
           + abs((SELECT count(*) FROM (SELECT unnest(p) FROM manifest_pq)) - 28), true
    UNION ALL SELECT 'desk public: deployed manifest.json names no held or suppressed card id, status or CSV path (matches)', NULL, NULL, 0,
           (SELECT count(*) FROM (SELECT content FROM read_text(getvariable('marts_dir') || '/desk/manifest.json')) m, heldids h
            WHERE position('"' || h.card_id || '"' IN m.content) > 0 OR position(h.card_id || '.csv' IN m.content) > 0)
           + (SELECT count(*) FROM (SELECT content FROM read_text(getvariable('marts_dir') || '/desk/manifest.json'))
              WHERE content LIKE '%"status": "hold"%' OR content LIKE '%"status": "suppressed"%' OR content LIKE '%"status": "evidence"%'), true
    UNION ALL SELECT 'desk public: manifest.json lists exactly the published cards; manifest_internal.json lists every card (mismatches)', NULL, NULL, 0,
           abs((SELECT count(*) FROM (SELECT unnest(list_concat(card_types.state_stand_out.cards, card_types.national_organizations.cards,
                     card_types.grant_categories.cards, card_types.contracts_without_competition.cards)) FROM read_json(getvariable('marts_dir') || '/desk/manifest.json')))
               - (SELECT count(*) FROM pubids))
           + abs((SELECT count(*) FROM (SELECT unnest(list_concat(card_types.state_stand_out.cards, card_types.national_organizations.cards,
                     card_types.grant_categories.cards, card_types.contracts_without_competition.cards)) FROM read_json(getvariable('marts_dir') || '/desk/manifest_internal.json')))
               - (SELECT count(*) FROM allcards)), true
    UNION ALL SELECT 'desk public (DOJ): 44 published cards (9 card4, 1 natorg, 24 card3, 10 card2)', NULL, NULL, 44,
           (SELECT count(*) FROM pubids), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card4 (DOJ): 10 raw candidates, as the prototype (spec 4.7)', NULL, NULL, 10,
           (SELECT count(*) FROM sc WHERE is_candidate), true
           WHERE getvariable('agency') = '015'
    UNION ALL SELECT 'desk card4 (DOJ): cards by status card/label/suppressed = 2/7/1 (spec 4.7)', NULL, NULL, 271,
           (SELECT 100 * count(*) FILTER (WHERE status = 'card') + 10 * count(*) FILTER (WHERE status = 'label')
                   + count(*) FILTER (WHERE status = 'suppressed') FROM cd), true
           WHERE getvariable('agency') = '015'
)
SELECT check_name, fiscal_year, definition, expected, actual, actual - expected AS diff,
       CASE WHEN actual IS NULL AND expected IS NULL THEN 'PASS'
            WHEN actual IS NULL OR expected IS NULL THEN 'FAIL'
            WHEN is_count AND actual = expected THEN 'PASS'
            WHEN NOT is_count AND abs(actual - expected) < 0.01 THEN 'PASS'
            ELSE 'FAIL' END AS status
FROM checks ORDER BY status, check_name, fiscal_year;
