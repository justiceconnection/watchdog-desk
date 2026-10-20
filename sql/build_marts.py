#!/usr/bin/env python3
"""Build the tier-1 marts (marts/<agency>/*.parquet) from data/fedspend.duckdb.

Usage (repo root, .venv active):
    python sql/build_marts.py                 # every agency in the database
    python sql/build_marts.py --agency 015    # one agency (repeatable)
    python sql/build_marts.py --check         # build, then run sql/checks/reconcile_marts.sql
    python sql/build_marts.py --check-only    # only run the checks against existing marts
    python sql/build_marts.py --v2-only       # write only marts/<agency>/v2/ (needs sql/v2/)
    python sql/build_marts.py --desk-only     # write only marts/<agency>/desk/ (Watchdog Desk cards, sql/desk/*.py)

How it works
  * Opens an in-memory DuckDB, ATTACHes data/fedspend.duckdb READ_ONLY, and puts it on
    the search path. Nothing is ever written to the database.
  * For each agency: SET VARIABLE agency = '<code>'; runs sql/marts/[0-8]*.sql in name
    order; COPYs every table named mart_* or account_ab_reconciliation to
    marts/<agency>/<table>.parquet (ZSTD).
  * Then runs sql/marts/90_dim_agency.sql once and writes marts/dim_agency.parquet.
  * Enforces the size budget: < 5 MB per mart, < 50 MB per agency (exit 1 if exceeded).
  * Optional parts are skipped with a printed note when their files are absent:
      - the prototype concept / v2 layer (sql/v2/, sql/marts/80_concepts.sql, 85_v2.sql, 86_v2_issues.sql):
        skipped entirely when sql/v2/ is absent;
      - any other sql/marts/*.sql file that is not present is simply not run (the Watchdog Desk needs only
        00_setup, 35_subaward_base, 40_awards, 50_subawards, 60_fiscal_years and 75_new_awards);
      - checks whose inputs or scripts are absent.

Only needs duckdb. Python 3.9+.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql" / "marts"
CHECKS = ROOT / "sql" / "checks" / "reconcile_marts.sql"
DB = ROOT / "data" / "fedspend.duckdb"
OUT = ROOT / "marts"
MART_MAX = 5 * 1024 * 1024
AGENCY_MAX = 50 * 1024 * 1024
EXPORT = re.compile(r"^(mart_\w+|account_ab_reconciliation)$")
CONCEPT = re.compile(r"^concept_\w+$")   # PROTOTYPE marts -> marts/<agency>/concepts/
V2 = re.compile(r"^v2_(\w+)$")              # PROTOTYPE v2 marts -> marts/<agency>/v2/<name without v2_>
DESK = re.compile(r"^desk_(\w+)$")          # Watchdog Desk marts -> marts/<agency>/desk/<name without desk_>
V2_DIR = ROOT / "sql" / "v2"
# Prototype concept / v2 SQL: run only when the v2 modules (sql/v2/) are present.
PROTOTYPE_SQL = {"80_concepts.sql", "85_v2.sql", "86_v2_issues.sql"}


def have_v2() -> bool:
    return (V2_DIR / "trend_signals.py").exists() and (V2_DIR / "signal_text.py").exists()


_noted = set()


def note(msg: str) -> None:
    """Print a note once per run."""
    if msg not in _noted:
        _noted.add(msg)
        print(f"note: {msg}")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB.as_posix()}' AS fs (READ_ONLY)")
    con.execute("SET search_path = 'memory.main,fs.main'")
    # Reproducible output: one thread makes floating-point sums add up in a fixed order,
    # and every export is sorted on all columns, so a rebuild on the same data gives
    # byte-identical Parquet files (same hashes).
    con.execute("SET threads = 1")
    return con


def run_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    con.execute(path.read_text())


def agencies_in_db(con) -> list[str]:
    rows = con.execute("""
        SELECT agency_code FROM account_balances
        UNION SELECT agency_code FROM prime_transactions
        ORDER BY 1""").fetchall()
    return [r[0] for r in rows]


def build_v2_python(con, agency: str) -> None:
    """Trend signals and year-over-year changes (sql/v2/trend_signals.py) -> tables v2_mart_*."""
    sys.path.insert(0, str(ROOT / "sql" / "v2"))
    import trend_signals as T
    p = T.load_params(agency)
    cov = T.coverage_from(con)
    cut = cov["assistance"]["cutoff"]
    eng = T.Engine(con, agency, p, "_v2_tx", "_v2_newaw", (cut.month, cut.day))
    import csv as _csv
    ov_path = ROOT / "sql" / "seeds" / "signal_overrides.csv"
    overrides, ov_rows = {}, []
    if ov_path.exists():
        with open(ov_path, encoding="utf-8") as f:
            ov_rows = [r for r in _csv.DictReader(f) if r["agency_code"] == agency]
        # spec 6.2: an override takes effect only when verified_in is set; label = override_type
        for r in ov_rows:
            r["item_id"] = f"{r['category']}|{r['dimension']}|{r['key']}|{r['target_year']}"
            r["label"] = r["override_type"]
        overrides = {r["item_id"]: r for r in ov_rows if r["effect"] == "demote" and r.get("verified_in")}
    SIG, FEED = eng.run(T.make_plan(cov, int(p["cycle_offset_years"])), overrides)
    matched = {f["item_id"] for f in FEED}
    _rows_to_table(con, "v2_signal_overrides", [dict(r, active=(r["item_id"] in overrides), matched_item=(r["item_id"] in matched))
                                                 for r in sorted(ov_rows, key=lambda r: r["item_id"])])
    data_as_of = con.execute("SELECT data_as_of FROM _params").fetchone()[0]
    short = (con.execute("SELECT abbreviation FROM _agency_names").fetchone() or [agency])[0]
    import signal_text as ST
    rend = ST.Renderer(con, agency, eng, cov, short, "_v2_newaw", "_v2_tx")
    # The default feed follows the dollars / new-awards switch. Items, ranks and events
    # stay as in spec 6/6.1 (all measures); the default feed and its unit ranks are filtered per measure
    # family: an item is in a family's feed when it has a signal of that family.
    rows = T.signal_rows(agency, SIG, FEED, data_as_of, short, rend)
    _rows_to_table(con, "v2_mart_trend_signals", rows)
    text_rows = [dict(r, measure_family=fam) for fam in ("all", "dollars", "counts")
                 for r in T.feed_text_rows(agency, FEED, rend, cov, None if fam == "all" else fam)]
    _rows_to_table(con, "v2_signal_feed_text", text_rows)
    # parameters for the methods page (from sql/seeds/trend_signal_params.csv), long format
    _rows_to_table(con, "v2_signal_params", [dict(agency_code=agency, parameter=k, value=str(v)) for k, v in sorted(p.items())
                                             if k != "agency_code"])
    _rows_to_table(con, "v2_mart_yoy_changes", T.yoy_rows(con, agency, p, cov, "_v2_tx", "_v2_newaw", data_as_of, rend))


def build_desk_python(con, agency: str) -> list:
    """Watchdog Desk cards (sql/desk/card4.py, natorg.py, card3.py, card2.py) -> tables desk_*; returns post-export writers
    (CSVs, then marts/<agency>/desk/manifest.json). Verification sign-offs (publish.signoffs_path()) are joined into
    the card tables as verified_on (NULL when the file or the row is missing) and verified_in (always NULL)."""
    sys.path.insert(0, str(ROOT / "sql" / "desk"))
    import card4, natorg, card2, card3, publish
    signoffs = publish.load_signoffs()
    signed = {"verified_on": "DATE", "verified_in": "VARCHAR"}
    eng = card4.Card4(con, agency)
    eng.run()
    tables, csvs = eng.tables()
    publish.apply_signoffs(tables["desk_card4_cards"], card4.CARD_TYPE, signoffs)
    for name, rows in tables.items():
        _typed_rows_to_table(con, name, rows, dict(card4.COLUMN_TYPES.get(name, {}), **signed) if name == "desk_card4_cards"
                             else card4.COLUMN_TYPES.get(name, {}))
    no = natorg.NatOrg(eng)
    no.run()
    no_tables, no_csvs = no.tables()
    publish.apply_signoffs(no_tables["desk_natorg_cards"], "national_organizations", signoffs)
    for name, rows in no_tables.items():
        _typed_rows_to_table(con, name, rows, dict(natorg.COLUMN_TYPES.get(name, {}), **signed) if name == "desk_natorg_cards"
                             else natorg.COLUMN_TYPES.get(name, {}))
    c3 = card3.Card3(eng)
    c3.build()
    c3.run()
    c3_tables, c3_csvs = c3.tables()
    publish.apply_signoffs(c3_tables["desk_card3_cards"], "grant_categories", signoffs)
    for name, rows in c3_tables.items():
        _typed_rows_to_table(con, name, rows, dict(card3.COLUMN_TYPES.get(name, {}), **signed) if name == "desk_card3_cards"
                             else card3.COLUMN_TYPES.get(name, {}))
    c2 = card2.Card2(con, agency)
    c2.build()
    c2_tables = c2.tables()
    publish.apply_signoffs(c2_tables["desk_card2_summary"], "contracts_without_competition", signoffs)
    for name, rows in c2_tables.items():
        _typed_rows_to_table(con, name, rows, dict(card2.COLUMN_TYPES.get(name, {}), **signed) if name == "desk_card2_summary"
                             else card2.COLUMN_TYPES.get(name, {}))
    types = {card4.CARD_TYPE: [(c["card_id"], c["status"], f"desk/csv/{c['card_id']}.csv") for c in tables["desk_card4_cards"]],
             "national_organizations": [(c["card_id"], c["status"], f"desk/csv/{c['card_id']}.csv") for c in no_tables["desk_natorg_cards"]],
             "grant_categories": [(c["card_id"], c["status"], c["csv_path"]) for c in c3_tables["desk_card3_cards"]],
             "contracts_without_competition": [(c["card_id"], c["status"], c["csv_path"]) for c in c2_tables["desk_card2_summary"]]}
    data_as_of = eng.data_as_of
    return [(card4.write_csvs, csvs), (natorg.write_csvs, no_csvs), (card3.write_csvs, c3_csvs), (lambda _c, out_dir: c2.write_csv(out_dir), None),
            (lambda _c, out_dir: publish.write_public(con, out_dir.parent, agency), None),
            (lambda _c, out_dir: publish.write_manifest(out_dir.parent, agency, data_as_of, types,
                                                        {r[0] for r in con.execute("SELECT card_id FROM _desk_pub").fetchall()}), None)]


def _typed_rows_to_table(con, name: str, rows: list[dict], declared: dict) -> None:
    """Rows -> table with explicit column types (declared, else inferred from the first non-null value)."""
    import datetime as _dt
    import json as _json
    import tempfile
    cols = list(rows[0].keys()) if rows else list(declared.keys())
    types = {}
    for c in cols:
        if c in declared:
            types[c] = declared[c]
            continue
        v = next((r[c] for r in rows if r.get(c) is not None), None)
        types[c] = ("BOOLEAN" if isinstance(v, bool) else "BIGINT" if isinstance(v, int) else "DOUBLE" if isinstance(v, float)
                    else "VARCHAR[]" if isinstance(v, list) else "TIMESTAMP" if isinstance(v, _dt.datetime)
                    else "DATE" if isinstance(v, _dt.date) else "VARCHAR")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump([{c: r.get(c) for c in cols} for r in rows], f, default=str)
        path = f.name
    spec = ", ".join(f"'{c}': '{t}'" for c, t in types.items())
    sel = ", ".join(f'"{c}"' for c in cols)
    if rows:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT {sel} FROM read_json('{path}', format='array', columns={{{spec}}})")
    else:
        con.execute(f"CREATE OR REPLACE TABLE {name} ({', '.join(f'{chr(34)}{c}{chr(34)} {t}' for c, t in types.items())})")
    os.unlink(path)


def _rows_to_table(con, name: str, rows: list[dict]) -> None:
    import json as _json
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        _json.dump(rows, f, default=str)
        path = f.name
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_json_auto('{path}', maximum_object_size=1000000000)")
    os.unlink(path)


def build_agency(con, agency: str, v2_only: bool = False, desk_only: bool = False) -> list[tuple[str, int, int]]:
    con.execute("SET VARIABLE agency = ?", [agency])
    v2 = have_v2()
    if not v2:
        note("sql/v2/ is absent: skipped the prototype concept / v2 layer (" + ", ".join(sorted(PROTOTYPE_SQL))
             + " and the trend-signal step); marts/<agency>/concepts/ and v2/ are not written")
    for f in sorted(SQL_DIR.glob("[0-8]*.sql")):
        if f.name in PROTOTYPE_SQL and not v2:
            continue
        run_file(con, f)
    if not desk_only and v2:
        build_v2_python(con, agency)
    post = [] if v2_only else build_desk_python(con, agency)
    out = OUT / agency
    out.mkdir(parents=True, exist_ok=True)
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = 'memory' ORDER BY 1").fetchall()]
    written = []
    if v2:
        (out / "concepts").mkdir(exist_ok=True)
        (out / "v2").mkdir(exist_ok=True)
    (out / "desk").mkdir(exist_ok=True)
    for t in tables:
        if DESK.match(t):
            if v2_only:
                continue
            path = out / "desk" / f"{DESK.match(t).group(1)}.parquet"
        elif desk_only:
            continue   # --desk-only: never rewrite v1, concept or v2 marts
        elif V2.match(t):
            path = out / "v2" / f"{V2.match(t).group(1)}.parquet"
        elif v2_only:
            continue   # --v2-only: never rewrite v1 or concept marts
        elif EXPORT.match(t):
            path = out / f"{t}.parquet"
        elif CONCEPT.match(t):
            path = out / "concepts" / f"{t}.parquet"
        else:
            continue
        con.execute(f"COPY (SELECT * FROM {t} ORDER BY ALL) TO '{path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        written.append((str(path.relative_to(out)), n, path.stat().st_size))
    for fn, csvs in post:
        for p in fn(csvs, out / "desk" / "csv"):
            written.append((str(p.relative_to(out)), -1, p.stat().st_size))
    return written


def build_dim_agency(con):
    """marts/dim_agency.parquet from sql/marts/90_dim_agency.sql; None when that file is absent."""
    if not (SQL_DIR / "90_dim_agency.sql").exists():
        note("sql/marts/90_dim_agency.sql is absent: skipped marts/dim_agency.parquet")
        return None
    run_file(con, SQL_DIR / "90_dim_agency.sql")
    path = OUT / "dim_agency.parquet"
    con.execute(f"COPY (SELECT * FROM dim_agency ORDER BY ALL) TO '{path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    return con.execute("SELECT count(*) FROM dim_agency").fetchone()[0], path.stat().st_size


def run_checks(con, agency: str) -> bool:
    con.execute("SET VARIABLE agency = ?", [agency])
    con.execute("SET VARIABLE marts_dir = ?", [(OUT / agency).as_posix()])
    sys.path.insert(0, str(ROOT / "sql" / "desk"))
    import publish
    con.execute("SET VARIABLE signoffs_csv = ?", [publish.signoffs_path().as_posix()])
    rows, cols = [], None
    # reconcile_marts.sql covers every v1 mart plus the prototype concept marts and the data-issues register;
    # it runs when all of those were built.
    needs = [OUT / agency / "concepts" / "concept_geo_county.parquet", OUT / agency / "mart_data_issues.parquet",
             OUT / agency / "mart_agency_fy_summary.parquet"]
    if CHECKS.exists() and all(p.exists() for p in needs):
        rows = con.execute(CHECKS.read_text()).fetchall()
        cols = [d[0] for d in con.description]
    else:
        note(f"skipped sql/checks/reconcile_marts.sql (needs the v1, data-issues and concept marts in marts/{agency}/)")
    v2 = ROOT / "sql" / "checks" / "reconcile_v2.sql"
    if (OUT / agency / "v2" / "mart_trend_signals.parquet").exists() and v2.exists():
        rows += con.execute(v2.read_text()).fetchall()   # PROTOTYPE v2 checks
    desk = ROOT / "sql" / "checks" / "reconcile_desk.sql"
    if (OUT / agency / "desk" / "card4_cards.parquet").exists() and desk.exists():
        if not publish.signoffs_path().exists():
            note("no sign-off file: the desk check of public card ids is run against an empty list")
            con.execute("SET VARIABLE signoffs_csv = ?", [_empty_signoffs().as_posix()])
        con.execute("SET VARIABLE desk_new_awards = ?", [_desk_new_awards(con, agency).as_posix()])
        rows += con.execute(desk.read_text()).fetchall()   # Watchdog Desk checks
        cols = cols or [d[0] for d in con.description]
    if cols is None:
        print(f"\nReconciliation checks, agency {agency}: none ran (no marts to check)")
        return False
    ok = True
    print(f"\nReconciliation checks, agency {agency}")
    print(" | ".join(cols))
    n_fail = 0
    for r in rows:
        rec = dict(zip(cols, r))
        n_fail += rec["status"] != "PASS"
        print(" | ".join("" if v is None else (f"{v:,.2f}" if isinstance(v, float) else str(v)) for v in r))
    print(f"{len(rows) - n_fail}/{len(rows)} checks PASS")
    ok = n_fail == 0
    proto = ROOT / "docs" / "specs" / "watchdog-cards-reference" / "card4_prototype.py"
    if (OUT / agency / "desk" / "card4_scores.parquet").exists() and not proto.exists():
        note("skipped the Card 4 prototype parity check (reference prototype not present)")
    elif (OUT / agency / "desk" / "card4_scores.parquet").exists():
        import subprocess
        p = subprocess.run([sys.executable, str(ROOT / "sql" / "checks" / "desk_card4_prototype.py"), "--agency", agency],
                           cwd=ROOT, capture_output=True, text=True)
        print(p.stdout.rstrip() + (("\n" + p.stderr.rstrip()) if p.returncode and p.stderr else ""))
        ok &= p.returncode == 0
    ok &= check_validation_log(con, agency)
    return ok


def _desk_new_awards(con, agency: str) -> Path:
    """Assistance new awards for the desk checks: marts/<agency>/v2/award_new.parquet when it exists, else the same rows
    (v2_award_new = _v2_award_new, assistance only) from the in-memory table built by sql/marts/75_new_awards.sql."""
    pq = OUT / agency / "v2" / "award_new.parquet"
    if pq.exists():
        return pq
    have = con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = 'memory' AND table_name = '_v2_award_new'").fetchone()[0]
    if not have or not con.execute("SELECT count(*) FROM _v2_award_new WHERE agency_code = ?", [agency]).fetchone()[0]:
        con.execute("SET VARIABLE agency = ?", [agency])
        for f in sorted(SQL_DIR.glob("[0-7]*.sql")):   # inputs of 75_new_awards.sql (no prototype SQL)
            run_file(con, f)
    import tempfile
    tmp = Path(tempfile.gettempdir()) / f"desk_check_award_new_{agency}.parquet"
    con.execute(f"COPY (SELECT * EXCLUDE (new_award_transaction_key, recipient_state_raw) FROM _v2_award_new "
                f"WHERE award_category = 'assistance') TO '{tmp.as_posix()}' (FORMAT parquet)")
    return tmp


def _empty_signoffs() -> Path:
    import tempfile
    p = Path(tempfile.gettempdir()) / "desk_signoffs_empty.csv"
    p.write_text("card_id,card_type,verified_date\n", encoding="utf-8")
    return p


def check_validation_log(con, agency: str) -> bool:
    """Compare mart totals with the newest logs/validation_*_<agency>.md ('Ours' column, $B to 3 dp)."""
    logs = sorted((ROOT / "logs").glob(f"validation_*_{agency}.md"))
    if not logs:
        print(f"(no logs/validation_*_{agency}.md; skipped log comparison)")
        return True
    need = ("mart_agency_fy_summary", "mart_awards", "mart_subaward_summary")
    if not all((OUT / agency / f"{m}.parquet").exists() for m in need):
        note(f"skipped the validation-log comparison (needs {', '.join(need)} in marts/{agency}/)")
        return True
    log = logs[-1]
    want = {
        "Budgetary resources (File A)": "SELECT fiscal_year, total_budgetary_resources FROM read_parquet(getvariable('marts_dir') || '/mart_agency_fy_summary.parquet')",
        "Obligations (File B)": "SELECT fiscal_year, obligations_b FROM read_parquet(getvariable('marts_dir') || '/mart_agency_fy_summary.parquet')",
        "Outlays (File B)": "SELECT fiscal_year, outlays_b FROM read_parquet(getvariable('marts_dir') || '/mart_agency_fy_summary.parquet')",
        # In the 'File A vs File B obligations' rows the 5th column holds File A.
        "File A vs File B obligations": "SELECT fiscal_year, obligations_a FROM read_parquet(getvariable('marts_dir') || '/mart_agency_fy_summary.parquet')",
        "Prime obligations (awarding)": "SELECT fiscal_year, sum(obligations) FROM read_parquet(getvariable('marts_dir') || '/mart_awards.parquet') WHERE definition = 'awarding' GROUP BY 1",
        "Sub-award amount (awarding)": "SELECT fiscal_year, sum(subaward_amount) FROM read_parquet(getvariable('marts_dir') || '/mart_subaward_summary.parquet') WHERE definition = 'awarding' GROUP BY 1",
    }
    mart = {k: dict(con.execute(q).fetchall()) for k, q in want.items()}
    pat = re.compile(r"^\| (.+?) \| FY(\d{4}) \| \*\*\w+\*\* \| \$(-?[\d.]+)B \| (?:\$(-?[\d.]+)B)?")
    n = bad = 0
    for line in log.read_text().splitlines():
        m = pat.match(line)
        if not m or m.group(1) not in mart:
            continue
        name, fy = m.group(1), int(m.group(2))
        ours = float(m.group(4) if name == "File A vs File B obligations" else m.group(3))
        got = mart[name].get(fy)
        n += 1
        if got is None or round(got / 1e9, 3) != ours:
            bad += 1
            print(f"LOG MISMATCH {name} FY{fy}: log ${ours}B, mart {got}")
    print(f"Validation log {log.name}: {n - bad}/{n} totals reproduced to $0.001B")
    return bad == 0 and n > 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agency", action="append", help="3-digit toptier code; repeatable; default all")
    ap.add_argument("--check", action="store_true", help="run reconciliation checks after building")
    ap.add_argument("--check-only", action="store_true", help="only run checks on existing marts")
    ap.add_argument("--v2-only", action="store_true",
                    help="build everything in memory but write only marts/<agency>/v2/ (v1 and concept files untouched)")
    ap.add_argument("--desk-only", action="store_true",
                    help="build everything in memory but write only marts/<agency>/desk/ (v1, concept and v2 files untouched)")
    ap.add_argument("--regen-listing-map", action="store_true",
                    help="regenerate sql/seeds/listing_office_map.csv from the data, then build")
    args = ap.parse_args()

    import os
    os.chdir(ROOT)  # seed and raw paths in the SQL are relative to the repo root
    con = connect()
    if args.regen_listing_map:
        seed = ROOT / "sql" / "seeds" / "listing_office_map.csv"
        q = (ROOT / "sql" / "seeds" / "listing_office_map.sql").read_text()
        con.execute(f"COPY ({q}) TO '{seed.as_posix()}' (HEADER, DELIMITER ',')")
        print(f"wrote {seed.relative_to(ROOT)}")
    agencies = args.agency or agencies_in_db(con)
    ok = True
    if args.v2_only and not have_v2():
        print("--v2-only needs sql/v2/ (trend_signals.py, signal_text.py), which is absent.")
        return 1
    if not args.check_only:
        for a in agencies:
            written = build_agency(con, a, args.v2_only, args.desk_only)
            total = sum(s for _, _, s in written)
            print(f"\nAgency {a}: marts/{a}/")
            for t, n, s in written:
                flag = "  OVER 5 MB BUDGET" if s > MART_MAX else ""
                ok &= s <= MART_MAX
                print(f"  {t:32s} {'' if n < 0 else f'{n:,} rows':>14} {s / 1024:>9.1f} KB{flag}")
            print(f"  {'TOTAL':32s} {'':>14} {total / 1024 / 1024:>9.2f} MB"
                  + ("  OVER 50 MB BUDGET" if total > AGENCY_MAX else ""))
            ok &= total <= AGENCY_MAX
        if not (args.v2_only or args.desk_only):
            dim = build_dim_agency(con)
            if dim:
                print(f"\nmarts/dim_agency.parquet {dim[0]} rows {dim[1] / 1024:.1f} KB")
    if args.check or args.check_only:
        for a in agencies:
            ok &= run_checks(con, a)
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
