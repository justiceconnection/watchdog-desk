"""Watchdog Desk: national organizations card (docs/specs/watchdog-cards.md 4.9).

Group: every new grant (metrics 7.7, awarding definition, assistance) to a national organization (the 146-UEI list
built by card4.Card4 into _desk_natorg; parameters natorg_* in desk_card4_params.csv).
Comparison: all other grant recipients, excluding non-national DC recipients (DC government agencies etc.), which
appear only in a footnote line. Same damped log ratio as Card 4: r = ln((v_t + c)/(v_t-1 + c)); the card appears
when |r_group - r_rest| >= natorg_gap_min (ln 1.5) and |excess| >= the Card 4 excess floor; count-only items need a
dollar change of count_card_min_dollar_change. One group, so no cross-sectional z. Fiscal-year basis; the award
cycle (like-elapsed) is evidence only; a reporting-gap year compares like periods (October to the cut-off month).

Reader text: sql/seeds/desk_natorg_text.csv. Called by sql/build_marts.py after card4 (needs its tables).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from card4 import ROOT, URL, amount, long_date, money, pct

GRP = "coalesce(recipient_uei, '') IN (SELECT recipient_uei FROM _desk_natorg WHERE recipient_uei IS NOT NULL)"


class NatOrg:
    def __init__(self, c4):
        self.c4, self.con, self.ag, self.P = c4, c4.con, c4.ag, c4.P
        with open(ROOT / "sql" / "seeds" / "desk_natorg_text.csv", encoding="utf-8") as f:
            self.text = {r["key"]: r["template"] for r in csv.DictReader(f) if r["agency_code"] == self.ag}
        hq = str(self.P.get("natorg_hq_state", ""))
        self.con.execute(f"""CREATE OR REPLACE TEMP TABLE _desk_ng AS
            SELECT award_key, award_id, new_award_date AS new_dt, new_award_fy AS fy, in_like_period, award_cycle, like_elapsed_flag,
                   component, recipient_state_raw AS st, recipient_name, recipient_uei, listing, listing_title,
                   recipient_type AS recip_type, new_award_amount AS new_amt,
                   CASE WHEN {GRP} THEN 'group' WHEN coalesce(recipient_state_raw, '') = '{hq}' THEN 'hq_other' ELSE 'rest' END AS side
            FROM _v2_award_new WHERE definition = 'awarding' AND award_category = 'assistance'""")

    def T(self, key, **kw):
        return self.text[key].format(**kw)

    def where(self, basis, t):
        if basis == "fy":
            return ("in_like_period" if self.c4.like_period("assistance", t) else "true"), "fy"
        return "award_cycle IS NOT NULL AND like_elapsed_flag", "award_cycle"

    def values(self, measure, basis, t):
        w, yr = self.where(basis, t)
        val = "count(*)" if measure == "count" else "coalesce(sum(new_amt), 0)"
        out = {(s, y): 0.0 for s in ("group", "rest", "hq_other") for y in (t - 1, t)}
        for s, y, v in self.con.execute(f"SELECT side, {yr}, {val} FROM _desk_ng WHERE {w} AND {yr} IN (?, ?) GROUP BY 1, 2",
                                        [t - 1, t]).fetchall():
            out[(s, y)] = float(v)
        return out

    def run(self):
        P, c4 = self.P, self.c4
        cov = c4.cov
        yrs = sorted(y for (c, y), v in cov.items() if c == "assistance" and not v["partial"])
        complete = [y for y in yrs if not cov[("assistance", y)]["prov"]]
        targets = [max(complete)] + [y for y in yrs if y > max(complete)]
        self.scores, self.cards = [], []
        for t in targets:
            for m in ("count", "dollars"):
                for basis in ("fy", "cycle"):
                    if basis == "cycle" and cov[("assistance", t)]["prov"]:
                        continue
                    v = self.values(m, basis, t)
                    c = P["c_dollars" if m == "dollars" else "c_counts"]
                    gp, gc, rp, rc = v[("group", t - 1)], v[("group", t)], v[("rest", t - 1)], v[("rest", t)]
                    r, R = math.log((gc + c) / (gp + c)), math.log((rc + c) / (rp + c))
                    exc = gc - gp * math.exp(R)
                    o = dict(fiscal_year=t, measure=m, basis=basis, group_prior=gp, group_current=gc, rest_prior=rp, rest_current=rc,
                             hq_other_prior=v[("hq_other", t - 1)], hq_other_current=v[("hq_other", t)], r_log=r, rest_r_log=R,
                             gap_log=r - R, excess=exc,
                             passes_gap=abs(r - R) >= P["natorg_gap_min"],
                             passes_excess=abs(exc) >= P["excess_dollars" if m == "dollars" else "excess_counts"])
                    o["is_candidate"] = o["passes_gap"] and o["passes_excess"]
                    o["opposite"] = r * R < 0
                    self.scores.append(o)
        idx = {(o["fiscal_year"], o["measure"], o["basis"]): o for o in self.scores}
        for o in self.scores:
            if o["basis"] != "fy" or not o["is_candidate"]:
                continue
            t, m = o["fiscal_year"], o["measure"]
            c = dict(o, card_id=f"natorg-{self.ag}-{t}-{m}")
            cyc = idx.get((t, m, "cycle"))
            c["cycle_gap_log"] = cyc["gap_log"] if cyc else None
            flags = []
            if c4.like_period("assistance", t):
                flags.append("gap_year")
            elif cyc is not None:
                flags.append("cycle_confirmed" if cyc["gap_log"] * o["gap_log"] > 0 and cyc["passes_gap"] else "timing?")
            status = "hold" if "timing?" in flags else "label" if "gap_year" in flags else "card"
            if "gap_year" in flags and P["gap_year_grant_status"] == "hold":
                status = "hold"
            w, yr = self.where("fy", t)
            dp, dc = self.con.execute(f"""SELECT coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0), coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0)
                                          FROM _desk_ng WHERE {w} AND side = 'group'""", [t - 1, t]).fetchone()
            c["dollar_change_same_rows"] = dc - dp
            if m == "count" and P["count_card_min_dollar_change"] > 0 and abs(dc - dp) < P["count_card_min_dollar_change"]:
                status = "suppressed"
            c.update(flags=flags, status=status)
            self.render(c)
            self.cards.append(c)
        return self.cards

    def render(self, c):
        c4, P = self.c4, self.P
        t, m = c["fiscal_year"], c["measure"]
        size = P["size_dollars" if m == "dollars" else "size_counts"]
        c["period_label"] = c4.period("assistance", t)
        c["pct_change"] = (c["group_current"] / c["group_prior"] - 1) if c["group_prior"] >= size else None
        c["rest_pct_change"] = (c["rest_current"] / c["rest_prior"] - 1) if c["rest_prior"] > 0 else None
        q = c["rest_pct_change"] or 0.0
        up = c["group_current"] > c["group_prior"]
        kw = dict(agency=c4.short, measure_word="dollars" if m == "dollars" else "awards", period=c["period_label"],
                  verb="rose" if up else "fell", pct=pct(c["pct_change"] or 0), prior=amount(c["group_prior"], m),
                  current=amount(c["group_current"], m), t_prior=t - 1, rest_pct=pct(q), rest_dir_noun="rise" if q > 0 else "fall",
                  rest_verb="rose" if q > 0 else "fell")
        case = "small_base" if c["pct_change"] is None else "opposite" if c["opposite"] else "same"
        c["headline_case"] = case
        c["headline"] = self.T("headline_" + case, **kw)
        gi = 100 * c["group_current"] / c["group_prior"] if c["group_prior"] else None
        ri = 100 * c["rest_current"] / c["rest_prior"] if c["rest_prior"] else None
        # raw (undamped) ratio of the two indexes; the damped ratio decides the card, the raw one is what readers see
        raw = (max(gi, ri) / min(gi, ri)) if gi and ri else None
        c["raw_ratio"] = raw
        parts = [self.T("why", t_prior=t - 1, g=f"{gi:,.0f}" if gi is not None else "n/a", r=f"{ri:,.0f}" if ri is not None else "n/a",
                        ratio=f"{raw:.1f}" if raw else "n/a")]
        if raw is not None and raw >= 1.5:
            parts.append(self.T("why_rule"))
        if c["opposite"]:
            parts.append(self.T("why_opposite"))
        c["why_text"] = " ".join(parts)
        c["fixed_line"] = c4.T("fixed_line")
        cav = []
        if c4.ojp_missing is not None:
            k = self.ojp_missing_group()
            c["ojp_missing_awards"] = k
            cav.append(("ojp_gap", self.T("caveat_ojp_gap" if k else "caveat_ojp_gap_zero", k=f"{k:,}", y=c4.ojp_year)))
        else:
            c["ojp_missing_awards"] = None
        if c4.like_period("assistance", t):
            cut = c4.cutoff["assistance"]
            cav.append(("grant_cutoff", c4.T("caveat_grant_cutoff", t=t, t_prior=t - 1, cut_long=long_date(cut), cut_month=cut.strftime("%B"))))
        elif c["cycle_gap_log"] is not None:
            cut = c4.cutoff["assistance"]
            cav.append(("cycle_so_far", self.T("caveat_cycle_so_far", t=t, cut_md=f"{cut.strftime('%B')} {cut.day}")))
        cav.append(("hq_other", self.T("caveat_hq_other", hq=c4.state_names.get(str(P["natorg_hq_state"]), P["natorg_hq_state"]),
                                       prior=amount(c["hq_other_prior"], m), current=amount(c["hq_other_current"], m),
                                       measure_word="dollars" if m == "dollars" else "awards",
                                       t_prior=t - 1, period=c["period_label"])))
        cav.append(("membership", self.T("caveat_membership", n=self.n_orgs())))
        c["caveat_keys"], c["caveats"] = [k for k, _ in cav], cav

    def n_orgs(self):
        return self.con.execute("SELECT count(DISTINCT recipient_uei) FROM _desk_natorg").fetchone()[0]

    def ojp_missing_group(self):
        """OJP-listed awards of year ojp_gap_year not in USAspending whose OJP legal name equals a national organization's
        USAspending recipient name (case- and space-insensitive). OJP's list has no UEI, so names are the only key."""
        c4 = self.c4
        yy = f"{c4.ojp_year % 100:02d}"
        src = str(self.P["ojp_dashboard_csv"])
        return self.con.execute(f"""
            WITH d AS (SELECT replace("Award Number", '-', '') AS fain, upper(trim(regexp_replace("Legal Name", '\\s+', ' ', 'g'))) AS nm,
                              regexp_extract("NOFO Title", 'FY ?(20)?(\\d\\d)([^0-9]|$)', 2) AS yy
                       FROM read_csv('{src}', all_varchar = true, header = true)),
                 pa AS (SELECT DISTINCT award_id FROM prime_transactions WHERE agency_code = getvariable('agency') AND award_category = 'assistance'),
                 nm AS (SELECT DISTINCT upper(trim(regexp_replace(recipient_name, '\\s+', ' ', 'g'))) AS nm FROM _desk_ng WHERE side = 'group')
            SELECT count(DISTINCT fain) FROM d WHERE yy = '{yy}' AND fain NOT IN (SELECT award_id FROM pa) AND nm IN (SELECT nm FROM nm)""").fetchone()[0]

    # ------------------------------------------------------------ outputs (same shapes as card4_*)
    def tables(self):
        ag, asof, c4 = self.ag, self.c4.data_as_of, self.c4
        cards, series, cavs, comps, progs, orgs, rows = [], [], [], [], [], [], []
        idx = {(o["fiscal_year"], o["measure"], o["basis"]): o for o in self.scores}
        csvs = {}
        for c in self.cards:
            cid, t, m = c["card_id"], c["fiscal_year"], c["measure"]
            cards.append({k: c[k] for k in ("card_id", "fiscal_year", "measure", "group_prior", "group_current", "rest_prior", "rest_current",
                                            "hq_other_prior", "hq_other_current", "pct_change", "rest_pct_change", "r_log", "rest_r_log",
                                            "gap_log", "cycle_gap_log", "excess", "opposite", "flags", "status", "dollar_change_same_rows",
                                            "ojp_missing_awards", "raw_ratio", "headline_case", "period_label", "headline", "why_text", "fixed_line",
                                            "caveat_keys")}
                         | {"agency_code": ag, "card_type": "national_organizations", "prior_year": t - 1, "basis": "fy",
                            "like_period": c4.like_period("assistance", t), "is_provisional": bool(c4.cov[("assistance", t)]["prov"]),
                            "group_label": "National organizations", "rest_label": "All other grant recipients",
                            "csv_path": f"desk/csv/{cid}.csv",
                            "method_ref": "docs/specs/watchdog-cards.md 4.9; docs/metrics.md 7.7; sql/desk/natorg.py", "data_as_of": asof})
            for i, (k, txt) in enumerate(c["caveats"]):
                cavs.append({"agency_code": ag, "card_id": cid, "sort": i + 1, "caveat_key": k, "text": txt, "data_as_of": asof})
            for panel, basis, plabel in (("fiscal_year", "fy", "Fiscal year"), ("award_cycle", "cycle", "Award cycle (evidence)")):
                o = idx.get((t, m, basis))
                if not o:
                    continue
                for ent, lab, p, q in (("group", "National organizations", o["group_prior"], o["group_current"]),
                                       ("rest", "All other grant recipients", o["rest_prior"], o["rest_current"])):
                    for role, y, v in (("prior", t - 1, p), ("current", t, q)):
                        lbl = f"FY{y}" if basis == "fy" else f"FY{y} award cycle"
                        if basis == "fy" and c4.like_period("assistance", t):
                            lbl += f" (Oct–{c4.cutoff['assistance'].strftime('%b')})"
                        series.append({"agency_code": ag, "card_id": cid, "panel": panel, "panel_label": plabel, "entity": ent,
                                       "entity_label": lab, "year_role": role, "year": y, "period_label": lbl, "value": v,
                                       "index_value": 100.0 * v / p if p > 0 else None,
                                       "is_provisional": bool(basis == "fy" and c4.cov.get(("assistance", y), {}).get("prov")),
                                       "data_as_of": asof})
            w, yr = self.where("fy", t)
            card_rows = []
            for y, ak, aid, nd, comp, lst, lt, rn, ru, rt, st, amt in self.con.execute(f"""
                    SELECT {yr}, award_key, award_id, new_dt, component, listing, listing_title, recipient_name, recipient_uei, recip_type, st, new_amt
                    FROM _desk_ng WHERE {w} AND side = 'group' AND {yr} IN (?, ?) ORDER BY 1, new_dt, award_key""", [t - 1, t]).fetchall():
                card_rows.append({"agency_code": ag, "card_id": cid, "row_kind": "award", "year_role": "current" if y == t else "prior",
                                  "fiscal_year": y, "award_key": ak, "award_id": aid, "new_award_date": nd, "component": comp, "listing": lst,
                                  "program_name": c4.listing_names.get(lst) or lt, "recipient_name": rn, "recipient_uei": ru,
                                  "recipient_type": rt, "recipient_type_label": c4.rtype.get(rt) if rt else None, "recipient_state": st,
                                  "n_awards": 1, "amount": amt, "usaspending_url": URL.format(ak), "data_as_of": asof})
            for kind, lab, side in (("group_total", "National organizations", "group"), ("rest_total", "All other grant recipients", "rest"),
                                    ("hq_other_total", "Other DC recipients (in neither group)", "hq_other")):
                for role, y in (("prior", t - 1), ("current", t)):
                    n = self.values("count", "fy", t)[(side, y)]
                    d = self.values("dollars", "fy", t)[(side, y)]
                    card_rows.append({"agency_code": ag, "card_id": cid, "row_kind": kind, "year_role": role, "fiscal_year": y,
                                      "award_key": None, "award_id": None, "new_award_date": None, "component": None, "listing": None,
                                      "program_name": None, "recipient_name": lab, "recipient_uei": None, "recipient_type": None,
                                      "recipient_type_label": None, "recipient_state": None, "n_awards": int(n), "amount": d,
                                      "usaspending_url": None, "data_as_of": asof})
            rows += card_rows
            csvs[cid] = (self.csv_header(c), card_rows)
            comps += self.drivers(c, "component", None)
            progs += self.drivers(c, "listing", None)
            orgs += self.drivers(c, "recipient_name", int(self.P["natorg_top_organizations"]))
        scores = [dict(o, agency_code=ag, data_as_of=asof) for o in self.scores]
        members = [{"agency_code": ag, "recipient_uei": u, "recipient_name": n, "rule_basis": b,
                    "recipient_state": s, "data_as_of": asof} for u, n, b, s in self.con.execute("""
                    SELECT o.recipient_uei, min(r.mst_name), string_agg(DISTINCT o.basis, '+' ORDER BY o.basis), min(r.mst)
                    FROM _desk_natorg o
                    LEFT JOIN (SELECT t.u, t.mst, (SELECT min(recipient_name) FROM _v2_award_new a WHERE a.recipient_uei = t.u) AS mst_name
                               FROM _desk_rtype t) r ON r.u = o.recipient_uei
                    GROUP BY 1 ORDER BY 1""").fetchall()]
        text = [{"agency_code": ag, "key": k, "template": v} for k, v in sorted(self.text.items())]
        return dict(desk_natorg_cards=cards, desk_natorg_caveats=cavs, desk_natorg_series=series, desk_natorg_components=comps,
                    desk_natorg_programs=progs, desk_natorg_organizations=orgs, desk_natorg_rows=rows, desk_natorg_scores=scores,
                    desk_natorg_members=members, desk_natorg_text=text), csvs

    def drivers(self, c, col, top):
        cid, t, m = c["card_id"], c["fiscal_year"], c["measure"]
        w, yr = self.where("fy", t)
        key = "dollars_change" if m == "dollars" else "count_change"
        out = []
        for k, lt, uei, pc, cc, pd, cd, aw in self.con.execute(f"""
                SELECT {col}, min(listing_title), min(recipient_uei),
                       count(*) FILTER (WHERE {yr} = ?), count(*) FILTER (WHERE {yr} = ?),
                       coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0), coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0),
                       list(award_key ORDER BY abs(new_amt) DESC, award_key)[1:5]
                FROM _desk_ng WHERE {w} AND side = 'group' AND {yr} IN (?, ?) GROUP BY 1""",
                [t - 1, t, t - 1, t, t - 1, t]).fetchall():
            d = dict(agency_code=self.ag, card_id=cid, prior_count=int(pc), current_count=int(cc), count_change=int(cc - pc),
                     prior_dollars=pd, current_dollars=cd, dollars_change=cd - pd)
            if col == "component":
                d["component"] = k
            elif col == "listing":
                d.update(listing=k, program_name=self.c4.listing_names.get(k) or lt,
                         name_source="listing_names seed" if k in self.c4.listing_names else "assistance listing title")
            else:
                d.update(recipient_name=k, recipient_uei=uei, award_keys=list(aw), award_urls=[URL.format(a) for a in aw])
            out.append(d)
        out.sort(key=lambda d: (-abs(d[key]), -abs(d["dollars_change"]), str(d.get("component") or d.get("listing") or d.get("recipient_name"))))
        out = out[:top] if top else out
        for i, d in enumerate(out):
            d["rank"], d["data_as_of"] = i + 1, self.c4.data_as_of
        return out

    def csv_header(self, c):
        t = c["fiscal_year"]
        return [c["headline"],
                f"Rows: every new grant award (metrics 7.7) to the {self.n_orgs()} national organizations (spec 4.9) in FY{t - 1} and FY{t}"
                + (f", October–{self.c4.cutoff['assistance'].strftime('%B')} only in both years" if self.c4.like_period("assistance", t) else "")
                + "; plus totals for national organizations, all other grant recipients, and other DC recipients (in neither group).",
                f"Definition: awarding agency {self.ag} ({self.c4.short}); amount = initial award amount (obligations on the new-award date); "
                f"fiscal year of the new-award date; nominal dollars.",
                f"Source: USAspending prime award transactions; data as of {str(self.c4.data_as_of)[:10]}. Card {c['card_id']}.",
                c["fixed_line"]] + [f"Caveat: {txt}" for _, txt in c["caveats"]]


CSV_COLS = ["row_kind", "year_role", "fiscal_year", "award_key", "award_id", "new_award_date", "component", "listing", "program_name",
            "recipient_name", "recipient_uei", "recipient_type", "recipient_type_label", "recipient_state", "n_awards", "amount", "usaspending_url"]


def write_csvs(csvs: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("natorg-*.csv"):
        old.unlink()
    paths = []
    for cid in sorted(csvs):
        header, rows = csvs[cid]
        p = out_dir / f"{cid}.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            for line in header:
                f.write("# " + line + "\n")
            w = csv.writer(f, lineterminator="\n")
            w.writerow(CSV_COLS)
            for r in rows:
                w.writerow(["" if r[k] is None else (f"{r[k]:.2f}" if k == "amount" else r[k]) for k in CSV_COLS])
        paths.append(p)
    return paths


_D, _V, _I, _L, _B = "DOUBLE", "VARCHAR", "INTEGER", "VARCHAR[]", "BOOLEAN"
_C = {"agency_code": _V, "fiscal_year": _I, "data_as_of": "TIMESTAMP", "card_id": _V}
_DRV = dict(_C, prior_count=_I, current_count=_I, count_change=_I, prior_dollars=_D, current_dollars=_D, dollars_change=_D, rank=_I)
COLUMN_TYPES = {
    "desk_natorg_cards": dict(_C, prior_year=_I, pct_change=_D, rest_pct_change=_D, cycle_gap_log=_D, flags=_L, caveat_keys=_L,
                              ojp_missing_awards=_I, raw_ratio=_D, dollar_change_same_rows=_D, group_prior=_D, group_current=_D, rest_prior=_D,
                              rest_current=_D, hq_other_prior=_D, hq_other_current=_D, excess=_D),
    "desk_natorg_caveats": dict(_C, sort=_I),
    "desk_natorg_series": dict(_C, year=_I, value=_D, index_value=_D),
    "desk_natorg_components": _DRV, "desk_natorg_programs": dict(_DRV, listing=_V, program_name=_V, name_source=_V),
    "desk_natorg_organizations": dict(_DRV, recipient_uei=_V, award_keys=_L, award_urls=_L),
    "desk_natorg_rows": dict(_C, award_key=_V, award_id=_V, new_award_date="DATE", component=_V, listing=_V, program_name=_V,
                             recipient_name=_V, recipient_uei=_V, recipient_type=_V, recipient_type_label=_V, recipient_state=_V,
                             n_awards=_I, amount=_D, usaspending_url=_V),
    "desk_natorg_scores": dict(_C, group_prior=_D, group_current=_D, rest_prior=_D, rest_current=_D, hq_other_prior=_D,
                               hq_other_current=_D, excess=_D),
    "desk_natorg_members": dict(_C, recipient_uei=_V, recipient_name=_V, rule_basis=_V, recipient_state=_V),
    "desk_natorg_text": {"agency_code": _V, "key": _V, "template": _V},
}
