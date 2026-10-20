"""Watchdog Desk, Card 3: grants by Justice Connection category (docs/specs/watchdog-cards.md section 3).

Base: new awards (metrics 7.7; _v2_award_new, definition awarding, assistance), amount = initial award amount,
joined on listing to the category scheme (categories_csv). The build FAILS if any assistance listing on an
agency-awarded transaction from first_fy on has no row in the scheme.
Scopes: doj (all), ojp (component = OJP under metrics 6.2), ojpx (OJP without the VOCA formula listings).
Bases: fy (FY of the new-award date, complete years), like (gap year and the year before, October to the cut-off
month), cycle_le (award cycle, like-elapsed). SCAAP is a separate segment: in display shares, out of trigger shares.
Office per listing is derived by rule (the dominant metrics 6.2 component by absolute new-award dollars), not taken
from the scheme's office column; disagreements are reported in card3_categories.

Parameters, caps and text: sql/seeds/desk_card3_params.csv, cvf_cap.csv, desk_card3_text.csv.
"""
from __future__ import annotations

import csv
from pathlib import Path

from card4 import ROOT, URL, long_date, money


def cap_fmt(v: float) -> str:
    return f"${v / 1e9:,.3f} billion"


def money_m1(v: float) -> str:
    return f"${v / 1e6:,.1f} million"


def money_m(v: float) -> str:
    return f"${v / 1e6:,.0f} million"

SCOPES = ("doj", "ojp", "ojpx")


def _seed(name, agency):
    with open(ROOT / "sql" / "seeds" / name, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["agency_code"] == agency]


def _in(codes):
    return ", ".join(f"'{c}'" for c in codes.split()) or "NULL"


class Card3:
    def __init__(self, c4):
        self.c4, self.con, self.ag = c4, c4.con, c4.ag
        self.P = {r["parameter"]: r["value"] for r in _seed("desk_card3_params.csv", self.ag)}
        if not self.P:
            raise SystemExit(f"no desk_card3_params rows for agency {self.ag}")
        self.text = {r["key"]: r["template"] for r in _seed("desk_card3_text.csv", self.ag)}
        self.caps = {int(r["fy"]): (float(r["cap"]) if r["cap"] else None) for r in _seed("cvf_cap.csv", self.ag)}
        self.f = lambda k: float(self.P[k])

    def T(self, key, **kw):
        return self.text[key].format(**kw)

    # ------------------------------------------------------------ base
    def build(self):
        P, con = self.P, self.con
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _desk_c3_scheme AS
            SELECT listing, program_title, category, subcategory, rationale, office AS office_scheme
            FROM read_csv('{P['categories_csv']}', header = true, all_varchar = true)""")
        missing = [r[0] for r in con.execute(f"""
            SELECT DISTINCT coalesce(program_code, '(none)') FROM prime_transactions
            WHERE agency_code = getvariable('agency') AND awarding_agency_code = agency_code AND award_category = 'assistance'
              AND fiscal_year >= {int(P['first_fy'])}
              AND coalesce(program_code, '(none)') NOT IN (SELECT listing FROM _desk_c3_scheme) ORDER BY 1""").fetchall()]
        if missing:
            raise SystemExit(f"Card 3: {len(missing)} listing(s) have no category in {P['categories_csv']}: {', '.join(missing)}")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _desk_c3 AS
            SELECT a.award_key, a.award_id, a.new_award_date AS new_dt, a.new_award_fy AS fy, a.in_like_period, a.award_cycle,
                   a.like_elapsed_flag, a.component, a.listing, coalesce(s.program_title, a.listing_title) AS program_title,
                   s.category, s.subcategory, a.recipient_name, a.recipient_uei, a.recipient_state_raw AS st, a.new_award_amount AS amt,
                   a.listing = '{P['scaap_listing']}' AS is_scaap,
                   a.component = '{P['ojp_component']}' AS in_ojp,
                   a.component = '{P['ojp_component']}' AND a.listing NOT IN ({_in(P['voca_formula_listings'])}) AS in_ojpx
            FROM _v2_award_new a JOIN _desk_c3_scheme s USING (listing)
            WHERE a.definition = 'awarding' AND a.award_category = 'assistance'""")
        n_unmatched = con.execute("""SELECT count(*) FROM _v2_award_new WHERE definition = 'awarding' AND award_category = 'assistance'
                                     AND listing NOT IN (SELECT listing FROM _desk_c3_scheme)""").fetchone()[0]
        if n_unmatched:
            raise SystemExit(f"Card 3: {n_unmatched} new awards have a listing with no category")
        cov = self.c4.cov
        yrs = sorted(y for (c, y), v in cov.items() if c == "assistance" and not v["partial"])
        self.complete = [y for y in yrs if not cov[("assistance", y)]["prov"] and y >= int(P["first_fy"])]
        self.gap_years = [y for y in yrs if cov[("assistance", y)]["gap"]]
        self.cut = self.c4.cutoff["assistance"]

    def scope_where(self, scope):
        return {"doj": "true", "ojp": "in_ojp", "ojpx": "in_ojpx"}[scope]

    def basis_where(self, basis):
        return {"fy": "true", "like": "in_like_period", "cycle_le": "award_cycle IS NOT NULL AND like_elapsed_flag"}[basis]

    def year_col(self, basis):
        return "award_cycle" if basis == "cycle_le" else "fy"

    def basis_years(self, basis):
        if basis == "fy":
            return self.complete
        if basis == "like":
            return sorted({y for g in self.gap_years for y in (g - 1, g)})
        return self.complete   # cycles through the latest complete FY (the newest cycle has barely started)

    # ------------------------------------------------------------ mix
    def mix(self):
        rows = []
        for scope in SCOPES:
            for basis in ("fy", "like", "cycle_le"):
                ys = self.basis_years(basis)
                if not ys:
                    continue
                yc = self.year_col(basis)
                rows += self.con.execute(f"""
                    WITH b AS (SELECT {yc} AS y, CASE WHEN is_scaap THEN 'SCAAP' ELSE category END AS segment, category, is_scaap, amt
                               FROM _desk_c3 WHERE {self.scope_where(scope)} AND {self.basis_where(basis)} AND {yc} IN ({", ".join(map(str, ys))})),
                         g AS (SELECT y, segment, any_value(category) AS category, bool_or(is_scaap) AS is_scaap, count(*) AS n, sum(amt) AS amt
                               FROM b GROUP BY 1, 2),
                         t AS (SELECT y, sum(amt) AS tot, sum(amt) FILTER (WHERE NOT is_scaap) AS tot_trig FROM g GROUP BY 1),
                         grid AS (SELECT y, segment, category, is_scaap FROM (SELECT DISTINCT y FROM g) CROSS JOIN
                                  (SELECT DISTINCT CASE WHEN is_scaap THEN 'SCAAP' ELSE category END AS segment, category, is_scaap FROM _desk_c3))
                    SELECT '{scope}', '{basis}', grid.y, grid.segment, grid.category, grid.is_scaap, coalesce(g.n, 0), coalesce(g.amt, 0),
                           coalesce(g.amt, 0) / t.tot, CASE WHEN grid.is_scaap THEN NULL ELSE coalesce(g.amt, 0) / t.tot_trig END, t.tot, t.tot_trig
                    FROM grid JOIN t USING (y) LEFT JOIN g USING (y, segment) ORDER BY 3, 4""").fetchall()
        self.mix_rows = rows
        self.mix_idx = {(r[0], r[1], r[2], r[3]): r for r in rows}
        return rows

    # ------------------------------------------------------------ candidates (3.3)
    def run(self):
        P, f = self.P, self.f
        self.mix()
        cats = sorted({r[3] for r in self.mix_rows if not r[5]})
        targets = [("fy", t) for t in self.complete if t - 1 in self.complete] + [("like", g) for g in self.gap_years]
        self.scope_rows, self.cards = [], []
        for basis, t in targets:
            for cat in cats:
                per = {}
                for scope in SCOPES:
                    a = self.mix_idx.get((scope, basis, t, cat))
                    b = self.mix_idx.get((scope, basis, t - 1, cat))
                    if not a or not b:
                        continue
                    amt_t, amt_p, sh_t, sh_p = a[7], b[7], a[9], b[9]
                    d = amt_t - amt_p
                    dsh = 100 * (sh_t - sh_p)
                    tests = dict(size=max(amt_t, amt_p) >= f("size_min"), abs=abs(d) >= f("abs_min"),
                                 pct=(amt_p == 0 or abs(d) >= f("pct_min") * amt_p),
                                 share=abs(dsh) >= f("share_min_pts") and d * dsh > 0)
                    cand = all(tests.values())
                    cyc = None
                    if basis == "fy":
                        ca, cb = self.mix_idx.get((scope, "cycle_le", t, cat)), self.mix_idx.get((scope, "cycle_le", t - 1, cat))
                        if ca and cb:
                            cyc = 100 * (ca[9] - cb[9])
                    confirmed = (cand and cyc is not None and cyc * dsh > 0 and abs(cyc) >= f("timing_min_ratio") * abs(dsh))
                    row = dict(scope=scope, basis=basis, fiscal_year=t, category=cat, amount_prior=amt_p, amount_current=amt_t,
                               change=d, share_prior=sh_p, share_current=sh_t, share_shift_pts=dsh,
                               display_share_prior=b[8], display_share_current=a[8], cycle_share_shift_pts=cyc,
                               pass_size=tests["size"], pass_abs=tests["abs"], pass_pct=tests["pct"], pass_share=tests["share"],
                               is_candidate=cand, timing=("gap_year" if basis == "like" else "confirmed" if confirmed else
                                                          ("timing?" if cand else None)))
                    dn = self.denominator(scope, basis, t, cat)
                    row.update(denominator_f=dn["f"], denominator_s_star=dn["s_star"])
                    per[scope] = row
                    self.scope_rows.append(row)
                cand_scopes = [s for s in SCOPES if s in per and per[s]["is_candidate"]]
                if cand_scopes:
                    self.cards.append(self.make_card(basis, t, cat, per, cand_scopes))
        return self.cards

    def make_card(self, basis, t, cat, per, cand_scopes):
        P, f, ag = self.P, self.f, self.ag
        conf = [s for s in cand_scopes if per[s]["timing"] == "confirmed"]
        gap = basis == "like"
        head = (conf or cand_scopes)[0]
        h = per[head]
        cid = f"card3-{ag}-{t}-" + "".join(ch if ch.isalnum() else "-" for ch in cat.lower()).strip("-").replace("--", "-")
        # label drivers: share of the category's change in the headline scope coming from specific listings
        def listing_change(listings):
            w, yr = self._w(head, basis)
            return self.con.execute(f"""SELECT coalesce(sum(amt) FILTER (WHERE {yr} = ?), 0) - coalesce(sum(amt) FILTER (WHERE {yr} = ?), 0)
                                        FROM _desk_c3 WHERE {w} AND category = ? AND NOT is_scaap AND listing IN ({_in(listings)})""",
                                    [t, t - 1, cat]).fetchone()[0]
        labels, sentences = [], []
        chg = h["change"]
        if cat == P["victim_category"] and chg and listing_change(P["voca_formula_listings"]) / chg >= f("label_min_share"):
            labels.append("cvf_cap")
            cp, ct = self.caps.get(t - 1), self.caps.get(t)
            sentences.append(("cvf_cap", self.T("label_cvf_cap", cap_prior=cap_fmt(cp), cap_t=cap_fmt(ct), t=t, t_prior=t - 1)
                              if cp and ct else self.T("label_cvf_cap_nocap")))
        if cat == P["earmark_category"] and chg and listing_change(P["earmark_listings"]) / chg >= f("label_min_share"):
            labels.append("earmarks")
            sentences.append(("earmarks", self.T("label_earmarks")))
        if (cat == P["covid_category"] and t in [int(y) for y in P["covid_years"].split()] and chg
                and listing_change(P["covid_listings"]) / chg >= f("label_min_share")):
            labels.append("covid")
            sentences.append(("covid", self.T("label_covid")))
        # denominator (3.3): the share moved mostly because the scope's total moved
        dn = self.denominator(head, basis, t, cat)
        if dn["f"] is not None and dn["f"] > 0 and dn["f"] >= f("denominator_min_f"):
            labels.append("denominator")
            T0, T1 = dn["total_prior"], dn["total_current"]
            sentences.append(("denominator", self.T("denominator_note", f_pct=f"{100 * dn['f']:.0f}", scope_owner=self.T(f"scope_label_{head}"),
                                                     rising_falling="rising" if T1 > T0 else "falling", total_prior=money_m(T0),
                                                     total_current=money_m(T1), t_prior=t - 1, category_lower=cat.lower(),
                                                     excl_scaap=" (excluding SCAAP)" if self.scaap_nonzero(head, basis, t) else "",
                                                     category_possessive=cat.lower() + ("'" if cat.lower().endswith("s") else "'s"),
                                                     s_star=f"{100 * dn['s_star']:.1f}")))
        # OJP gap (3.3): agency-wide sentence for FY >= ojp_gap_year, except the gap year, where caveat_gap_share replaces it
        k = late = None
        if self.c4.ojp_missing is not None and t >= self.c4.ojp_year:
            labels.append("ojp_gap")
            if not gap:
                k = self.ojp_missing_total(t)
                sentences.append(("ojp_gap", self.T("caveat_ojp_gap_share", k=f"{k:,}", t=t)))
        if gap:
            k = self.ojp_missing_total(t - 1) if self.c4.ojp_missing is not None else None
            late = self.late_pct(t)
        timing_hold = not gap and not conf
        if timing_hold:
            status = "hold"
        elif gap:
            status = "hold" if P["gap_year_status"] == "hold" else "label"
        else:
            status = "label" if labels else "card"
        flags = (["gap_year"] if gap else ["confirmed" if conf else "timing?"]) + labels
        period = (self.T("period_gap", t=t, cut_month=self.cut.strftime("%B")) if gap else self.T("period_complete", t=t))
        p, q = h["share_current"], h["share_prior"]   # trigger shares: SCAAP out of the total
        headline = self.T("headline", category=cat, p=f"{100 * p:.1f}%", q=f"{100 * q:.1f}%",
                          scope_label=self.T(f"scope_label_{head}"), period=period, up_down="up" if p > q else "down", t_prior=t - 1,
                          prior_period=(f"FY{t - 1} (October–{self.cut.strftime('%B')})" if gap else f"FY{t - 1}"))
        second = self.T("second_line", prior=money_m1(h["amount_prior"]), current=money_m1(h["amount_current"]))
        nxt = [sc for sc in (conf or cand_scopes) if sc != head]
        if nxt and cat in P["second_line_other_scope_categories"].split("|"):
            o = per[nxt[0]]
            second += self.T("second_line_other_scope", scope_name={"doj": "DOJ", "ojp": "OJP", "ojpx": "OJP excluding VOCA formula grants"}[nxt[0]],
                             q=f"{100 * o['share_prior']:.1f}%", p=f"{100 * o['share_current']:.1f}%")
        caveats = list(sentences)
        if gap:
            caveats.append(("gap_year", self.T("caveat_gap_share", t=t, t_prior=t - 1, cut_long=long_date(self.cut),
                                               cut_month=self.cut.strftime("%B"), k=f"{k:,}" if k is not None else "some",
                                               late_pct=late)))
        if cat in P["tribal_first_categories"].split("|"):
            caveats.append(("tribal_first", self.T("caveat_tribal_first")))
        drv = self.drivers(cid, head, basis, t, cat)
        label_text = self.one_award(head, basis, t, cat, chg)
        if label_text:
            flags.append("one_award")   # concentration note (3.4); not a status label (3.3)
        return dict(agency_code=ag, card_id=cid, card_type="grant_categories", fiscal_year=t, prior_year=t - 1, basis=basis,
                    like_period=gap, is_provisional=bool(self.c4.cov[("assistance", t)]["prov"]), period_label=period, category=cat,
                    headline_scope=head, candidate_scopes=cand_scopes, confirmed_scopes=conf,
                    amount_prior=h["amount_prior"], amount_current=h["amount_current"], change=chg,
                    share_prior=q, share_current=p, trigger_share_prior=h["share_prior"], trigger_share_current=h["share_current"],
                    display_share_prior=h["display_share_prior"], display_share_current=h["display_share_current"],
                    share_shift_pts=h["share_shift_pts"], cycle_share_shift_pts=h["cycle_share_shift_pts"],
                    flags=flags, labels=labels, status=status, ojp_missing_awards=k, late_cycle_pct_floor=late,
                    denominator_f=dn["f"], denominator_s_star=dn["s_star"], scope_total_prior=dn["total_prior"],
                    scope_total_current=dn["total_current"],
                    headline=headline, second_line=second, label_text=label_text, fixed_line=self.T("fixed_line"),
                    caveat_keys=[c[0] for c in caveats], caveats=caveats, drivers=drv, csv_path=f"desk/csv/{cid}.csv",
                    method_ref="docs/specs/watchdog-cards.md 3.2-3.7; docs/metrics.md 7.7, 6.2; sql/desk/card3.py",
                    data_as_of=self.c4.data_as_of)

    def denominator(self, scope, basis, t, cat):
        a, b = self.mix_idx.get((scope, basis, t, cat)), self.mix_idx.get((scope, basis, t - 1, cat))
        # trigger basis (SCAAP out of the total), consistent with the share-shift test
        s0, s1, A1, T0, T1 = b[9], a[9], a[7], b[11], a[11]
        s_star = A1 / T0 if T0 else None
        fv = (s1 - s_star) / (s1 - s0) if s_star is not None and s1 != s0 else None
        return dict(f=fv, s_star=s_star, total_prior=T0, total_current=T1)

    def scaap_nonzero(self, scope, basis, t):
        """The scope total excludes a non-zero SCAAP amount in t or t-1."""
        return any((self.mix_idx.get((scope, basis, y, "SCAAP")) or (0,) * 8)[7] for y in (t - 1, t))

    def late_pct(self, t):
        """Lower of the two like periods' late-cycle dollar shares (award cycle earlier than the FY of the award), rounded down (3.5).
        Reproduces the spec's 97.5% / 92.4% (DOJ, Oct-Jul FY2025 / FY2026)."""
        r = self.con.execute(f"""SELECT fy, sum(amt) FILTER (WHERE award_cycle < fy) / sum(amt) FROM _desk_c3
                                 WHERE in_like_period AND fy IN ({t - 1}, {t}) GROUP BY 1""").fetchall()
        self.late_shares = dict(r)
        import math
        return math.floor(100 * min(v for _, v in r))

    def _w(self, scope, basis):
        return f"{self.scope_where(scope)} AND {self.basis_where(basis)}", self.year_col(basis)

    def ojp_missing_total(self, t):
        yy = f"{t % 100:02d}"
        return self.con.execute(f"""
            WITH d AS (SELECT replace("Award Number", '-', '') AS fain,
                              regexp_extract("NOFO Title", 'FY ?(20)?(\\d\\d)([^0-9]|$)', 2) AS yy
                       FROM read_csv('{self.c4.P['ojp_dashboard_csv']}', all_varchar = true, header = true)),
                 pa AS (SELECT DISTINCT award_id FROM prime_transactions WHERE agency_code = getvariable('agency') AND award_category = 'assistance')
            SELECT count(DISTINCT fain) FROM d WHERE yy = '{yy}' AND fain NOT IN (SELECT award_id FROM pa)""").fetchone()[0]

    def drivers(self, cid, scope, basis, t, cat):
        w, yr = self._w(scope, basis)
        out = []
        for lst, title, sub, pa, ca, pn, cn in self.con.execute(f"""
                SELECT listing, any_value(program_title), any_value(subcategory),
                       coalesce(sum(amt) FILTER (WHERE {yr} = ?), 0), coalesce(sum(amt) FILTER (WHERE {yr} = ?), 0),
                       count(*) FILTER (WHERE {yr} = ?), count(*) FILTER (WHERE {yr} = ?)
                FROM _desk_c3 WHERE {w} AND category = ? AND {yr} IN (?, ?) GROUP BY 1""",
                [t - 1, t, t - 1, t, cat, t - 1, t]).fetchall():
            tot_p = self.mix_idx[(scope, basis, t - 1, cat)][11]
            tot_c = self.mix_idx[(scope, basis, t, cat)][11]
            out.append(dict(agency_code=self.ag, card_id=cid, scope=scope, listing=lst,
                            program_name=self.c4.listing_names.get(lst) or title, program_title=title, subcategory=sub,
                            is_scaap=lst == self.P["scaap_listing"], prior_amount=pa, current_amount=ca, change=ca - pa,
                            prior_count=int(pn), current_count=int(cn),
                            prior_share_of_scope=pa / tot_p if tot_p and lst != self.P["scaap_listing"] else None,
                            current_share_of_scope=ca / tot_c if tot_c and lst != self.P["scaap_listing"] else None))
        out.sort(key=lambda d: (-abs(d["change"]), d["listing"]))
        for i, d in enumerate(out):
            d["rank"] = i + 1
            d["is_top_driver"] = i < int(self.P["top_listings"])
            d["data_as_of"] = self.c4.data_as_of
        return out

    def one_award(self, scope, basis, t, cat, chg):
        """One-award concentration (3.4): >= one_award_share of the change, same direction; Card 4 label wording."""
        if not chg:
            return None
        w, yr = self._w(scope, basis)
        r = self.con.execute(f"""SELECT award_key, coalesce(sum(amt) FILTER (WHERE {yr} = ?), 0) - coalesce(sum(amt) FILTER (WHERE {yr} = ?), 0) AS d,
                                        any_value(recipient_name), any_value(component), any_value(fy)
                                 FROM _desk_c3 WHERE {w} AND category = ? AND NOT is_scaap AND {yr} IN (?, ?)
                                 GROUP BY 1 ORDER BY abs(d) DESC, 1 LIMIT 1""", [t, t - 1, cat, t - 1, t]).fetchone()
        if not r or r[1] * chg <= 0 or abs(r[1]) / abs(chg) < self.f("one_award_share"):
            return None
        c4 = self.c4
        lead = c4.T("label_lead_over" if abs(r[1]) > abs(chg) else "label_lead")
        lost = r[1] < 0
        return c4.T("label_award_lost" if lost else "label_award_new", lead=lead,
                    component=c4.short_comp.get(r[3], r[3]), award_type="grant", recipient=c4.display.get(r[2], r[2]),
                    year=t - 1 if lost else t, next_year=t, amount=money(abs(r[1])))

    # ------------------------------------------------------------ outputs
    def tables(self):
        ag, asof = self.ag, self.c4.data_as_of
        cards, cav, lst, rows, csvs = [], [], [], [], {}
        for c in self.cards:
            cards.append({k: v for k, v in c.items() if k not in ("caveats", "drivers")})
            for i, (k, txt) in enumerate(c["caveats"]):
                cav.append(dict(agency_code=ag, card_id=c["card_id"], sort=i + 1, caveat_key=k, text=txt, data_as_of=asof))
            lst += c["drivers"]
            w, yr = self._w("doj", c["basis"])
            r = self.con.execute(f"""SELECT {yr}, award_id, award_key, listing, program_title, subcategory, component, recipient_name,
                                            recipient_uei, st, new_dt, amt, award_cycle, like_elapsed_flag, in_like_period, is_scaap, in_ojp, in_ojpx
                                     FROM _desk_c3 WHERE {w} AND category = ? AND {yr} IN (?, ?) ORDER BY 1, new_dt, award_key""",
                                 [c["category"], c["fiscal_year"] - 1, c["fiscal_year"]]).fetchall()
            crow = [dict(agency_code=ag, card_id=c["card_id"], year_role="current" if x[0] == c["fiscal_year"] else "prior", fiscal_year=x[0],
                         fain=x[1], award_key=x[2], listing=x[3], program_title=x[4], subcategory=x[5], component=x[6],
                         recipient_name=x[7], recipient_uei=x[8], recipient_state=x[9], new_award_date=x[10], amount=x[11],
                         award_cycle=x[12], like_elapsed=x[13], in_like_period=x[14], is_scaap=x[15], in_ojp_scope=x[16],
                         in_ojp_excl_voca_scope=x[17], usaspending_url=URL.format(x[2]), data_as_of=asof) for x in r]
            rows += crow
            csvs[c["card_id"]] = (self.csv_header(c), crow)
        mix = [dict(agency_code=ag, scope=r[0], basis=r[1], year=r[2], segment=r[3], category=r[4], is_scaap_segment=r[5], n_awards=r[6],
                    amount=r[7], display_share=r[8], trigger_share=r[9], scope_total=r[10], scope_total_excl_scaap=r[11],
                    is_hatched=bool(r[1] in ("fy", "like") and self.c4.cov.get(("assistance", r[2]), {}).get("prov")),
                    data_as_of=asof) for r in self.mix_rows]
        periods = []
        pdefs = [(self.complete[i], self.complete[min(i + 2, len(self.complete) - 1)]) for i in range(0, len(self.complete), 3)]
        for scope in SCOPES:
            for a, b in pdefs:
                for seg, cat, is_s, amt, voca in self.con.execute(f"""
                        SELECT CASE WHEN is_scaap THEN 'SCAAP' ELSE category END, any_value(category), bool_or(is_scaap), sum(amt),
                               coalesce(sum(amt) FILTER (WHERE listing IN ({_in(self.P['voca_formula_listings'])})), 0)
                        FROM _desk_c3 WHERE {self.scope_where(scope)} AND fy BETWEEN {a} AND {b} GROUP BY 1 ORDER BY 1""").fetchall():
                    periods.append(dict(agency_code=ag, scope=scope, period=f"FY{a}–{b}", first_fy=a, last_fy=b, segment=seg, category=cat,
                                        is_scaap_segment=is_s, amount=amt, voca_formula_amount=voca, data_as_of=asof))
        office = [dict(agency_code=ag, listing=r[0], program_title=r[1], category=r[2], subcategory=r[3], rationale=r[4],
                       office_scheme=r[5], office_rule=r[6], office_matches=(r[5] == r[6]), new_award_amount_fy_window=r[7], data_as_of=asof)
                  for r in self.con.execute(f"""
            WITH o AS (SELECT program_code AS listing, component, sum(abs(federal_action_obligation)) AS v
                       FROM _award_tx2 t JOIN prime_transactions p USING (transaction_key)
                       WHERE t.definition = 'awarding' AND t.award_category = 'assistance' AND p.agency_code = getvariable('agency')
                       GROUP BY 1, 2),
                 r AS (SELECT listing, arg_max(component, (v, component)) AS comp FROM o GROUP BY 1),
                 short AS (SELECT * FROM (VALUES ('Office of Justice Programs', 'OJP'), ('Office on Violence Against Women', 'OVW'),
                                                 ('COPS Office', 'COPS'), ('Bureau of Prisons', 'BOP')) v(component, short))
            SELECT s.listing, s.program_title, s.category, s.subcategory, s.rationale, s.office_scheme,
                   coalesce(sh.short, r.comp), (SELECT sum(amt) FROM _desk_c3 c WHERE c.listing = s.listing AND c.fy BETWEEN {self.complete[0]} AND {self.complete[-1]})
            FROM _desk_c3_scheme s LEFT JOIN r USING (listing) LEFT JOIN short sh ON sh.component = r.comp ORDER BY 1""").fetchall()]
        scopes = [dict(r, agency_code=ag, data_as_of=asof) for r in self.scope_rows]
        caps = [dict(agency_code=ag, fiscal_year=y, cap=v) for y, v in sorted(self.caps.items())]
        text = [dict(agency_code=ag, key=k, template=v) for k, v in sorted(self.text.items())]
        params = [dict(agency_code=ag, parameter=k, value=v) for k, v in sorted(self.P.items())]
        return dict(desk_card3_cards=cards, desk_card3_caveats=cav, desk_card3_listings=lst, desk_card3_rows=rows, desk_card3_mix=mix,
                    desk_card3_periods=periods, desk_card3_categories=office, desk_card3_scopes=scopes, desk_card3_cvf_cap=caps,
                    desk_card3_text=text, desk_card3_params=params), csvs

    def csv_header(self, c):
        return [c["headline"] + " " + c["second_line"] + (" " + c["label_text"] if c["label_text"] else ""),
                f"Rows: every new grant award (metrics 7.7) in {c['category']} in FY{c['fiscal_year'] - 1} and FY{c['fiscal_year']}"
                + (f", October–{self.cut.strftime('%B')} only in both years" if c["like_period"] else "")
                + ", all DOJ components (scope columns mark OJP and OJP excluding VOCA formula grants).",
                f"Definition: awarding agency {self.ag} ({self.c4.short}); fiscal year of the new-award date; categories from {self.P['categories_csv']}. "
                + self.T("csv_note"),
                f"Source: USAspending prime award transactions; data as of {str(self.c4.data_as_of)[:10]}. Card {c['card_id']}.",
                c["fixed_line"]] + [f"Note: {t}" for _, t in c["caveats"]]


CSV_COLS = ["year_role", "fiscal_year", "fain", "award_key", "listing", "program_title", "subcategory", "component", "recipient_name",
            "recipient_uei", "recipient_state", "new_award_date", "amount", "award_cycle", "like_elapsed", "in_like_period", "is_scaap",
            "in_ojp_scope", "in_ojp_excl_voca_scope", "usaspending_url"]


def write_csvs(csvs, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("card3-*.csv"):
        old.unlink()
    paths = []
    for cid in sorted(csvs):
        header, rows = csvs[cid]
        p = out_dir / f"{cid}.csv"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            for line in header:
                fh.write("# " + line + "\n")
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(CSV_COLS)
            for r in rows:
                w.writerow(["" if r[k] is None else (f"{r[k]:.2f}" if k == "amount" else ("t" if r[k] is True else "f" if r[k] is False else r[k]))
                            for k in CSV_COLS])
        paths.append(p)
    return paths


_D, _V, _I, _L, _B = "DOUBLE", "VARCHAR", "INTEGER", "VARCHAR[]", "BOOLEAN"
_C = {"agency_code": _V, "data_as_of": "TIMESTAMP"}
COLUMN_TYPES = {
    "desk_card3_cards": dict(_C, fiscal_year=_I, prior_year=_I, candidate_scopes=_L, confirmed_scopes=_L, flags=_L, labels=_L,
                             caveat_keys=_L, cycle_share_shift_pts=_D, ojp_missing_awards=_I, label_text=_V, late_cycle_pct_floor=_I,
                             denominator_f=_D, denominator_s_star=_D,
                             amount_prior=_D, amount_current=_D, change=_D),
    "desk_card3_caveats": dict(_C, sort=_I),
    "desk_card3_listings": dict(_C, prior_count=_I, current_count=_I, rank=_I, prior_share_of_scope=_D, current_share_of_scope=_D,
                                prior_amount=_D, current_amount=_D, change=_D),
    "desk_card3_rows": dict(_C, fiscal_year=_I, award_cycle=_I, new_award_date="DATE", amount=_D, fain=_V, recipient_uei=_V, recipient_state=_V),
    "desk_card3_mix": dict(_C, year=_I, n_awards=_I, amount=_D, display_share=_D, trigger_share=_D, scope_total=_D, scope_total_excl_scaap=_D),
    "desk_card3_periods": dict(_C, first_fy=_I, last_fy=_I, amount=_D, voca_formula_amount=_D),
    "desk_card3_categories": dict(_C, office_rule=_V, new_award_amount_fy_window=_D),
    "desk_card3_scopes": dict(_C, fiscal_year=_I, cycle_share_shift_pts=_D, timing=_V, denominator_f=_D, denominator_s_star=_D, amount_prior=_D, amount_current=_D, change=_D),
    "desk_card3_cvf_cap": dict(_C, fiscal_year=_I, cap=_D),
    "desk_card3_text": {"agency_code": _V, "key": _V, "template": _V},
    "desk_card3_params": {"agency_code": _V, "parameter": _V, "value": _V},
}
