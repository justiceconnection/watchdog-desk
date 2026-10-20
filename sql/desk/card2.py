"""Watchdog Desk, Card 2: contracts awarded without competition (docs/specs/watchdog-cards.md 2.1-2.4).

Universe: new contract awards = base records (modification_number '0'), awarding agency = the agency, joined to
contract_transactions for the competition fields. Small purchases are excluded by BOTH tests (2.1): a NULL-safe code
test (extent F/G, solicitation SP1, justification SP2/MPT; 182,499 DOJ base records have a NULL in
at least one code field, so every comparison is wrapped in coalesce(..., false)) OR anticipated value at award
(base_and_all_options_value, else the base obligation) at or below $250,000. Not competed = B, C, NDO; competed =
A, D, E, CDO (E per FPDS convention); a NULL extent code is "not reported" and left out of the share.
Dollars are initial award obligations (the base record's federal_action_obligation).

Parameters, reason labels, flag list and reader text are seeds (sql/seeds/desk_card2_*.csv).
Called by sql/build_marts.py (desk step). Creates desk_card2_* tables and one CSV (not-competed rows).
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
URL = "https://www.usaspending.gov/award/{}/"


def _seed(name, agency):
    with open(ROOT / "sql" / "seeds" / name, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["agency_code"] == agency]


def _in(codes: str) -> str:
    return ", ".join(f"'{c}'" for c in codes.split()) or "NULL"


def money(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${a / 1e9:,.1f} billion"
    if a >= 1e6:
        return f"${a / 1e6:,.1f} million"
    return f"${a:,.0f}"


class Card2:
    def __init__(self, con, agency: str):
        self.con, self.ag = con, agency
        self.P = {r["parameter"]: r["value"] for r in _seed("desk_card2_params.csv", agency)}
        if not self.P:
            raise SystemExit(f"no desk_card2_params rows for agency {agency}")
        self.text = {r["key"]: r["template"] for r in _seed("desk_card2_text.csv", agency)}
        self.display = {r["recorded_name"]: r["display_name"] for r in _seed("recipient_display_names.csv", agency)}
        self.flags = sorted(_seed("desk_card2_flags.csv", agency), key=lambda r: int(r["sort"]))
        self.short = (con.execute("SELECT abbreviation FROM _agency_names").fetchone() or [agency])[0]
        self.data_as_of = con.execute("SELECT data_as_of FROM _params").fetchone()[0]
        self.cov = {r[0]: dict(prov=r[1], partial=r[2], maxd=r[3]) for r in con.execute(
            """SELECT fiscal_year, is_provisional, is_partial_year, max_action_date FROM mart_award_coverage
               WHERE definition = 'awarding' AND award_category = 'contract'""").fetchall()}

    def _labels(self, name):
        with open(ROOT / "sql" / "seeds" / name, encoding="utf-8") as fh:
            return {r["code"]: r["label"] for r in csv.DictReader(fh)}

    def T(self, key, **kw):
        return self.text[key].format(**kw)

    def build(self):
        P, con = self.P, self.con
        con.execute(f"CREATE OR REPLACE TEMP TABLE _desk_c2_reasons AS SELECT code, label, band, CAST(sort AS INTEGER) AS sort "
                    f"FROM read_csv('sql/seeds/desk_card2_reasons.csv', header = true, all_varchar = true) WHERE agency_code = getvariable('agency')")
        years = [y for y, v in self.cov.items() if not v["partial"] and y >= int(P["first_fy"])]
        flagcols = ", ".join(f"ct.{r['column']} AS flag_{i}" for i, r in enumerate(self.flags))
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _desk_c2_base AS
            WITH b AS (
                SELECT p.transaction_key, p.award_key, p.fiscal_year AS fy, p.action_date, p.federal_action_obligation AS amt,
                       ct.extent_competed_code AS ec, ct.solicitation_procedures_code AS sp, ct.other_than_full_and_open_competition_code AS oth,
                       ct.base_and_all_options_value AS options_value,
                       coalesce(TRY_CAST(ct.base_and_all_options_value AS DOUBLE), p.federal_action_obligation) AS val,
                       ct.recipient_name, ct.recipient_uei, ct.type_of_set_aside_code AS set_aside, ct.number_of_offers_received AS offers,
                       ct.contracting_officers_determination_of_business_size_code AS size_code,
                       ct.organizational_type AS org_type, ct.awarding_sub_agency_name AS sub_agency, ct.awarding_office_name AS office,
                       ct.product_or_service_code AS psc, ct.product_or_service_code_description AS psc_description,
                       ct.naics_code AS naics, ct.naics_description, ct.primary_place_of_performance_state_code AS pop_state,
                       left(coalesce(ct.prime_award_base_transaction_description, ct.transaction_description), 200) AS description,
                       {flagcols}
                FROM prime_transactions p
                JOIN contract_transactions ct ON ct.contract_transaction_unique_key = p.transaction_key
                WHERE p.agency_code = getvariable('agency') AND p.awarding_agency_code = p.agency_code
                  AND p.award_category = 'contract' AND p.modification_number = '0'
                  AND p.fiscal_year IN ({", ".join(str(y) for y in years)}))
            SELECT *,
                   -- NULL-safe small-purchase code test
                   (coalesce(ec IN ({_in(P['sap_extent_codes'])}), false) OR coalesce(sp IN ({_in(P['sap_solicitation_codes'])}), false)
                    OR coalesce(oth IN ({_in(P['sap_justification_codes'])}), false)) AS sap_code,
                   val <= {float(P['sap_threshold'])} AS sap_value,
                   CASE WHEN ec IN ({_in(P['not_competed_codes'])}) THEN 'not_competed'
                        WHEN ec IN ({_in(P['competed_codes'])}) THEN 'competed'
                        WHEN ec IS NULL THEN 'not_reported' ELSE 'other' END AS cls
            FROM b""")
        con.execute("""CREATE OR REPLACE TEMP TABLE _desk_c2_u AS
                       SELECT * FROM _desk_c2_base WHERE NOT sap_code AND NOT sap_value""")
        self.years = sorted(years)

    def tables(self):
        P, con, ag, asof = self.P, self.con, self.ag, self.data_as_of
        ut = P["utilities_code"]
        summ = con.execute(f"""
            SELECT fy, count(*) FILTER (WHERE cls IN ('competed', 'not_competed')) AS n_universe,
                   count(*) FILTER (WHERE cls = 'not_competed') AS n_nc, count(*) FILTER (WHERE cls = 'competed') AS n_c,
                   count(*) FILTER (WHERE cls = 'not_reported') AS n_nr, count(*) FILTER (WHERE cls = 'other') AS n_other,
                   coalesce(sum(amt) FILTER (WHERE cls IN ('competed', 'not_competed')), 0) AS d_universe,
                   coalesce(sum(amt) FILTER (WHERE cls = 'not_competed'), 0) AS d_nc,
                   coalesce(sum(amt) FILTER (WHERE cls = 'competed'), 0) AS d_c,
                   coalesce(sum(amt) FILTER (WHERE cls = 'not_reported'), 0) AS d_nr,
                   count(*) FILTER (WHERE cls = 'not_competed' AND oth = '{ut}') AS n_ut,
                   coalesce(sum(amt) FILTER (WHERE cls = 'not_competed' AND oth = '{ut}'), 0) AS d_ut
            FROM _desk_c2_u GROUP BY 1 ORDER BY 1""").fetchall()
        top = con.execute(f"""
            WITH nc AS (SELECT * FROM _desk_c2_u WHERE cls = 'not_competed'),
                 t AS (SELECT fy, sum(amt) AS tot FROM nc GROUP BY 1)
            SELECT nc.fy, row_number() OVER (PARTITION BY nc.fy ORDER BY nc.amt DESC, nc.transaction_key) AS rk,
                   nc.award_key, nc.recipient_name, nc.recipient_uei, nc.amt, nc.amt / t.tot AS share, nc.oth,
                   coalesce(r.label, nc.oth, 'not stated') AS reason_label, nc.sub_agency, nc.psc_description, nc.action_date
            FROM nc JOIN t USING (fy) LEFT JOIN _desk_c2_reasons r ON r.code = nc.oth
            QUALIFY rk <= {int(P['top_awards_n'])} ORDER BY 1, 2""").fetchall()
        top_by = {}
        for r in top:
            top_by.setdefault(r[0], []).append(r)
        summary = []
        for (fy, nu, nnc, nc_, nnr, nother, du, dnc, dc, dnr, nut, dut) in summ:
            cov = self.cov[fy]
            period = self.T("period_provisional" if cov["prov"] else "period_complete", t=fy)
            first = top_by.get(fy, [None])[0]
            share_top = first[6] if first else None
            show_top = share_top is not None and share_top >= float(P["concentration_share"])
            summary.append({
                "agency_code": ag, "card_id": f"card2-{ag}-{fy}", "card_type": "contracts_without_competition", "status": "card",
                "csv_path": f"desk/csv/card2-{ag}-not-competed.csv", "fiscal_year": fy, "period_label": period, "is_provisional": bool(cov["prov"]),
                "data_through": cov["maxd"], "n_universe": nu, "n_not_competed": nnc, "n_competed": nc_, "n_not_reported": nnr,
                "n_other_code": nother, "dollars_universe": du, "dollars_not_competed": dnc, "dollars_competed": dc,
                "dollars_not_reported": dnr,
                "share_count": nnc / nu if nu else None, "share_dollars": dnc / du if du else None,
                "n_utilities": nut, "dollars_utilities": dut,
                "n_not_competed_excl_utilities": nnc - nut, "dollars_not_competed_excl_utilities": dnc - dut,
                "share_count_utilities": nut / nu if nu else None, "share_dollars_utilities": dut / du if du else None,
                "top_award_share": share_top, "show_top_awards": show_top,
                "headline": self.T("headline", period=period, p=f"{100 * nnc / nu:.1f}%", agency=self.short, n=f"{nnc:,}", N=f"{nu:,}",
                                   d=money(dnc), D=money(du)) if nu else None,
                "concentration_line": self.T("concentration_line", amount=money(first[5]), recipient=self.display.get(first[3], first[3]), reason=first[8].lower(),
                                             share=f"{100 * share_top:.0f}%", period=period, t=fy) if show_top else None,
                "fixed_line": self.T("fixed_line"),
                "provisional_note": self.T("provisional_note", t=fy, through=f"{cov['maxd'].strftime('%b')} {cov['maxd'].day}, {cov['maxd'].year}")
                if cov["prov"] else None,
                "data_as_of": asof})
        # why_range (2.3): range of dollar shares over the complete years, then this year's share
        comp = [r for r in summary if not r["is_provisional"] and r["share_dollars"] is not None]
        if comp:
            lo = min(comp, key=lambda r: (r["share_dollars"], r["fiscal_year"]))
            hi = max(comp, key=lambda r: (r["share_dollars"], -r["fiscal_year"]))
            for r in summary:
                r["why_text"] = self.T("why_range", first=comp[0]["fiscal_year"], last_complete=comp[-1]["fiscal_year"],
                                       min_pct=f"{100 * lo['share_dollars']:.0f}%", min_fy=lo["fiscal_year"],
                                       max_pct=f"{100 * hi['share_dollars']:.0f}%", max_fy=hi["fiscal_year"],
                                       period=r["period_label"], cur_pct=f"{100 * r['share_dollars']:.0f}%")
        tops = [{"agency_code": ag, "fiscal_year": r[0], "rank": r[1], "award_key": r[2], "recipient_name": r[3], "recipient_uei": r[4],
                 "amount": r[5], "share_of_not_competed_dollars": r[6], "reason_code": r[7], "reason_label": r[8], "sub_agency": r[9],
                 "psc_description": r[10], "action_date": r[11], "usaspending_url": URL.format(r[2]), "data_as_of": asof} for r in top]
        # three small-purchase exclusion choices (2.1 comparison table). "Value only" follows the spec: G counts as not competed.
        nc_codes, c_codes = _in(P["not_competed_codes"]), _in(P["competed_codes"])
        choices = []
        for rule, where, ncx, cx in (
                ("code_only", "NOT sap_code", nc_codes, c_codes),
                ("value_only", "NOT sap_value", nc_codes + ", 'G'", c_codes + ", 'F'"),
                ("both", "NOT sap_code AND NOT sap_value", nc_codes, c_codes)):
            for fy, n_nc, n_all, d_nc, d_all in con.execute(f"""
                    SELECT fy, count(*) FILTER (WHERE ec IN ({ncx})), count(*) FILTER (WHERE ec IN ({ncx}) OR ec IN ({cx})),
                           coalesce(sum(amt) FILTER (WHERE ec IN ({ncx})), 0), coalesce(sum(amt) FILTER (WHERE ec IN ({ncx}) OR ec IN ({cx})), 0)
                    FROM _desk_c2_base WHERE {where} GROUP BY 1 ORDER BY 1""").fetchall():
                choices.append({"agency_code": ag, "fiscal_year": fy, "rule": rule, "is_default": rule == "both",
                                "n_not_competed": n_nc, "n_universe": n_all, "dollars_not_competed": d_nc, "dollars_universe": d_all,
                                "data_as_of": asof})
        reasons = [{"agency_code": ag, "fiscal_year": r[0], "reason_code": r[1], "reason_label": r[2], "band": r[3], "sort": r[4],
                    "n_awards": r[5], "dollars": r[6], "share_count_of_universe": r[7], "share_dollars_of_universe": r[8], "data_as_of": asof}
                   for r in con.execute("""
            WITH t AS (SELECT fy, count(*) FILTER (WHERE cls IN ('competed', 'not_competed')) AS nu,
                              sum(amt) FILTER (WHERE cls IN ('competed', 'not_competed')) AS du FROM _desk_c2_u GROUP BY 1)
            SELECT u.fy, coalesce(u.oth, 'NONE'), coalesce(r.label, CASE WHEN u.oth IS NULL THEN 'Reason not stated' ELSE u.oth END),
                   coalesce(r.band, 'other'), coalesce(r.sort, 99), count(*), sum(u.amt), count(*) / any_value(t.nu), sum(u.amt) / any_value(t.du)
            FROM _desk_c2_u u JOIN t USING (fy) LEFT JOIN _desk_c2_reasons r ON r.code = u.oth
            WHERE u.cls = 'not_competed' GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 5, 2""").fetchall()]
        # recipient types among not-competed awards; flags are never additive
        rt = []
        dims = [("size", "CASE size_code WHEN 'S' THEN 'Small business' WHEN 'O' THEN 'Other than small' ELSE 'Not reported' END", True, ""),
                ("organization_type", "coalesce(org_type, 'Not reported')", True, f"AND fy >= {int(P['org_type_first_fy'])}"),
                ("set_aside", "coalesce(set_aside, 'Not reported')", True, "")]
        labels = {"set_aside": self._labels("contract_set_aside_labels.csv"), "organization_type": self._labels("contract_org_type_labels.csv"),
                  "size": {}}
        for dim, expr, additive, extra in dims:
            for fy, cat, n, d in con.execute(f"""SELECT fy, {expr}, count(*), sum(amt) FROM _desk_c2_u
                                                 WHERE cls = 'not_competed' {extra} GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
                lab = labels[dim].get(cat, cat)
                if dim != "size" and cat not in labels[dim]:
                    raise SystemExit(f"Card 2: no plain-English label for {dim} code {cat!r}; add it to the seed")
                rt.append({"agency_code": ag, "fiscal_year": fy, "dimension": dim, "category": cat, "category_label": lab,
                           "is_additive": additive, "n_awards": n, "dollars": d, "data_as_of": asof})
        for i, f in enumerate(self.flags):
            for fy, n, d in con.execute(f"""SELECT fy, count(*), coalesce(sum(amt), 0) FROM _desk_c2_u
                                            WHERE cls = 'not_competed' AND flag_{i} = 't' GROUP BY 1 ORDER BY 1""").fetchall():
                rt.append({"agency_code": ag, "fiscal_year": fy, "dimension": "flag", "category": f["column"], "category_label": f["label"], "is_additive": False,
                           "n_awards": n, "dollars": d, "data_as_of": asof})
        # secondary dollar view: obligations of every action (by action FY) on universe awards, by class
        allact = [{"agency_code": ag, "fiscal_year": r[0], "competition_class": r[1], "n_actions": r[2], "dollars": r[3], "data_as_of": asof}
                  for r in con.execute(f"""
            WITH a AS (SELECT DISTINCT award_key, cls FROM _desk_c2_u WHERE cls IN ('competed', 'not_competed'))
            SELECT p.fiscal_year, a.cls, count(*), sum(p.federal_action_obligation)
            FROM prime_transactions p JOIN a USING (award_key)
            WHERE p.agency_code = getvariable('agency') AND p.awarding_agency_code = p.agency_code AND p.award_category = 'contract'
              AND p.fiscal_year IN ({", ".join(str(y) for y in self.years)})
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()]
        # rows: not-competed new awards in the universe (2.3 CSV)
        fl = ", ".join(f"flag_{i} = 't' AS \"{f['column']}\"" for i, f in enumerate(self.flags))
        rows_q = f"""SELECT u.fy AS fiscal_year, u.award_key, u.transaction_key, u.action_date, u.amt AS amount, u.options_value AS anticipated_value,
                            u.recipient_name, u.recipient_uei, u.ec AS extent_competed_code, u.oth AS reason_code,
                            coalesce(r.label, u.oth) AS reason_label, coalesce(r.band, 'other') AS band, u.sp AS solicitation_procedures_code,
                            u.set_aside AS set_aside_code, coalesce(sl.label, u.set_aside) AS set_aside_label,
                            u.offers AS number_of_offers, u.size_code AS business_size_code,
                            CASE WHEN u.fy >= {int(P['org_type_first_fy'])} THEN u.org_type END AS organization_type,
                            CASE WHEN u.fy >= {int(P['org_type_first_fy'])} THEN coalesce(ol.label, u.org_type) END AS organization_type_label,
                            {fl}, u.sub_agency, u.office, u.psc, u.psc_description, u.naics, u.naics_description, u.pop_state, u.description
                     FROM _desk_c2_u u LEFT JOIN _desk_c2_reasons r ON r.code = u.oth
                     LEFT JOIN read_csv('sql/seeds/contract_set_aside_labels.csv', header = true, all_varchar = true) sl ON sl.code = u.set_aside
                     LEFT JOIN read_csv('sql/seeds/contract_org_type_labels.csv', header = true, all_varchar = true) ol ON ol.code = u.org_type
                     WHERE u.cls = 'not_competed'
                     ORDER BY u.fy, u.action_date, u.transaction_key"""
        cur = con.execute(rows_q)
        cols = [d[0] for d in cur.description]
        rows = [dict(agency_code=ag, **dict(zip(cols, r)), usaspending_url=URL.format(r[1]), data_as_of=asof) for r in cur.fetchall()]
        text = [{"agency_code": ag, "key": k, "template": v} for k, v in sorted(self.text.items())]
        texts_rendered = [{"agency_code": ag, "key": "title", "text": self.T("title")},
                          {"agency_code": ag, "key": "explainer", "text": self.T("explainer")},
                          {"agency_code": ag, "key": "fixed_line", "text": self.T("fixed_line")},
                          {"agency_code": ag, "key": "statutory_note", "text": self.T("statutory_note")},
                          {"agency_code": ag, "key": "flags_note", "text": self.T("flags_note")},
                          {"agency_code": ag, "key": "org_type_note", "text": self.T("org_type_note", first=int(P["org_type_first_fy"]))}]
        params = [{"agency_code": ag, "parameter": k, "value": v} for k, v in sorted(P.items())]
        self.csv_rows, self.csv_cols = rows, ["fiscal_year"] + [c for c in cols if c != "fiscal_year"] + ["usaspending_url"]
        return dict(desk_card2_summary=summary, desk_card2_exclusion_choices=choices, desk_card2_reasons=reasons,
                    desk_card2_recipient_types=rt, desk_card2_top_awards=tops, desk_card2_all_actions=allact,
                    desk_card2_rows=rows, desk_card2_text=texts_rendered, desk_card2_templates=text, desk_card2_params=params)

    def write_csv(self, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"card2-{self.ag}-not-competed.csv"
        first, last = self.years[0], self.years[-1]
        prov = [y for y in self.years if self.cov[y]["prov"]]
        header = [self.T("title") + f": not-competed new contracts, FY{first}-FY{last}",
                  f"Rows: base records (modification 0) of contracts awarded by {self.short} (agency {self.ag}) coded not competed "
                  f"({self.P['not_competed_codes'].replace(' ', ', ')}), excluding small purchases (simplified-acquisition codes, or anticipated value "
                  f"${float(self.P['sap_threshold']):,.0f} or less). amount = initial award obligation; anticipated_value = base and all options.",
                  f"Source: USAspending contract transactions; data as of {str(self.data_as_of)[:10]}.",
                  self.T("explainer"),
                  self.T("fixed_line"),
                  self.T("flags_note") + " " + self.T("org_type_note", first=int(self.P["org_type_first_fy"])),
                  *(self.T("provisional_note", t=y, through=f"{self.cov[y]['maxd'].strftime('%b')} {self.cov[y]['maxd'].day}, {self.cov[y]['maxd'].year}")
                    for y in prov)]
        with open(p, "w", encoding="utf-8", newline="") as f:
            for line in header:
                f.write("# " + line + "\n")
            w = csv.writer(f, lineterminator="\n")
            w.writerow(self.csv_cols)
            for r in self.csv_rows:
                w.writerow(["" if r[k] is None else (f"{r[k]:.2f}" if k in ("amount", "anticipated_value") and isinstance(r[k], float)
                                                     else ("t" if r[k] is True else "f" if r[k] is False else r[k])) for k in self.csv_cols])
        return [p]


_D, _V, _I, _B = "DOUBLE", "VARCHAR", "INTEGER", "BOOLEAN"
_C = {"agency_code": _V, "fiscal_year": _I, "data_as_of": "TIMESTAMP"}
COLUMN_TYPES = {
    "desk_card2_summary": dict(_C, n_universe=_I, n_not_competed=_I, n_competed=_I, n_not_reported=_I, n_other_code=_I,
                               n_utilities=_I, n_not_competed_excl_utilities=_I, top_award_share=_D, concentration_line=_V,
                               provisional_note=_V, data_through="DATE", headline=_V, why_text=_V),
    "desk_card2_exclusion_choices": dict(_C, n_not_competed=_I, n_universe=_I),
    "desk_card2_reasons": dict(_C, sort=_I, n_awards=_I),
    "desk_card2_recipient_types": dict(_C, n_awards=_I),
    "desk_card2_top_awards": dict(_C, rank=_I, reason_code=_V, action_date="DATE"),
    "desk_card2_all_actions": dict(_C, n_actions=_I),
    "desk_card2_rows": dict(_C, action_date="DATE", amount=_D, anticipated_value=_D, reason_code=_V, organization_type=_V,
                            set_aside_code=_V, set_aside_label=_V, organization_type_label=_V, number_of_offers=_V, solicitation_procedures_code=_V, description=_V),
    "desk_card2_text": {"agency_code": _V, "key": _V, "text": _V},
    "desk_card2_templates": {"agency_code": _V, "key": _V, "template": _V},
    "desk_card2_params": {"agency_code": _V, "parameter": _V, "value": _V},
}
