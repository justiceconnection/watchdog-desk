"""Watchdog Desk, Card 4: states that stand out (internal name: state anomalies).

Method: docs/specs/watchdog-cards.md section 4 (4.2-4.6; 4.9 national organizations
used here only as an exclusion). A parameterized port of docs/specs/watchdog-cards-reference/card4_prototype.py.
- Rule and editorial parameters: sql/seeds/desk_card4_params.csv (per agency).
- Reader text (the spec's exact wording): sql/seeds/desk_card4_text.csv; edit wording there, not here.
- Per-card editorial overrides: sql/seeds/desk_card_overrides.csv.
- Target years and cut-offs come from mart_award_coverage, never hard-coded.
- Inputs (in memory, built by sql/marts/*.sql): _v2_award_new (metrics 7.7 new awards), _v2_tx (contractor-address
  shares), _sub_base (sub-awards with the metrics 8.1 default-exclusion flags), mart_award_coverage, _params.

Called by sql/build_marts.py (desk step). Creates in-memory tables desk_card4_*; the runner writes them to
marts/<agency>/desk/card4_*.parquet and one CSV per card to marts/<agency>/desk/csv/.
"""
from __future__ import annotations

import csv
import math
import statistics as S
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
URL = "https://www.usaspending.gov/award/{}/"
CAT_NOUN = {"assistance": "grant", "contract": "contract"}
CAT_PLURAL = {"assistance": "grants", "contract": "contracts"}
TYPE_NOUN = {"Contracts": "contract", "IDVs": "contract", "Grants": "grant", "Other assistance": "award"}
CARD_TYPE = "state_stand_out"   # internal id (renamed from state_anomaly)
STATUSES = ("card", "label", "hold", "evidence", "suppressed")


# ---------------------------------------------------------------- parameters and seeds
def _seed(name: str, agency: str) -> list[dict]:
    with open(ROOT / "sql" / "seeds" / name, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["agency_code"] == agency]


def load_params(agency: str) -> dict:
    p = {}
    for r in _seed("desk_card4_params.csv", agency):
        try:
            p[r["parameter"]] = float(r["value"])
        except ValueError:
            p[r["parameter"]] = r["value"]
    if not p:
        raise SystemExit(f"no desk_card4_params rows for agency {agency}")
    return p


def load_overrides(agency: str) -> dict:
    return {(int(r["fiscal_year"]), r["state"], r["award_category"], r["measure"]): r
            for r in _seed("desk_card_overrides.csv", agency) if r["card_type"] == CARD_TYPE}


def load_text(agency: str) -> dict:
    return {r["key"]: r["template"] for r in _seed("desk_card4_text.csv", agency)}


# ---------------------------------------------------------------- formatting
def money(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${a / 1e9:,.1f} billion"
    if a >= 1e6:
        return f"${a / 1e6:,.1f} million"
    return f"${a:,.0f}"


def amount(v: float, measure: str) -> str:
    if measure == "dollars":
        return money(v)
    n = int(round(v))
    return f"{n:,} award" + ("" if n == 1 else "s")


def pct(x: float) -> str:
    return f"{abs(x) * 100:,.0f}%"


def quantile_cont(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo = math.floor(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def short_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def words(p: dict, key: str) -> list[str]:
    return str(p.get(key, "") or "").split()


# ---------------------------------------------------------------- engine
class Card4:
    def __init__(self, con, agency: str, newaw: str = "_v2_award_new", tx: str = "_v2_tx"):
        self.con, self.ag, self.P = con, agency, load_params(agency)
        self.overrides = load_overrides(agency)
        self.text = load_text(agency)
        self.short_comp = {r["component"]: r["short_name"] for r in _seed("component_short_names.csv", agency)}
        # reader-text recipient names (spec 4.6); tables and CSVs keep the recorded names
        self.display = {r["recorded_name"]: r["display_name"] for r in _seed("recipient_display_names.csv", agency)}
        self.tx = tx
        P = self.P
        # national organizations (spec 4.9, rule as in the prototype): grant recipients whose modal recipient type is
        # non-government and (a) whose modal recipient state is the HQ state, or (b) whose sub-awards reach >= N states
        nongov = ", ".join(f"'{x}'" for x in words(P, "natorg_nongov_types")) or "NULL"
        rule = P.get("natorg_rule", "a_or_b")
        # modal type and modal state per recipient with EXPLICIT ties (spec 4.9): a recipient passes the
        # type test only if every tied modal type is non-government, and test (a) only if every tied modal state is the
        # HQ state. mt / mst hold a representative value (NULL when the test fails on a tie) for display.
        hq = str(P.get("natorg_hq_state", ""))
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _desk_rtype AS
            WITH base AS (SELECT recipient_uei AS u, recipient_type AS ty, recipient_state_raw AS st
                          FROM {newaw} WHERE definition = 'awarding' AND award_category = 'assistance' AND recipient_uei IS NOT NULL),
                 tc AS (SELECT u, ty, count(*) n FROM base WHERE ty IS NOT NULL GROUP BY 1, 2),
                 tm AS (SELECT u, ty FROM tc QUALIFY n = max(n) OVER (PARTITION BY u)),
                 tt AS (SELECT u, bool_and(ty IN ({nongov})) AS type_ok, count(*) AS n_tied_types, min(ty) AS mt FROM tm GROUP BY 1),
                 sc AS (SELECT u, st, count(*) n FROM base WHERE st IS NOT NULL GROUP BY 1, 2),
                 sm AS (SELECT u, st FROM sc QUALIFY n = max(n) OVER (PARTITION BY u)),
                 ss AS (SELECT u, bool_and(st = '{hq}') AS hq_ok, count(*) AS n_tied_states, min(st) AS mst FROM sm GROUP BY 1)
            SELECT u, tt.mt, ss.mst, coalesce(tt.type_ok, false) AS type_ok, coalesce(ss.hq_ok, false) AS hq_ok,
                   tt.n_tied_types, ss.n_tied_states
            FROM (SELECT DISTINCT u FROM base) b LEFT JOIN tt USING (u) LEFT JOIN ss USING (u)""")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _desk_natorg AS
            SELECT u AS recipient_uei, 'a' AS basis FROM _desk_rtype
            WHERE '{rule}' IN ('a_or_b', 'a_only') AND type_ok AND hq_ok
            UNION
            SELECT prime_awardee_uei, 'b' FROM subawards
            WHERE '{rule}' = 'a_or_b' AND agency_code = getvariable('agency') AND award_category = 'assistance'
              AND prime_awardee_uei IN (SELECT u FROM _desk_rtype WHERE type_ok)
            GROUP BY 1 HAVING count(DISTINCT subawardee_state_code) >= {int(P.get('natorg_min_sub_states', 5))}""")
        ex = " ".join(f"AND recipient_state_raw <> '{s}'" for s in words(P, "excluded_states"))
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _desk_nw AS
            SELECT award_key, award_id, award_category, award_type_group AS type_group, new_award_date AS new_dt,
                   new_award_fy AS fy, in_like_period, award_cycle, like_elapsed_flag, component, recipient_state_raw AS st,
                   pop_state, recipient_name, recipient_uei, listing, listing_title, recipient_type AS recip_type,
                   new_award_amount AS new_amt, new_award_transaction_key
            FROM {newaw}
            WHERE definition = 'awarding' AND recipient_state_raw IS NOT NULL {ex}
              AND NOT (award_category = 'assistance'
                       AND coalesce(recipient_uei, '') IN (SELECT recipient_uei FROM _desk_natorg WHERE recipient_uei IS NOT NULL))""")
        cov = con.execute("""SELECT award_category, fiscal_year, is_provisional, is_partial_year, has_reporting_gap, max_action_date
                             FROM mart_award_coverage WHERE definition = 'awarding' ORDER BY 1, 2""").fetchall()
        self.cov = {(r[0], r[1]): dict(prov=r[2], partial=r[3], gap=r[4], maxd=r[5]) for r in cov}
        self.short = (con.execute("SELECT abbreviation FROM _agency_names").fetchone() or [agency])[0]
        self.data_as_of = con.execute("SELECT data_as_of FROM _params").fetchone()[0]
        self.state_names = dict(con.execute("SELECT state_code, state_name FROM _seed_state_codes").fetchall())
        self.listing_names = dict(con.execute(
            "SELECT listing, display_name FROM read_csv('sql/seeds/listing_names.csv', header=true, all_varchar=true) "
            "WHERE agency_code = getvariable('agency')").fetchall())
        self.rtype = dict(con.execute(
            "SELECT code, label FROM read_csv('sql/seeds/recipient_type_labels.csv', header=true, all_varchar=true)").fetchall())
        self.cutoff = {cat: max(v["maxd"] for (c, y), v in self.cov.items() if c == cat and not v["partial"])
                       for cat in ("assistance", "contract")}
        # OJP gap note (4.6): FY-yy awards on OJP's own award list, by dashboard state, with no USAspending FAIN
        # (parameter ojp_dashboard_csv). Agencies without the file get no note.
        self.ojp_missing, self.ojp_year = None, None
        src = str(P.get("ojp_dashboard_csv", "") or "")
        if src and (ROOT / src).exists():
            self.ojp_year = int(P["ojp_gap_year"])
            yy = f"{self.ojp_year % 100:02d}"
            self.ojp_missing = dict(con.execute(f"""
                WITH d AS (SELECT replace("Award Number", '-', '') AS fain, "State" AS st,
                                  regexp_extract("NOFO Title", 'FY ?(20)?(\\d\\d)([^0-9]|$)', 2) AS yy
                           FROM read_csv('{src}', all_varchar = true, header = true)),
                     pa AS (SELECT DISTINCT award_id FROM prime_transactions
                            WHERE agency_code = getvariable('agency') AND award_category = 'assistance')
                SELECT st, count(DISTINCT fain) FROM d WHERE yy = '{yy}' AND fain NOT IN (SELECT award_id FROM pa) GROUP BY 1""").fetchall())

    # targets (4.4): the latest complete FY and any newer non-partial (provisional) FY, per category;
    # the award-cycle basis (evidence only) for complete grant years; partial years (FY2027) never scored.
    def plan(self):
        out = []
        for cat in ("assistance", "contract"):
            yrs = sorted(y for (c, y), v in self.cov.items() if c == cat and not v["partial"])
            complete = [y for y in yrs if not self.cov[(cat, y)]["prov"]]
            if not complete:
                continue
            for t in [max(complete)] + [y for y in yrs if y > max(complete)]:
                for measure in ("count", "dollars"):
                    out.append((cat, measure, "fy", t))
                    if cat == "assistance" and not self.cov[(cat, t)]["prov"]:
                        out.append((cat, measure, "cycle", t))
        return out

    def like_period(self, cat, t):
        return bool(self.cov[(cat, t)]["gap"])

    def where(self, cat, basis, t):
        """(SQL filter, year expression) for a series: same filters as the prototype's series() / where()."""
        w = f"award_category = '{cat}'"
        if cat == "contract":
            w += f" AND new_amt > {self.P['contract_min_amount']}"
        if basis == "fy":
            return w + (" AND in_like_period" if self.like_period(cat, t) else ""), "fy"
        return w + " AND award_cycle IS NOT NULL AND like_elapsed_flag", "award_cycle"

    def series(self, cat, measure, basis, t):
        w, yr = self.where(cat, basis, t)
        val = "count(*)" if measure == "count" else "sum(new_amt)"
        rows = self.con.execute(f"SELECT st, {yr} AS y, {val} FROM _desk_nw WHERE {w} AND {yr} IN (?, ?) GROUP BY ALL ORDER BY 1, 2",
                                [t - 1, t]).fetchall()
        d = {}
        for st, y, v in rows:
            d.setdefault(st, [0.0, 0.0])[0 if y == t - 1 else 1] = float(v or 0)
        return d

    def score(self, cat, measure, basis, t):
        P = self.P
        c = P["c_dollars" if measure == "dollars" else "c_counts"]
        size = P["size_dollars" if measure == "dollars" else "size_counts"]
        exc = P["excess_dollars" if measure == "dollars" else "excess_counts"]
        d = self.series(cat, measure, basis, t)
        if not d:
            return []
        totp = sum(v[0] for v in d.values())
        totc = sum(v[1] for v in d.values())
        out = []
        for st, (p, q) in sorted(d.items()):
            np_, nq = totp - p, totc - q
            R = math.log((max(nq, 0) + c) / (max(np_, 0) + c))
            r = math.log((max(q, 0) + c) / (max(p, 0) + c))
            out.append(dict(state=st, prior=p, current=q, r=r, R=R, gap=r - R, excess=q - p * math.exp(R),
                            nat_prior=totp, nat_current=totc, passes_size=max(p, q) >= size))
        devs = [o["gap"] for o in out if o["passes_size"]]
        scored = len(devs) >= P["min_states"]
        med = S.median(devs) if devs else None
        scale = max(1.4826 * S.median([abs(x - med) for x in devs]), P["s_min"]) if devs else None
        for o in out:
            o.update(award_category=cat, measure=measure, basis=basis, fiscal_year=t, n_states_scored=len(devs),
                     median_gap=med, scale=scale, z=((o["gap"] - med) / scale) if scored else None,
                     passes_excess=abs(o["excess"]) >= exc)
            opp = (o["r"] * o["R"] < 0) and abs(o["r"]) >= P["opp_min"] and abs(o["R"]) >= P["nat_min"]
            far = scored and abs(o["z"]) >= P["z_far"]
            cand = scored and o["passes_size"] and o["passes_excess"] and (opp or far)
            o["trigger"] = (("opposite" if opp else "") + ("+" if opp and far else "") + ("far" if far else "")) if cand else None
            o["is_candidate"] = cand
        return out

    # ------------------------------------------------------------ labels and status (4.4, 4.5)
    def driver(self, o):
        cat, t = o["award_category"], o["fiscal_year"]
        w, yr = self.where(cat, o["basis"], t)
        val = "sum(new_amt)" if o["measure"] == "dollars" else "count(*)"
        change = o["current"] - o["prior"]
        for by in (["award_key", "recipient_name"] if o["measure"] == "dollars" else ["recipient_name"]):
            row = self.con.execute(
                f"""SELECT {by}, coalesce({val} FILTER (WHERE {yr} = ?), 0) - coalesce({val} FILTER (WHERE {yr} = ?), 0) AS d,
                           coalesce({val} FILTER (WHERE {yr} = ?), 0) AS v_cur, coalesce({val} FILTER (WHERE {yr} = ?), 0) AS v_prior
                    FROM _desk_nw WHERE {w} AND st = ? AND {yr} IN (?, ?) GROUP BY 1 ORDER BY abs(d) DESC, 1 LIMIT 1""",
                [t, t - 1, t, t - 1, o["state"], t - 1, t]).fetchone()
            if row and change and row[1] * change > 0 and abs(row[1]) / abs(change) >= self.P["concentration_share"]:
                kind = "one_award" if by == "award_key" else "one_recipient"
                gain = change > 0
                d = dict(driver_kind=kind, driver_key=row[0], driver_recipient=row[0], driver_share=abs(row[1]) / abs(change),
                         driver_change=row[1], driver_value=row[2] if gain else row[3], driver_year=t if gain else t - 1,
                         driver_award_url=None, driver_component=None, driver_award_type=None)
                if kind == "one_award":
                    rn, comp, tg = self.con.execute("SELECT recipient_name, component, type_group FROM _desk_nw WHERE award_key = ?",
                                                    [row[0]]).fetchone()
                    d.update(driver_recipient=rn, driver_component=comp, driver_award_type=TYPE_NOUN.get(tg, CAT_NOUN[cat]),
                             driver_award_url=URL.format(row[0]))
                return d
        return dict(driver_kind=None, driver_key=None, driver_recipient=None, driver_share=None, driver_change=None,
                    driver_value=None, driver_year=None, driver_award_url=None, driver_component=None, driver_award_type=None)

    def evaluate(self, o, idx):
        """Flags and the prototype's status for one candidate (fiscal-year or award-cycle basis)."""
        P = self.P
        cat, t, st, m, basis = o["award_category"], o["fiscal_year"], o["state"], o["measure"], o["basis"]
        c = dict(o)
        c.update(self.driver(o))
        flags = [c["driver_kind"]] if c["driver_kind"] else []
        w, yr = self.where(cat, basis, t)
        c.update(caveat_cell_share=None, caveat_base_share=None, cycle_z=None, state_agency_share=None, state_agency_dollars=None, subaward_floor=None, subaward_recipients=None,
                 contractor_address_share=None, contractor_address_base=None, pop_in_state_share=None)
        if cat == "assistance" and basis == "fy":
            if self.like_period(cat, t):
                flags.append("gap_year")
            elif not self.cov[(cat, t)]["prov"]:
                zc = idx.get((cat, m, "cycle", t, st))
                c["cycle_z"] = zc["z"] if zc else None
                ok = zc is not None and zc["z"] is not None and zc["z"] * o["z"] > 0 and abs(zc["z"]) >= P["cycle_confirm_z"]
                flags.append("cycle_confirmed" if ok else "timing?")
            c["state_agency_share"], c["state_agency_dollars"] = self.con.execute(
                f"""SELECT sum(new_amt) FILTER (WHERE recip_type = 'A') / nullif(sum(new_amt), 0), sum(new_amt) FILTER (WHERE recip_type = 'A')
                    FROM _desk_nw WHERE {w} AND st = ? AND {yr} = ?""", [st, t]).fetchone()
            # 4.6 pass-through: sub-awards (any action date to the data date) under the card's current-period type-A new
            # awards, after the metrics 8.1 default exclusions; n = distinct sub-recipient UEIs. Self-reported: a floor.
            c["subaward_floor"], c["subaward_recipients"] = self.con.execute(
                f"""SELECT coalesce(sum(s.subaward_amount), 0), count(DISTINCT s.subawardee_uei) FROM _sub_base s
                    WHERE s.definition = 'awarding' AND NOT s.is_resubmitted_duplicate AND NOT s.is_outlier
                      AND s.prime_award_unique_key IN (SELECT award_key FROM _desk_nw WHERE {w} AND st = ? AND {yr} = ? AND recip_type = 'A')""",
                [st, t]).fetchone()
        if cat == "contract":
            ca = self.con.execute(
                f"""SELECT sum(abs(amt)) FILTER (WHERE pop_is_contractor_address) / nullif(sum(abs(amt)), 0)
                    FROM {self.tx} WHERE award_category = 'contract' AND st = ? AND fiscal_year = ?""", [st, t]).fetchone()[0] or 0
            base = self.base_ca.get(t, 0) or 0
            c["contractor_address_share"], c["contractor_address_base"] = ca, base
            flags.append("contractor_address" if ca >= min(base + P["ca_margin"], P["ca_cap"]) else "pop_caveat")
            # 4.6: share of the card's current-period new-award dollars recorded as performed in the state
            c["pop_in_state_share"] = self.con.execute(
                f"""SELECT sum(new_amt) FILTER (WHERE pop_state = st) / nullif(sum(new_amt), 0)
                    FROM _desk_nw WHERE {w} AND st = ? AND {yr} = ?""", [st, t]).fetchone()[0]
            # caveat numbers: on the card's own new-award dollars, the same base as pop_in.
            # {cell}: share whose new-award transaction has PoP ZIP+4 = contractor ZIP+4; {base}: the same over every
            # agency contract new award in the size band that FY. (The contractor_address flag keeps the trend-signals base.)
            c["caveat_cell_share"] = self.con.execute(
                f"""SELECT sum(n.new_amt) FILTER (WHERE x.pop_is_contractor_address) / nullif(sum(n.new_amt), 0)
                    FROM _desk_nw n LEFT JOIN {self.tx} x ON x.transaction_key = n.new_award_transaction_key
                    WHERE {w.replace('award_category', 'n.award_category').replace('new_amt', 'n.new_amt').replace('in_like_period', 'n.in_like_period')}
                      AND n.st = ? AND n.{yr} = ?""", [st, t]).fetchone()[0] or 0
            c["caveat_base_share"] = self.base_new.get(t, 0) or 0
        c["flags"] = flags
        rule = ("evidence" if basis == "cycle"                      # cycle rows never stand alone (spec 4.2: evidence only)
                else "hold" if "timing?" in flags
                else "label" if any(f in ("one_award", "one_recipient", "contractor_address", "gap_year") for f in flags) else "card")
        c["dollar_change_same_rows"] = None
        if m == "count":
            dp, dc = self.con.execute(f"""SELECT coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0), coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0)
                                          FROM _desk_nw WHERE {w} AND st = ?""", [t - 1, t, st]).fetchone()
            c["dollar_change_same_rows"] = dc - dp
            if rule != "evidence" and P["count_card_min_dollar_change"] > 0 and abs(dc - dp) < P["count_card_min_dollar_change"]:
                rule = "suppressed"
        c["rule_status"] = rule
        return c

    def run(self):
        P = self.P
        self.base_new = dict(self.con.execute(
            f"""SELECT a.new_award_fy, sum(a.new_award_amount) FILTER (WHERE x.pop_is_contractor_address) / sum(a.new_award_amount)
                FROM _v2_award_new a LEFT JOIN {self.tx} x ON x.transaction_key = a.new_award_transaction_key
                WHERE a.definition = 'awarding' AND a.award_category = 'contract' AND a.new_award_amount > {P['contract_min_amount']}
                GROUP BY 1""").fetchall())
        self.base_ca = dict(self.con.execute(
            f"""SELECT fiscal_year, sum(abs(amt)) FILTER (WHERE pop_is_contractor_address) / sum(abs(amt))
                FROM {self.tx} WHERE award_category = 'contract' GROUP BY 1""").fetchall())
        scores = []
        for cat, measure, basis, t in self.plan():
            scores += self.score(cat, measure, basis, t)
        self.scores = scores
        self.idx = idx = {(o["award_category"], o["measure"], o["basis"], o["fiscal_year"], o["state"]): o for o in scores}
        self.ev = {k: self.evaluate(o, idx) for k, o in idx.items() if o["is_candidate"]}
        cards = []
        for key in sorted((k for k in self.ev if k[2] == "fy"), key=lambda k: (k[3], k[0], k[4], k[1])):
            c = self.ev[key]
            cat, m, _, t, st = key
            reasons = [f for f in c["flags"] if f in ("timing?", "gap_year", "one_award", "one_recipient", "contractor_address")]
            status = c["rule_status"]
            if status == "suppressed":
                reasons.append("dollar_change_under_minimum")
            elif status != "hold":   # editorial switches (4.8 answers live in the params seed)
                if "gap_year" in c["flags"] and P["gap_year_grant_status"] == "hold":
                    status = "hold"
                if c["driver_kind"] and P["one_award_status"] == "hold":
                    status = "hold"
            ov = self.overrides.get((t, st, cat, m)) or {}
            c["editorial_question"] = ov.get("editorial_question") or None
            c["override_reason"] = ov.get("reason") or None
            c["override_wording"] = ov.get("wording") or None
            c["override_label_text"] = ov.get("label_text") or None
            if ov.get("status"):
                if ov["status"] not in STATUSES:
                    raise SystemExit(f"desk_card_overrides: bad status {ov['status']!r}")
                status = ov["status"]
                reasons.append(ov.get("reason_code") or "manual_override")
            c.update(status=status, status_reasons=reasons, card_id=f"card4-{self.ag}-{t}-{st}-{cat}-{m}")
            self.render(c)
            cards.append(c)
        self.cards = cards
        return cards

    # ------------------------------------------------------------ reader text (4.6); templates in the text seed
    def T(self, key, **kw):
        if key not in self.text:
            raise SystemExit(f"desk_card4_text: missing key {key!r} for agency {self.ag}")
        return self.text[key].format(**kw)

    def period(self, cat, t):
        if cat == "assistance" and self.like_period(cat, t):
            return self.T("period_gap", t=t, cut_month=self.cutoff[cat].strftime("%B"))
        if self.cov[(cat, t)]["prov"]:
            return self.T("period_provisional", t=t)
        return self.T("period_complete", t=t)

    def band(self, cat, m, t):
        size = self.P["size_dollars" if m == "dollars" else "size_counts"]
        g = [100 * ((o["current"] / o["prior"] - 1) - ((o["nat_current"] - o["current"]) / (o["nat_prior"] - o["prior"]) - 1))
             for o in self.scores
             if (o["award_category"], o["measure"], o["basis"], o["fiscal_year"]) == (cat, m, "fy", t)
             and o["passes_size"] and o["prior"] >= size and o["nat_prior"] - o["prior"] > 0]
        return quantile_cont(g, self.P["band_lo_pct"] / 100), quantile_cont(g, self.P["band_hi_pct"] / 100)

    def render(self, c):
        P = self.P
        cat, m, t, st = c["award_category"], c["measure"], c["fiscal_year"], c["state"]
        name = self.state_names.get(st, st)
        size = P["size_dollars" if m == "dollars" else "size_counts"]
        noun, mw = CAT_NOUN[cat], ("dollars" if m == "dollars" else "awards")
        rest_p, rest_c = c["nat_prior"] - c["prior"], c["nat_current"] - c["current"]
        c["state_name"] = name
        c["period_label"] = self.period(cat, t)
        c["prior_year"] = t - 1
        # no percent when the prior value is below the size floor (4.6 "small prior base")
        c["pct_change"] = (c["current"] / c["prior"] - 1) if c["prior"] >= size and c["prior"] > 0 else None
        c["rest_prior"], c["rest_current"] = rest_p, rest_c
        c["rest_pct_change"] = (rest_c / rest_p - 1) if rest_p > 0 else None
        c["direction_case"] = "opposite" if "opposite" in c["trigger"] else "same_or_far"
        up = c["current"] > c["prior"]
        based_in = "contractor_address" in c["flags"] or c.get("override_wording") == "contractors_based_in"
        subj = self.T("subject_contractors" if based_in else "subject_state", state=name)
        q = c["rest_pct_change"] or 0.0
        kw = dict(subject=subj, agency=self.short, noun=noun, measure_word=mw, period=c["period_label"], verb="rose" if up else "fell",
                  pct=pct(c["pct_change"] or 0), prior=amount(c["prior"], m), current=amount(c["current"], m), t_prior=t - 1,
                  rest_pct=pct(q), rest_dir_noun="rise" if q > 0 else "fall", rest_verb="rose" if q > 0 else "fell")
        if c["pct_change"] is None:
            c["headline_case"] = "small_base"
        elif c["direction_case"] == "opposite":
            c["headline_case"] = "opposite"
        elif round(abs(q) * 100) == 0:
            c["headline_case"] = "same_flat"
        else:
            c["headline_case"] = "fell_more" if not up else "rose_more"
        c["headline"] = self.T("headline_" + c["headline_case"], **kw)
        # label sentence for one_award / one_recipient (4.5), naming the award or recipient
        c["label_text"], c["driver_share_display"] = c.get("override_label_text"), None
        if c["driver_kind"]:
            share = c["driver_share"]
            c["driver_share_display"] = "100%+" if share > 1 else f"{share * 100:.0f}%"
            lost = c["driver_change"] < 0
            lead = self.T("label_lead_over" if share > 1 else "label_lead")
            key = f"label_{'award' if c['driver_kind'] == 'one_award' else 'recipient'}_{'lost' if lost else 'new'}" + ("_count" if m == "count" else "")
            c["label_text"] = c.get("override_label_text") or self.T(key, lead=lead, component=self.short_comp.get(c["driver_component"], c["driver_component"] or ""), award_type=c["driver_award_type"] or noun,
                                     recipient=self.display.get(c["driver_recipient"], c["driver_recipient"]), year=c["driver_year"], next_year=c["driver_year"] + 1,
                                     amount=amount(c["driver_value"], m), n=int(round(c["driver_value"])), noun=noun)
        # why it stands out (4.6 item 2). Gap = state % change minus rest-of-country % change (undamped, percentage
        # points), over floor-passing states with a prior value at the size floor; the quoted band edge is the one on
        # the card's side (10th percentile for a fall, 90th for a rise), because the spread is skewed.
        lo, hi = self.band(cat, m, t)
        c["gap_pts"] = (100 * (c["pct_change"] - c["rest_pct_change"])) if c["pct_change"] is not None and c["rest_pct_change"] is not None else None
        side_up = (c["gap_pts"] if c["gap_pts"] is not None else c["gap"]) > 0
        band = None if lo is None else abs(hi if side_up else lo)
        c["band_lo_pts"], c["band_hi_pts"], c["band_pts"] = lo, hi, band
        c["gap_outside_band"] = (None if band is None or c["gap_pts"] is None
                                 else (c["gap_pts"] > hi if side_up else c["gap_pts"] < lo))
        parts = []
        if "far" in c["trigger"] and band is not None:
            parts.append(self.T("why_pts", band=f"{band:,.0f}", state=name, gap=f"{abs(c['gap_pts']):,.0f}",
                                above_below="above" if side_up else "below") if c["gap_pts"] is not None
                         else self.T("why_small_base", state=name, t_prior=t - 1, rise_fall="rise" if up else "fall"))
        if c["direction_case"] == "opposite":
            parts.append(self.T("why_opposite"))
        c["why_text"] = " ".join(parts)
        c["fixed_line"] = self.T("fixed_line")
        # caveats (4.6 item 6), in display order; keys and text
        cav = []
        if cat == "assistance" and self.ojp_missing is not None:
            k = self.ojp_missing.get(st, 0)
            cav.append(("ojp_gap", self.T("caveat_ojp_gap" if k else "caveat_ojp_gap_zero", k=f"{k:,}", y=self.ojp_year, state=name)))
        c["ojp_missing_awards"] = self.ojp_missing.get(st, 0) if (cat == "assistance" and self.ojp_missing is not None) else None
        if cat == "assistance" and self.like_period(cat, t):
            cut = self.cutoff[cat]
            cav.append(("grant_cutoff", self.T("caveat_grant_cutoff", t=t, t_prior=t - 1, cut_long=long_date(cut), cut_month=cut.strftime("%B"))))
        if cat == "assistance" and (c["state_agency_share"] or 0) >= P["pass_through_min_share"]:
            share = f"{c['state_agency_share'] * 100:.0f}"
            if (c["subaward_floor"] or 0) > 0:
                cav.append(("pass_through", self.T("caveat_pass_through", x=share, state=name, y=money(c["subaward_floor"]),
                                                   n=f"{c['subaward_recipients']:,}")))
            else:
                cav.append(("pass_through", self.T("caveat_pass_through_none", x=share, state=name)))
        if cat == "contract":
            cav.append(("contractor_address", self.T("caveat_contractor_address", state=name, agency=self.short, t=t,
                                                     cell=f"{c['caveat_cell_share'] * 100:.0f}",
                                                     base=f"{c['caveat_base_share'] * 100:.0f}",
                                                     pop_in=f"{(c['pop_in_state_share'] or 0) * 100:.0f}")))
            if self.cov[(cat, t)]["prov"]:
                cav.append(("provisional_contracts", self.T("caveat_provisional_contracts", t=t, through=short_date(self.cov[(cat, t)]["maxd"]))))
        c["caveat_keys"] = [k for k, _ in cav]
        c["caveats"] = cav

    # ------------------------------------------------------------ outputs
    def tables(self):
        """Returns ({table_name: rows}, {card_id: (csv header lines, rows)})."""
        ag, asof = self.ag, self.data_as_of
        cards, series, comps, progs, recips, rows, cavs = [], [], [], [], [], [], []
        idx = self.idx
        csvs = {}
        for c in self.cards:
            cid, cat, m, t, st = c["card_id"], c["award_category"], c["measure"], c["fiscal_year"], c["state"]
            cards.append({
                "agency_code": ag, "card_id": cid, "card_type": CARD_TYPE, "fiscal_year": t, "prior_year": t - 1,
                "period_label": c["period_label"], "award_category": cat, "category_label": CAT_PLURAL[cat], "measure": m,
                "basis": "fy", "like_period": self.like_period(cat, t), "is_provisional": bool(self.cov[(cat, t)]["prov"]),
                "state": st, "state_name": c["state_name"],
                "prior_value": c["prior"], "current_value": c["current"], "change": c["current"] - c["prior"],
                "pct_change": c["pct_change"], "rest_prior": c["rest_prior"], "rest_current": c["rest_current"],
                "rest_pct_change": c["rest_pct_change"], "national_prior": c["nat_prior"], "national_current": c["nat_current"],
                "r_log": c["r"], "rest_r_log": c["R"], "gap_log": c["gap"], "z": c["z"], "cycle_z": c["cycle_z"],
                "excess": c["excess"], "trigger": c["trigger"], "direction_case": c["direction_case"], "headline_case": c["headline_case"],
                "gap_pts": c["gap_pts"], "gap_outside_band": c["gap_outside_band"], "band_lo_pts": c["band_lo_pts"],
                "band_hi_pts": c["band_hi_pts"], "band_pts": c["band_pts"],
                "flags": c["flags"], "rule_status": c["rule_status"], "status": c["status"], "status_reasons": c["status_reasons"],
                "editorial_question": c["editorial_question"], "override_reason": c["override_reason"], "override_wording": c["override_wording"],
                "driver_kind": c["driver_kind"], "driver_key": c["driver_key"], "driver_recipient": c["driver_recipient"],
                "driver_display_name": self.display.get(c["driver_recipient"], c["driver_recipient"]) if c["driver_recipient"] else None,
                "driver_component": c["driver_component"], "driver_award_type": c["driver_award_type"],
                "driver_share": c["driver_share"], "driver_share_display": c["driver_share_display"], "driver_change": c["driver_change"],
                "driver_value": c["driver_value"], "driver_year": c["driver_year"], "driver_award_url": c["driver_award_url"],
                "state_agency_share": c["state_agency_share"], "state_agency_dollars": c["state_agency_dollars"],
                "subaward_floor": c["subaward_floor"], "subaward_recipients": c["subaward_recipients"],
                # caveat numbers (card's new-award dollars) vs the flag's trend-signals base (all contract transactions)
                "contractor_address_share": c["caveat_cell_share"], "contractor_address_base": c["caveat_base_share"],
                "contractor_address_flag_share": c["contractor_address_share"], "contractor_address_flag_base": c["contractor_address_base"],
                "pop_in_state_share": c["pop_in_state_share"], "ojp_missing_awards": c["ojp_missing_awards"],
                "dollar_change_same_rows": c["dollar_change_same_rows"],
                "headline": c["headline"], "label_text": c["label_text"], "why_text": c["why_text"], "fixed_line": c["fixed_line"],
                "caveat_keys": c["caveat_keys"], "csv_path": f"desk/csv/{cid}.csv",
                "method_ref": "docs/specs/watchdog-cards.md 4.2-4.6; docs/metrics.md 7.7, 7.4; sql/desk/card4.py",
                "data_as_of": asof})
            for i, (k, txt) in enumerate(c["caveats"]):
                cavs.append({"agency_code": ag, "card_id": cid, "sort": i + 1, "caveat_key": k, "text": txt, "data_as_of": asof})
            # chart (4.6 item 4): state and rest of the country, prior year = 100; grants add the award-cycle evidence panel
            panels = [("fiscal_year", "fy", "Fiscal year")]
            if (cat, m, "cycle", t, st) in idx:
                panels.append(("award_cycle", "cycle", "Award cycle (evidence)"))
            for panel, basis, plabel in panels:
                o = idx[(cat, m, basis, t, st)]
                for ent, p, q in (("state", o["prior"], o["current"]), ("rest", o["nat_prior"] - o["prior"], o["nat_current"] - o["current"])):
                    for role, y, v in (("prior", t - 1, p), ("current", t, q)):
                        lbl = f"FY{y}" if basis == "fy" else f"FY{y} award cycle"
                        if basis == "fy" and self.like_period(cat, t):
                            lbl += f" (Oct–{self.cutoff[cat].strftime('%b')})"
                        series.append({"agency_code": ag, "card_id": cid, "panel": panel, "panel_label": plabel, "entity": ent,
                                       "entity_label": c["state_name"] if ent == "state" else "Rest of the country",
                                       "year_role": role, "year": y, "period_label": lbl, "value": v,
                                       "index_value": (100.0 * v / p) if p > 0 else None,
                                       "is_provisional": bool(basis == "fy" and self.cov.get((cat, y), {}).get("prov")),
                                       "z": o["z"], "data_as_of": asof})
            # rows behind the card (4.6 item 7)
            w, yr = self.where(cat, "fy", t)
            r = self.con.execute(f"""SELECT {yr} AS y, award_key, award_id, new_dt, component, listing, listing_title,
                                            recipient_name, recipient_uei, recip_type, pop_state, new_amt
                                     FROM _desk_nw WHERE {w} AND st = ? AND {yr} IN (?, ?) ORDER BY y, new_dt, award_key""",
                                 [st, t - 1, t]).fetchall()
            card_rows = []
            for y, ak, aid, nd, comp, lst, ltitle, rn, ru, rt, pop, amt in r:
                card_rows.append({"agency_code": ag, "card_id": cid, "row_kind": "award", "year_role": "current" if y == t else "prior",
                                  "fiscal_year": y, "award_key": ak, "award_id": aid, "new_award_date": nd, "component": comp,
                                  "listing": lst if cat == "assistance" else None,
                                  "program_name": (self.listing_names.get(lst) or ltitle) if cat == "assistance" else None,
                                  "recipient_name": rn, "recipient_uei": ru, "recipient_type": rt,
                                  "recipient_type_label": self.rtype.get(rt) if rt else None, "pop_state": pop,
                                  "n_awards": 1, "amount": amt, "usaspending_url": URL.format(ak), "data_as_of": asof})
            dol = idx.get((cat, "dollars", "fy", t, st))
            cnt = idx.get((cat, "count", "fy", t, st))
            for kind, lab in (("state_total", c["state_name"]), ("rest_total", "Rest of the country")):
                for role, y, i in (("prior", t - 1, 0), ("current", t, 1)):
                    def pick(src):
                        if not src:
                            return None
                        s = (src["prior"], src["current"])[i]
                        return s if kind == "state_total" else (src["nat_prior"], src["nat_current"])[i] - s
                    card_rows.append({"agency_code": ag, "card_id": cid, "row_kind": kind, "year_role": role, "fiscal_year": y,
                                      "award_key": None, "award_id": None, "new_award_date": None, "component": None, "listing": None,
                                      "program_name": None, "recipient_name": lab, "recipient_uei": None, "recipient_type": None,
                                      "recipient_type_label": None, "pop_state": None,
                                      "n_awards": int(round(pick(cnt))) if cnt else None,
                                      "amount": pick(dol), "usaspending_url": None, "data_as_of": asof})
            rows += card_rows
            csvs[cid] = (self.csv_header(c), card_rows)
            comps += self.drivers(c, "component", "component", None)
            if cat == "assistance":
                progs += self.drivers(c, "listing", "listing", None)
            recips += self.drivers(c, "recipient_name", "recipient", int(self.P["top_recipients"]))
        params = [{"agency_code": ag, "parameter": k, "value": str(v)} for k, v in sorted(self.P.items())]
        scores = []
        for o in self.scores:
            e = self.ev.get((o["award_category"], o["measure"], o["basis"], o["fiscal_year"], o["state"]))
            scores.append({
                "agency_code": ag, "fiscal_year": o["fiscal_year"], "award_category": o["award_category"],
                "measure": o["measure"], "basis": o["basis"],
                "like_period": bool(o["basis"] == "fy" and self.like_period(o["award_category"], o["fiscal_year"])),
                "state": o["state"], "prior_value": o["prior"], "current_value": o["current"],
                "national_prior": o["nat_prior"], "national_current": o["nat_current"], "r_log": o["r"], "rest_r_log": o["R"],
                "gap_log": o["gap"], "median_gap": o["median_gap"], "scale": o["scale"], "n_states_scored": o["n_states_scored"],
                "z": o["z"], "excess": o["excess"], "passes_size": o["passes_size"], "passes_excess": o["passes_excess"],
                "trigger": o["trigger"], "is_candidate": o["is_candidate"],
                "flags": e["flags"] if e else None, "rule_status": e["rule_status"] if e else None,
                "driver_kind": e["driver_kind"] if e else None, "driver_key": e["driver_key"] if e else None,
                "driver_share": e["driver_share"] if e else None,
                "state_agency_share": e["state_agency_share"] if e else None,
                "contractor_address_share": e["contractor_address_share"] if e else None,
                "card_id": (f"card4-{ag}-{o['fiscal_year']}-{o['state']}-{o['award_category']}-{o['measure']}"
                            if e and o["basis"] == "fy" else None),
                "data_as_of": asof})
        nat = [{"agency_code": ag, "recipient_uei": u, "recipient_name": n, "rule_basis": b, "data_as_of": asof}
               for u, n, b in self.con.execute("""
                   SELECT o.recipient_uei, (SELECT min(recipient_name) FROM _v2_award_new a WHERE a.recipient_uei = o.recipient_uei),
                          string_agg(DISTINCT basis, '+' ORDER BY basis)
                   FROM _desk_natorg o GROUP BY 1 ORDER BY 1""").fetchall()]
        text = [{"agency_code": ag, "key": k, "template": v} for k, v in sorted(self.text.items())]
        return dict(desk_card4_cards=cards, desk_card4_caveats=cavs, desk_card4_series=series,
                    desk_card4_components=comps, desk_card4_programs=progs, desk_card4_recipients=recips,
                    desk_card4_rows=rows, desk_card4_scores=scores, desk_card4_params=params, desk_card4_text=text,
                    desk_card4_national_orgs=nat), csvs

    def drivers(self, c, col, kind, top):
        cid, cat, m, t, st = c["card_id"], c["award_category"], c["measure"], c["fiscal_year"], c["state"]
        w, yr = self.where(cat, "fy", t)
        key = "dollars_change" if m == "dollars" else "count_change"
        rows = self.con.execute(f"""
            SELECT {col} AS k, min(listing_title) AS lt, min(recipient_uei) AS uei,
                   count(*) FILTER (WHERE {yr} = ?) AS pc, count(*) FILTER (WHERE {yr} = ?) AS cc,
                   coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0) AS pd, coalesce(sum(new_amt) FILTER (WHERE {yr} = ?), 0) AS cd,
                   list(award_key ORDER BY abs(new_amt) DESC, award_key)[1:5] AS aw
            FROM _desk_nw WHERE {w} AND st = ? AND {yr} IN (?, ?) GROUP BY 1""",
            [t - 1, t, t - 1, t, st, t - 1, t]).fetchall()
        out = []
        for k, lt, uei, pc, cc, pd, cd, aw in rows:
            d = dict(agency_code=self.ag, card_id=cid, prior_count=int(pc), current_count=int(cc), count_change=int(cc - pc),
                     prior_dollars=pd, current_dollars=cd, dollars_change=cd - pd)
            if kind == "component":
                d = dict(d, component=k)
            elif kind == "listing":
                d = dict(d, listing=k, program_name=self.listing_names.get(k) or lt,
                         name_source="listing_names seed" if k in self.listing_names else "assistance listing title")
            else:
                d = dict(d, recipient_name=k, recipient_uei=uei, award_keys=list(aw), award_urls=[URL.format(a) for a in aw])
            out.append(d)
        out.sort(key=lambda d: (-abs(d[key]), -abs(d["dollars_change"]), str(d.get("component") or d.get("listing") or d.get("recipient_name"))))
        out = out[:top] if top else out
        for i, d in enumerate(out):
            d["rank"] = i + 1
            d["data_as_of"] = self.data_as_of
        return out

    def csv_header(self, c):
        cat, t = c["award_category"], c["fiscal_year"]
        rows = (f"Rows: every new {CAT_NOUN[cat]} award (metrics 7.7) to recipients in {c['state_name']} in FY{t - 1} and FY{t}"
                + (f", October–{self.cutoff[cat].strftime('%B')} only in both years" if self.like_period(cat, t) else "")
                + (f"; contracts over ${self.P['contract_min_amount']:,.0f} only" if cat == "contract" else "")
                + ("; national organizations excluded (spec 4.9)" if cat == "assistance" else "")
                + "; plus state and rest-of-country totals (rest of the country excludes "
                + (" ".join(words(self.P, "excluded_states")) or "no states") + ").")
        lines = [f"{c['headline']}" + (f" {c['label_text']}" if c["label_text"] else ""),
                 rows,
                 f"Definition: awarding agency {self.ag} ({self.short}); state = recipient state of the new-award transaction; "
                 f"amount = initial award amount (obligations on the new-award date); fiscal year of the new-award date; nominal dollars.",
                 f"Source: USAspending prime award transactions; data as of {str(self.data_as_of)[:10]}. Card {c['card_id']}.",
                 c["fixed_line"]]
        lines += [f"Caveat: {txt}" for _, txt in c["caveats"]]
        return lines


CSV_COLS = ["row_kind", "year_role", "fiscal_year", "award_key", "award_id", "new_award_date", "component", "listing", "program_name",
            "recipient_name", "recipient_uei", "recipient_type", "recipient_type_label", "pop_state", "n_awards", "amount", "usaspending_url"]


def write_csvs(csvs: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("card4-*.csv"):
        old.unlink()
    paths = []
    for cid in sorted(csvs):
        header, rows = csvs[cid]
        p = out_dir / f"{cid}.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            for line in header:
                f.write("# " + line.replace("\n", " ") + "\n")
            w = csv.writer(f, lineterminator="\n")
            w.writerow(CSV_COLS)
            for r in rows:
                w.writerow(["" if r[k] is None else (f"{r[k]:.2f}" if k == "amount" else r[k]) for k in CSV_COLS])
        paths.append(p)
    return paths


# Explicit types for columns that can be all-null (the runner infers the rest).
_D, _V, _I, _L, _B = "DOUBLE", "VARCHAR", "INTEGER", "VARCHAR[]", "BOOLEAN"
_COMMON = {"fiscal_year": _I, "data_as_of": "TIMESTAMP", "agency_code": _V, "card_id": _V}
COLUMN_TYPES = {
    "desk_card4_cards": dict(_COMMON, prior_year=_I, pct_change=_D, rest_pct_change=_D, z=_D, cycle_z=_D, gap_pts=_D,
                             band_lo_pts=_D, band_hi_pts=_D, band_pts=_D, gap_outside_band=_B, flags=_L, status_reasons=_L,
                             caveat_keys=_L, editorial_question=_V, override_reason=_V, override_wording=_V, driver_kind=_V,
                             driver_key=_V, driver_recipient=_V, driver_display_name=_V, driver_component=_V, driver_award_type=_V, driver_share=_D,
                             driver_share_display=_V, driver_change=_D, driver_value=_D, driver_year=_I, driver_award_url=_V,
                             state_agency_share=_D, state_agency_dollars=_D, subaward_floor=_D, subaward_recipients=_I,
                             contractor_address_share=_D, contractor_address_base=_D, pop_in_state_share=_D,
                             contractor_address_flag_share=_D, contractor_address_flag_base=_D,
                             ojp_missing_awards=_I, dollar_change_same_rows=_D, label_text=_V,
                             prior_value=_D, current_value=_D, change=_D, rest_prior=_D, rest_current=_D,
                             national_prior=_D, national_current=_D, excess=_D),
    "desk_card4_caveats": dict(_COMMON, sort=_I),
    "desk_card4_series": dict(_COMMON, year=_I, value=_D, index_value=_D, z=_D),
    "desk_card4_components": dict(_COMMON, prior_count=_I, current_count=_I, count_change=_I, prior_dollars=_D,
                                  current_dollars=_D, dollars_change=_D, rank=_I),
    "desk_card4_programs": dict(_COMMON, listing=_V, program_name=_V, name_source=_V, prior_count=_I, current_count=_I,
                                count_change=_I, prior_dollars=_D, current_dollars=_D, dollars_change=_D, rank=_I),
    "desk_card4_recipients": dict(_COMMON, recipient_name=_V, recipient_uei=_V, award_keys=_L, award_urls=_L, prior_count=_I,
                                  current_count=_I, count_change=_I, prior_dollars=_D, current_dollars=_D, dollars_change=_D, rank=_I),
    "desk_card4_rows": dict(_COMMON, award_key=_V, award_id=_V, new_award_date="DATE", component=_V, listing=_V,
                            program_name=_V, recipient_name=_V, recipient_uei=_V, recipient_type=_V, recipient_type_label=_V,
                            pop_state=_V, n_awards=_I, amount=_D, usaspending_url=_V),
    "desk_card4_scores": dict(_COMMON, prior_value=_D, current_value=_D, national_prior=_D, national_current=_D, median_gap=_D,
                              scale=_D, z=_D, n_states_scored=_I, trigger=_V, excess=_D, flags=_L, rule_status=_V,
                              driver_kind=_V, driver_key=_V, driver_share=_D, state_agency_share=_D, contractor_address_share=_D),
    "desk_card4_text": {"agency_code": _V, "key": _V, "template": _V},
    "desk_card4_params": {"agency_code": _V, "parameter": _V, "value": _V},
    "desk_card4_national_orgs": dict(_COMMON, recipient_uei=_V, recipient_name=_V, rule_basis=_V),
}
