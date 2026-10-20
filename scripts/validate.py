#!/usr/bin/env python3
"""Check the local database against USAspending's own published totals.

Runs offline: compares against reference snapshots saved by fetch.py.
Writes logs/validation_<date>_<agency>.md and exits non-zero on any FAIL.

Usage:
  python scripts/validate.py              # DOJ
  python scripts/validate.py --agency 070
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DB_PATH, LOGS, agency_raw_dir, current_fiscal_year, load_json, log  # noqa: E402

try:
    import duckdb
except ImportError:
    raise SystemExit("duckdb is not installed. Run:  bash scripts/setup.sh  then  source .venv/bin/activate")

# (pass_tolerance, warn_tolerance) as fractions
ACCOUNT_TOL = (0.005, 0.02)
AWARD_TOL = (0.01, 0.03)


class Report:
    def __init__(self):
        self.rows = []

    def add(self, check, scope, status, ours=None, theirs=None, note=""):
        self.rows.append((check, scope, status, ours, theirs, note))

    def compare(self, check, scope, ours, theirs, tol, provisional=False):
        if theirs in (None, 0) and ours in (None, 0):
            return self.add(check, scope, "PASS", ours, theirs, "both zero/empty")
        if theirs in (None, 0) or ours is None:
            return self.add(check, scope, "INFO" if provisional else "WARN", ours, theirs, "missing on one side")
        diff = (ours - theirs) / abs(theirs)
        status = "PASS" if abs(diff) <= tol[0] else ("WARN" if abs(diff) <= tol[1] else "FAIL")
        note = f"diff {diff:+.2%}"
        if provisional and status != "PASS":
            status, note = "INFO", note + " (current FY, provisional)"
        self.add(check, scope, status, ours, theirs, note)

    def counts(self):
        out = {}
        for r in self.rows:
            out[r[2]] = out.get(r[2], 0) + 1
        return out

    def markdown(self, title):
        def money(v):
            if v is None:
                return ""
            if isinstance(v, (int, float)) and abs(v) >= 1e5:
                return f"${v / 1e9:,.3f}B"
            return f"{v:,}" if isinstance(v, (int, float)) else str(v)
        lines = [f"# {title}", "", f"Generated {dt.datetime.now():%Y-%m-%d %H:%M}", "",
                 "Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(self.counts().items())), "",
                 "| Check | Scope | Status | Ours | USAspending | Note |", "|---|---|---|---|---|---|"]
        for c, s, st, o, t, n in self.rows:
            lines.append(f"| {c} | {s} | **{st}** | {money(o)} | {money(t)} | {n} |")
        return "\n".join(lines) + "\n"


def has_view(con, name):
    return con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0] > 0


def scalar(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agency", default="015")
    args = ap.parse_args()
    agency = args.agency

    if not DB_PATH.exists():
        raise SystemExit("No database yet. Run fetch.py and build.py first.")
    ref_dir = agency_raw_dir(agency) / "reference"
    snap = load_json(ref_dir / "snapshot_info.json", {})
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rep = Report()
    cur_fy = current_fiscal_year()
    latest = {int(k): v for k, v in snap.get("latest_period_by_fy", {}).items()}
    # Only judge fiscal years that fetch.py was asked to pull.
    jobs = load_json(agency_raw_dir(agency) / "manifest.json", {}).get("jobs", {}).values()
    acct_fys = {int(j["fy"]) for j in jobs if j.get("kind") == "accounts"}
    award_fys = {int(j["fy"]) for j in jobs if j.get("kind") == "awards"}

    # ---------------------------------------------------------- account totals (File A)
    if has_view(con, "account_balances"):
        ours = {r[0]: r[1:] for r in con.execute("""
            SELECT fiscal_year, sum(total_budgetary_resources), sum(obligations_incurred), sum(gross_outlay_amount),
                   max(submission_period_num)
            FROM account_balances WHERE agency_code = ? GROUP BY 1 ORDER BY 1""", [agency]).fetchall()}
        fileb = {}
        if has_view(con, "account_activity"):
            fileb = {r[0]: r[1:] for r in con.execute("""
                SELECT fiscal_year, sum(obligations_incurred), sum(gross_outlay_amount_FYB_to_period_end)
                FROM account_activity WHERE agency_code = ? GROUP BY 1""", [agency]).fetchall()}
        budg = load_json(ref_dir / "budgetary_resources.json", {})
        theirs = {int(r["fiscal_year"]): r for r in
                  (budg.get("agency_data_by_year") or budg.get("agency_by_year") or [])}
        for fy in sorted(ours):
            br, ob, out, period = ours[fy]
            if latest.get(fy) and period and period < latest[fy]:
                rep.add("File A period", f"FY{fy}", "WARN", period, latest[fy],
                        "newer period revealed; re-run fetch.py")
            t = theirs.get(fy)
            if not t:
                rep.add("Budgetary resources", f"FY{fy}", "WARN", br, None, "no published figure")
                continue
            prov = fy >= cur_fy - 1 and latest.get(fy, 12) < 12
            rep.compare("Budgetary resources (File A)", f"FY{fy}", br, t.get("agency_budgetary_resources"),
                        ACCOUNT_TOL, prov)
            # USAspending's published agency obligations/outlays are summed from File B, so that is
            # the like-for-like check that our load is complete. File A vs B is checked separately below.
            if fileb.get(fy):
                bob, bout = fileb[fy]
                rep.compare("Obligations (File B)", f"FY{fy}", bob, t.get("agency_total_obligated"), ACCOUNT_TOL, prov)
                if t.get("agency_total_outlayed") is not None:
                    rep.compare("Outlays (File B)", f"FY{fy}", bout, t.get("agency_total_outlayed"), ACCOUNT_TOL, prov)
        for fy in sorted(acct_fys - set(ours)):
            rep.add("File A coverage", f"FY{fy}", "FAIL", None, None, "fiscal year requested but no rows")

        # File A vs File B: differences here are the agency's own reporting inconsistencies
        # (e.g. sign flips or missing rows in File B), not load errors. Reported as WARN with the
        # accounts responsible, so analysts know which source to trust for which account.
        if has_view(con, "account_activity"):
            gaps = con.execute("""
                WITH a AS (SELECT fiscal_year, treasury_account_symbol tas, sum(obligations_incurred) ob
                           FROM account_balances WHERE agency_code=? GROUP BY 1, 2),
                     b AS (SELECT fiscal_year, treasury_account_symbol tas, sum(obligations_incurred) ob
                           FROM account_activity WHERE agency_code=? GROUP BY 1, 2)
                SELECT fiscal_year, sum(coalesce(a.ob, 0)) a_tot, sum(coalesce(b.ob, 0)) b_tot,
                       list(tas || ' ' || CAST(round((coalesce(a.ob,0) - coalesce(b.ob,0)) / 1e6) AS BIGINT) || 'M'
                            ORDER BY abs(coalesce(a.ob,0) - coalesce(b.ob,0)) DESC)[1:3] AS top
                FROM a FULL JOIN b USING (fiscal_year, tas) GROUP BY 1 ORDER BY 1""", [agency, agency]).fetchall()
            for fy, a_tot, b_tot, top in gaps:
                diff = (b_tot - a_tot) / abs(a_tot) if a_tot else 0
                if abs(diff) <= 0.01:
                    rep.add("File A vs File B obligations", f"FY{fy}", "PASS", b_tot, a_tot, f"diff {diff:+.2%}")
                else:
                    rep.add("File A vs File B obligations", f"FY{fy}", "WARN", b_tot, a_tot,
                            f"diff {diff:+.2%}; agency reporting gap, largest: {', '.join(top)}. "
                            "Use File A for account totals.")

    # ---------------------------------------------------------- award totals
    def sot(kind):
        res = load_json(ref_dir / f"spending_over_time_awarding_{kind}.json", {}).get("results", [])
        out = {}
        for r in res:
            fy = (r.get("time_period") or {}).get("fiscal_year")
            if fy:
                out[int(fy)] = r.get("aggregated_amount")
        return out

    if has_view(con, "prime_transactions"):
        n = scalar(con, "SELECT count(*) FROM prime_transactions WHERE agency_code = ?", [agency])
        d = scalar(con, "SELECT count(*) - count(DISTINCT transaction_key) FROM prime_transactions WHERE agency_code=?",
                   [agency])
        rep.add("Unique transaction keys", "all", "PASS" if d == 0 else "FAIL", n, None, f"{d:,} duplicates")
        nk = scalar(con, "SELECT count(*) FROM prime_transactions WHERE agency_code=? AND award_key IS NULL", [agency])
        rep.add("Null award keys", "all", "PASS" if nk == 0 else "WARN", nk)
        ours = dict(con.execute("""
            SELECT fiscal_year, sum(federal_action_obligation) FROM prime_transactions
            WHERE agency_code = ? AND awarding_agency_code = agency_code GROUP BY 1""", [agency]).fetchall())
        theirs = sot("prime")
        for fy in sorted(award_fys):
            if fy not in ours:
                rep.add("Prime obligations (awarding)", f"FY{fy}", "FAIL", None, theirs.get(fy), "no local rows")
                continue
            rep.compare("Prime obligations (awarding)", f"FY{fy}", ours[fy], theirs.get(fy), AWARD_TOL,
                        provisional=fy >= cur_fy)
        roles = dict(con.execute("""SELECT pull_role, count(*) FROM prime_transactions WHERE agency_code=?
                                    GROUP BY 1""", [agency]).fetchall())
        rep.add("Funding-only transactions added", "all", "INFO", roles.get("funding", 0), None,
                "DOJ-funded actions awarded by another agency")

    if has_view(con, "subawards"):
        ours = dict(con.execute("""
            SELECT fiscal_year, sum(subaward_amount) FROM subawards
            WHERE agency_code = ? AND prime_award_awarding_agency_code = agency_code GROUP BY 1""",
                                [agency]).fetchall())
        theirs = sot("subawards")
        for fy in sorted(award_fys):
            rep.compare("Sub-award amount (awarding)", f"FY{fy}", ours.get(fy), theirs.get(fy), AWARD_TOL,
                        provisional=fy >= cur_fy)
        if has_view(con, "prime_awards"):
            orphan = scalar(con, """
                SELECT count(*) FROM subawards s
                WHERE s.agency_code = ? AND NOT EXISTS (
                    SELECT 1 FROM prime_awards p WHERE p.award_key = s.prime_award_unique_key)""", [agency])
            total = scalar(con, "SELECT count(*) FROM subawards WHERE agency_code = ?", [agency])
            rep.add("Sub-awards whose prime is outside window", "all", "INFO", orphan, total,
                    f"{orphan / total:.1%} of sub-awards" if total else "")

    con.close()
    LOGS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"validation_{dt.date.today():%Y-%m-%d}_{agency}.md"
    md = rep.markdown(f"Validation: agency {agency}")
    out.write_text(md)
    print(md)
    log(f"Saved {out}")
    if rep.counts().get("FAIL"):
        log("There are FAILs. Don't publish numbers from this load until they're explained.")
        sys.exit(1)


if __name__ == "__main__":
    main()
