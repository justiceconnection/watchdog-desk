## Appendix C: Reader text for the methods page

<!-- Convention (not reader text): everything in this appendix outside HTML comments is reader-ready and is used verbatim on the methods page ("How the cards work"), headings included. HTML comments (like this one) are maintainer notes and are stripped at build time, never shown. Each paragraph, list or table is followed by a comment naming its source in the card methods rules and, where relevant, the mart parameter it restates. Values are for DOJ (agency 015) as of the 2026-10-16 marts; if a parameter in card2_params, card3_params or card4_params changes, this appendix must be updated in the same change. Status: VERIFIED 2026-10-17; every number was checked against the params marts. -->

### How the cards work

The Watchdog Desk shows four kinds of card. Each one compares DOJ's new awards across places, groups or years and describes what changed. None of them says why, and none indicates anything improper.

- **States that stand out.** A state where new DOJ grants or contracts changed very differently from the rest of the country in the same year.
- **National organizations.** Grants to nonprofit and private organizations that work nationally, compared with grants to everyone else. They get their own card because where they are based says little about where the money is used.
- **Contracts awarded without competition.** The share of DOJ's new contracts, above the small-purchase threshold, that were awarded without competition, year by year.
- **Grant categories.** A category of DOJ grants (for example, crime victim services) whose share of DOJ's new grant dollars rose or fell sharply.

All four cards count **new awards**: the amount committed when a grant or contract is first made, not later changes and not money actually spent. Years are federal fiscal years (October to September), by the date of the award. The current fiscal year is incomplete and is marked as such.

<!-- Source: card methods rules (all four card types); metrics 7.7 (new awards, initial award amount; awarding agency). "Not later changes and not money actually spent" = not net obligations, not outlays. -->

### States that stand out

**The comparison.** For each state we compare the change in its new DOJ awards from one year to the next with the change for the rest of the country (all other states together) over the same years. Grants and contracts are compared separately, by dollars and by number of awards. A contract counts only if it is worth more than $10,000. Washington, DC is left out of these comparisons, as are the national organizations described below.

<!-- Source: card methods rules, states that stand out: unit (DC excluded, national organizations excluded from grants, contracts over $10,000) and triggers. Params: contract_min_amount 10000, excluded_states DC. -->

**When a state is picked.** A state gets a card when either of these is true:

- **It moved the opposite way.** The state rose by 50% or more, or fell by a third or more, while the rest of the country moved at least about 10% in the other direction.
- **It is far outside the usual range.** We measure how far each state's change differs from the rest of the country's, then compare that gap with how much the gaps typically vary from state to state that year. A state is picked when its gap is at least 3 times the typical variation. So that a quiet year doesn't make small differences look large, the typical variation is never taken as less than a 25% difference. At least 5 states must pass the size floor below for this test to run.

<!-- Source: card methods rules, states that stand out: triggers and the robust z. Params: opp_min = ln(1.5) (+50% / -33.3%), nat_min = ln(1.1) ("about 10%": +10% or -9.1%), z_far 3.0, s_min = ln(1.25) (floor on 1.4826*MAD), min_states 5. "Typical variation" = scaled median absolute deviation of the gaps around their median. -->

**Size floors.** Small numbers swing a lot, so a state is considered only if:

- its larger year had at least $10 million in new awards (for a dollar comparison) or 25 awards (for a count comparison);
- its change differs from what it would have been at the rest of the country's rate by at least $5 million, or 15 awards;
- for a count comparison, its dollar total also changed by at least $1 million.

To keep very small starting amounts from producing huge percentages, the comparison adds $5 million (or 10 awards) to both years before measuring the change. The percentages shown in headlines are the plain, unadjusted changes. When a state's earlier year is below the size floor, the headline gives the two dollar totals instead of a percentage.

<!-- Source: card methods rules, states that stand out: floors and damping c; caveat on a small prior base (percentages undamped). Params: size_dollars 10000000, size_counts 25 (applied to the larger of the two years, per measure), excess_dollars 5000000, excess_counts 15 (excess = current - prior x rest-of-country ratio), count_card_min_dollar_change 1000000, c_dollars 5000000, c_counts 10. Items failing the $1M rule are not published (status suppressed). -->

**Timing check.** Grants are often made months after the fiscal year they are funded from, so a fall in one year can simply be awards arriving late. For a complete year, a grant result must also show up when awards are grouped by the funding year they belong to (counted to the same point in each year): same direction, and at least 2 times the typical variation. Results that don't pass are held, not published. For the current fiscal year, grant data runs only through July 31, 2026, so we compare October–July with October–July of the year before, and every such card says that some of the change may be award timing. Current-year contract data is provisional through September 30, 2026.

<!-- Source: card methods rules, states that stand out: funding-year check; status (timing? = hold; gap_year = label); FY2026 grant gap caveat. Params: cycle_confirm_z 2.0, gap_year_grant_status label. "Funding year" = award cycle (metrics 7.7, award cycle; like-elapsed). FY2027 is never scored (funding-year check rule); not stated to readers because no FY2027 data is shown. -->

**What a card adds.** If one award, or one recipient, accounts for 60% or more of a state's change, the card names it. If 25% or more of a state's grant dollars went to state government agencies, the card notes that much of that money is usually passed on to local governments and organizations, and gives the reported sub-award total as a minimum. For contracts, the card counts contractors based in the state and shows how much of the work is recorded as performed there. When an unusually large share of the dollars lists the contractor's own address as the place of work (at least 39 percentage points above the DOJ-wide share that year, up to 95%), the headline says "contractors based in" the state. This test uses all contract dollars recorded that year, including changes to earlier contracts; the shares printed on the card use new-award dollars only. Grant cards from FY2025 on also say how many of OJP's own listed awards for the state are not yet in USAspending.

<!-- Source: card methods rules, states that stand out: flags (one_award / one_recipient >= 60%; contractor_address) and caveats (pass-through >= 25%, contractor address caveat, OJP gap note). Params: concentration_share 0.6, pass_through_min_share 0.25, ca_margin 0.39, ca_cap 0.95, ojp_gap_year 2025. The 39-point test uses the trend-signals base (absolute contract dollars, all actions, in the target year), while the caveat's printed shares use new-award dollars (caveat rule); the reader sentence now states both (2026-10-17). -->

### National organizations

Some grant recipients are nonprofit or private organizations that work nationally: technical-assistance providers, research organizations, and federations with local affiliates. Where their grants are recorded depends on where the organization is headquartered, not where the money is used. Mixed into the state comparisons, they made Washington, DC look like a state outlier, so they are compared as one group instead.

A recipient is on the list if the type most often recorded on its DOJ awards is a nonprofit, a business or another non-government organization, and either:

- **Headquartered in DC:** the location most often recorded on its DOJ awards is Washington, DC; or
- **DOJ-funded sub-awards reach 5 or more states:** since FY2017, it has passed DOJ grant money on to sub-recipients in 5 or more states.

When a recipient's records are evenly split, it counts as non-government only if every one of the tied types is non-government, and as DC-based only if every tied location is DC. This keeps out government agencies that are sometimes recorded as non-government. DC government agencies that are not national organizations are left out of both the state cards and this card.

<!-- Source: card methods rules, national organizations: Why, Rule (modal business type in M N Q R X; (a) modal state DC, (b) >= 5 distinct sub-award states, FY2017+), Mode ties (W1), Excluded from both cards. Params: natorg_nongov_types "M N Q R X", natorg_hq_state DC, natorg_min_sub_states 5, natorg_rule a_or_b. The two bold labels are exactly the frontend's existing basis labels. "Most often recorded" = the unique mode (ties per W1). -->

**When the card appears.** We compare the group's change in new grants with the change for all other grant recipients, the same way as for states. The card appears when the two changes differ by a factor of 1.5 or more (for example, the group's grants falling by half while everyone else's fell by a quarter), and the difference amounts to at least $5 million or 15 awards. The same timing check by funding year is shown as supporting evidence.

<!-- Source: card methods rules, national organizations: Comparison (|r_group - r_rest| >= ln 1.5; excess >= $5M or 15 awards; cycle as evidence). Params: natorg_gap_min = ln(1.5), excess_dollars, excess_counts. Example check: ln(0.5/0.75) = -ln 1.5. -->

### Contracts awarded without competition

**What counts.** Each new contract is recorded with how it was competed. We count a contract as **awarded without competition** when it is marked:

- **not available for competition** (for example, a source required by law or by an international agreement);
- **not competed**; or
- **a non-competitive order** under an existing contract.

We count it as **competed** when it is marked full and open competition, full and open competition after some sources were excluded (for example, a small-business set-aside), a competitive order under an existing contract, or **a follow-on to an earlier competed contract**. That last group is counted as competed because the government's standard competition reporting treats it that way. Contracts with no competition entry are shown separately as "not reported" and left out of the share.

<!-- Source: card methods rules, contracts without competition: Not competed (B, C, NDO), Competed (A, D, E, CDO), E decision, NULL code. Params: not_competed_codes "B C NDO", competed_codes "A D E CDO". Examples in brackets are the FPDS meanings of B and D. -->

**Small purchases are left out.** Small purchases are made under simplified, faster procedures with lighter competition rules, and there are tens of thousands of them a year. Including them would make the share mostly about routine buying. We leave out any contract that is recorded as a simplified-procedure purchase, or whose expected value when awarded (including options) is $250,000 or less, the federal small-purchase threshold. We use $250,000 in every year; the threshold was $150,000 until 2018, so the earliest years leave out slightly more than the rules then required.

<!-- Source: card methods rules, contracts without competition: Small purchases excluded (both tests; F/G, SP1, SP2/MPT; base_and_all_options_value <= $250,000, falling back to the base obligation; $250K in all years), and the "code only" row of the comparison table. Params: sap_threshold 250000, sap_extent_codes, sap_solicitation_codes, sap_justification_codes. -->

**The share.** The share by number is non-competed contracts divided by all contracts that were either competed or not competed. The share by dollars uses each contract's first commitment of money.

<!-- Source: card methods rules, contracts without competition: Share (counts), Share (dollars) (initial award obligations). -->

**Reasons.** Contracting offices give a reason for each contract awarded without competition. The chart groups them into bands: only one responsible source; authorized by law (including sole-source awards to small businesses in the SBA's 8(a) program, which includes Alaska Native corporations); utilities; unusual and compelling urgency; follow-on contract; keeping an essential supplier or research capability available; unique source; and brand name. **Utilities** (mostly power and water for federal prisons, usually from a single local provider) are about a fifth of these contracts, so they are their own band and stay in the share. When one contract is 15% or more of a year's non-competed dollars, the card lists that year's five largest. These codes are recorded by the contracting office and can be wrong; they don't show intent.

<!-- Source: card methods rules, contracts without competition: Stated reason table (ONE, OTH, UT, URG, FOC, MES, UNQ, BND) and utilities decision (1,347 of 6,051 = 22%, FY2017-26); Concentration rule; Explainer and statutory_note. Params: utilities_code UT, concentration_share 0.15, top_awards_n 5. -->

### Grant categories

**The twelve categories.** Every DOJ grant program is placed in one category by its main topic. A program that serves several purposes can't be split, so it goes where most of its purpose lies.

| Category | What it covers |
|---|---|
| Crime victim services | Crime Victims Fund formula grants to states for victim assistance and compensation, and services for trafficking victims, victims of mass violence and terrorism, and other victims |
| Violence against women | Office on Violence Against Women programs: formula grants to states, sexual assault services, legal help, housing, rural and campus programs, protection orders, coalitions and training |
| Policing and law enforcement | COPS hiring and community policing, body-worn cameras, officer safety and wellness, training, information sharing, sex offender registration, and drug, gun and cyber crime enforcement |
| Byrne JAG and flexible justice assistance | Byrne Justice Assistance Grants, which states and localities can use for many justice purposes, other Byrne grants, and the FY2020 COVID-19 emergency funding |
| Corrections and reentry | Reentry programs, substance use treatment in prisons, justice reinvestment, prison rape elimination and community supervision; also the State Criminal Alien Assistance Program, shown separately |
| Youth, children and juvenile justice | Juvenile justice and delinquency prevention, mentoring, missing and exploited children, child abuse investigation and children's advocacy centers, and youth violence and gang prevention |
| Substance use, mental health and treatment courts | Opioid and stimulant programs, prescription drug monitoring, drug, veterans and other treatment courts, and mental health collaboration |
| Courts, prosecution and defense | Support for prosecutors and public defenders, capital case litigation, student loan repayment for prosecutors and defenders, and civil rights cold cases |
| Violence reduction and prevention | Community violence intervention, school violence prevention, Project Safe Neighborhoods and community crime reduction |
| Tribal justice | Programs open only to tribes, whatever their topic: the tribal victim services set-aside, tribal violence-against-women programs, tribal courts and justice systems, and tribal youth |
| Research, statistics and forensics | Research and evaluation, justice statistics, criminal records improvement, and forensic science, including DNA backlog reduction and sexual assault kits |
| Congressionally directed and other | Awards Congress directed to specific recipients (earmarks), and a few small programs with no clear topic |

Programs open only to tribes always go to tribal justice. So crime victim services and violence against women leave out their tribal portions; the cards for those categories say so.

<!-- Source: card methods rules, grant categories: Categories and Precedence (tribal first; then by topic; setting decides); docs/specs/grant-categories.csv (descriptions summarize the subcategory column and the largest listings by new-award amount FY2017-25). Param: tribal_first_categories "Crime victim services|Violence against women". -->

**Three views.** Each card shows the category's share of new grant dollars three ways: across all of DOJ's grant-making offices; within the Office of Justice Programs (OJP); and within OJP leaving out the Crime Victims Fund formula grants to states, which are large and follow a spending cap Congress sets each year.

<!-- Source: card methods rules, grant categories: Unit (scopes: DOJ; OJP; OJP excluding VOCA formula 16.575, 16.576). Param: voca_formula_listings. -->

**When a category is picked.** A category gets a card when, in at least one of the three views, all four of these are true. Increases and decreases both count.

1. **Size:** the category had at least $25 million in new awards in the current year or the year before (whichever is larger).
2. **Dollar change:** its new awards rose or fell by at least $10 million.
3. **Percent change:** they rose or fell by at least 15% of the year before (or the year before was zero).
4. **Share change:** its share of new grant dollars moved by at least 5 percentage points, in the same direction as the dollar change. A category whose share rose only because others fell doesn't count.

<!-- Source: card methods rules, grant categories: test table and "Same direction". Params: size_min 25000000, abs_min 10000000, pct_min 0.15, share_min_pts 5. -->

**Timing check.** The share change must also appear when awards are grouped by the funding year they belong to (counted to the same point in each year): in the same direction and at least half as large. Candidates that don't pass are held, not published. For the current fiscal year, grant data runs only through July 31, 2026, and the check can't be done yet; those cards compare October–July in both years and say that the shares mostly reflect award timing.

<!-- Source: card methods rules, grant categories: Timing check (confirmed: same sign, >= half; otherwise hold) and Status; FY2026 (not applicable in the gap year; publish with gap_year and caveat_gap_share); caveat on award timing. Param: timing_min_ratio 0.5, gap_year_status label. -->

**SCAAP.** The State Criminal Alien Assistance Program reimburses state and local jail costs and was paid only in FY2022–23, for two earlier years. It is left out of every number on these cards, including shares and totals, and drawn separately on the chart.

<!-- Source: card methods rules, grant categories: SCAAP (left out of every card number, W7); chart footnote; category mix. Param: scaap_listing 16.606. Wording deliberately does not say "hatched" or "dotted": the chart now draws it dotted above 100% (matching the note_scaap_shares wording). -->

**When the total moved.** A category's share can change because its own dollars changed or because the total for all categories changed. When half or more of the share change comes from the total moving, the card says so and gives the share the category would have had at the previous year's total.

<!-- Source: card methods rules, grant categories: denominator label (f >= 0.5; never when f <= 0; the card still publishes). Param: denominator_min_f 0.5. -->

**Notes added in specific cases.** On a congressionally directed card where earmarks make up half or more of the change, the card notes that these awards depend on whether that year's appropriations act included them. On a crime victim services card where the Crime Victims Fund formula grants make up half or more of the change, the card gives the cap Congress set in each year. On a Byrne JAG card for FY2020–21 where COVID-19 emergency funding makes up half or more of the change, the card says so. If one award makes up 60% or more of the change, the card names it. Cards for FY2025 or later note that OJP's own award list includes awards that aren't in USAspending yet, so every category's share may change when they are reported.

<!-- Source: card methods rules, grant categories: Labels (earmarks: 16.753 >= 50% of change; cvf_cap: VOCA formula >= 50%; covid: 16.034 >= 50%, FY2020-21; ojp_gap FY2025+, replaced by caveat_gap_share in FY2026), Drivers (one-award 60%). Params: label_min_share 0.5, earmark_listings 16.753, covid_listings 16.034, covid_years "2020 2021", one_award_share 0.6. -->

### Settings

These are the settings behind the cards, in plain terms.

| Setting | Value |
|---|---|
| **States that stand out** | |
| Contracts counted | worth more than $10,000 |
| Left out of state comparisons | Washington, DC, and national organizations (grants) |
| "Opposite direction": state's change | up 50% or more, or down a third or more |
| "Opposite direction": rest of the country's change | at least about 10% the other way |
| "Far outside the usual range" | at least 3 times the typical variation between states |
| Smallest typical variation used | a 25% difference |
| States needed to run the comparison | at least 5 |
| Size floor (larger of the two years) | $10 million, or 25 awards |
| Difference from the rest-of-country rate | at least $5 million, or 15 awards |
| Count comparisons: dollar change needed | at least $1 million |
| Smoothing added to both years | $5 million, or 10 awards |
| Timing check (complete years, grants) | same direction and at least 2 times the typical variation |
| "Most states" range in the explanation | between the 10th and 90th percentiles of states |
| Naming one award or recipient | 60% or more of the change |
| State-agency pass-through note | 25% or more of the grant dollars |
| "Contractors based in" wording | contractor's own address is the place of work for at least 39 percentage points more of the dollars than DOJ-wide, up to 95% |
| Recipients listed on each card | top 5 |
| OJP missing-awards note | grant cards from FY2025 on |
| **National organizations** | |
| Membership | non-government, and headquartered in DC or with sub-awards in 5 or more states |
| Card appears when changes differ by | a factor of 1.5 or more, and at least $5 million or 15 awards |
| Organizations listed on the card | top 10 |
| **Contracts awarded without competition** | |
| Small-purchase threshold | $250,000 expected value, all years |
| Years shown | FY2017 on; organization type from FY2019 |
| Listing the largest contracts | when one contract is 15% or more of a year's non-competed dollars; five listed |
| **Grant categories** | |
| Size | $25 million or more in the larger of the two years |
| Dollar change | $10 million or more, up or down |
| Percent change | 15% or more, up or down |
| Share change | 5 percentage points or more, same direction as dollars |
| Timing check | same direction and at least half as large |
| "Total moved" note | half or more of the share change |
| Earmark, victim fund cap and COVID notes | half or more of the change |
| Naming one award | 60% or more of the change |
| Programs listed as main drivers | top 3 |

<!-- Source: card4_params, card2_params, card3_params (marts/015/desk, read 2026-10-17), mapped row by row in the order above: contract_min_amount; excluded_states + the unit rule; opp_min; nat_min; z_far; s_min; min_states; size_dollars/size_counts; excess_dollars/excess_counts; count_card_min_dollar_change; c_dollars/c_counts; cycle_confirm_z; band_lo_pct/band_hi_pct; concentration_share; pass_through_min_share; ca_margin/ca_cap; top_recipients; ojp_gap_year; natorg_nongov_types/natorg_hq_state/natorg_min_sub_states/natorg_rule; natorg_gap_min + excess; natorg_top_organizations; sap_threshold; first_fy/org_type_first_fy; concentration_share/top_awards_n; size_min; abs_min; pct_min; share_min_pts; timing_min_ratio; denominator_min_f; label_min_share; one_award_share; top_listings.
Not shown to readers (internal, non-numeric or file references): ojp_dashboard_csv, gap_year_grant_status, one_award_status, gap_year_status, categories_csv, ojp_component, covid_category, earmark_category, victim_category, second_line_other_scope_categories, scaap_listing, voca_formula_listings, covid_listings, earmark_listings, covid_years, tribal_first_categories (all described in prose above), and the code lists competed_codes, not_competed_codes, sap_*_codes, utilities_code (described in prose in the Contracts section). Show the plain values above, never the raw parameter values (several are natural logs). -->
