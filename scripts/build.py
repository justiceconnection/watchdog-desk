#!/usr/bin/env python3
"""Turn downloaded zips into Parquet files and a DuckDB database of views.

  data/raw/<agency>/**/*.zip  ->  data/parquet/<dataset>/agency=../fy=../role=../*.parquet
                              ->  data/fedspend.duckdb  (typed views + analysis views)

Usage:
  python scripts/build.py            # convert new/changed zips, rebuild the database
  python scripts/build.py --full     # reconvert every zip from scratch

Parquet keeps every column as text (exactly as published). Types are applied
in the DuckDB views, so a bad value never breaks a load.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, DB_PATH, PARQUET, RAW, SQL_DIR, classify_csv, load_json, log, save_json  # noqa: E402

try:
    import duckdb
except ImportError:
    raise SystemExit("duckdb is not installed. Run:  bash scripts/setup.sh  then  source .venv/bin/activate")

STATE_PATH = PARQUET / "_build_state.json"
TMP = DATA / "_tmp"

ACCOUNT_DATASETS = ["account_balances", "account_activity", "award_financial"]
AWARD_DATASETS = ["contract_transactions", "assistance_transactions", "contract_subawards", "assistance_subawards"]

# ----------------------------------------------------------------- column typing

MONEY_RE = re.compile(r"(amount|obligat|outlay|_value|budgetary_resources|dollars|subsidy_cost|^ussgl|_total$|_total_fyb$)",
                      re.IGNORECASE)
NOT_MONEY_RE = re.compile(r"(code|_name|description|basis|_flag|indicator|fund_codes)", re.IGNORECASE)
META = {"_agency": "agency_code", "_fy": "fiscal_year", "_role": "pull_role",
        "_period": "submission_period_num", "_source_file": "source_file"}


def typed_expr(col: str) -> str:
    q = '"' + col.replace('"', '""') + '"'
    low = col.lower()
    if col in META:
        if col in ("_fy", "_period"):
            return f"TRY_CAST({q} AS INTEGER) AS {META[col]}"
        return f"{q} AS {META[col]}"
    if low.endswith("_date"):
        return f"TRY_CAST(LEFT({q}, 10) AS DATE) AS {q}"
    if low.endswith("_fiscal_year") or low in ("subaward_sam_report_year", "subaward_sam_report_month"):
        return f"TRY_CAST({q} AS INTEGER) AS {q}"
    if MONEY_RE.search(low) and not NOT_MONEY_RE.search(low):
        return f"TRY_CAST(REPLACE({q}, ',', '') AS DOUBLE) AS {q}"
    return q


# ----------------------------------------------------------------- zip -> parquet

def job_meta(manifest: dict, zip_rel: str) -> dict:
    for job in manifest.get("jobs", {}).values():
        if job.get("path") == zip_rel and job.get("status") == "downloaded":
            return job
    return {}


def convert_zip(con, agency: str, zip_path: Path, meta: dict) -> list[str]:
    fy = str(meta.get("fy", ""))
    role = meta.get("role") or "owner"
    period = str(meta.get("period") or "")
    outputs = []
    TMP.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith((".csv", ".txt", ".tsv"))]
        for i, member in enumerate(sorted(members)):
            ds = classify_csv(member)
            if ds is None:
                log(f"    skipping unrecognized file {member}")
                continue
            wanted = {"A": "account_balances", "B": "account_activity", "C": "award_financial"}.get(meta.get("file"))
            if wanted and ds != wanted:
                log(f"    skipping {member} (job requested {wanted} only)")
                continue
            out_dir = PARQUET / ds / f"agency={agency}" / f"fy={fy}" / f"role={role}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{zip_path.stem}__{Path(member).stem}.parquet"  # unique per source zip
            tmp_csv = TMP / Path(member).name
            with zf.open(member) as src, open(tmp_csv, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            delim = "\t" if member.lower().endswith(".tsv") else ("|" if member.lower().endswith(".txt") else ",")
            src_name = Path(member).name.replace("'", "''")
            con.execute(f"""
                COPY (
                    SELECT *, '{agency}' AS _agency, '{fy}' AS _fy, '{role}' AS _role,
                           '{period}' AS _period, '{src_name}' AS _source_file
                    FROM read_csv('{_sql_path(tmp_csv)}', header=true, all_varchar=true, delim='{delim}',
                                  quote='"', escape='"', max_line_size=20000000)
                ) TO '{_sql_path(out)}' (FORMAT parquet, COMPRESSION zstd)
            """)
            n = con.execute(f"SELECT count(*) FROM read_parquet('{_sql_path(out)}')").fetchone()[0]
            log(f"    {ds:<24} {Path(member).name}  ->  {n:,} rows")
            tmp_csv.unlink(missing_ok=True)
            outputs.append(str(out.relative_to(PARQUET)))
    return outputs


def _sql_path(p: Path) -> str:
    return str(p).replace("'", "''")


def convert_all(full: bool) -> None:
    if full and PARQUET.exists():
        shutil.rmtree(PARQUET)
    state = {} if full else load_json(STATE_PATH, {})
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    seen = set()
    for agency_dir in sorted(p for p in RAW.iterdir() if p.is_dir()) if RAW.exists() else []:
        agency = agency_dir.name
        manifest = load_json(agency_dir / "manifest.json", {"jobs": {}})
        for zip_path in sorted(agency_dir.glob("*/*.zip")):
            rel = str(zip_path.relative_to(RAW))
            seen.add(rel)
            st = zip_path.stat()
            sig = {"size": st.st_size, "mtime": int(st.st_mtime)}
            prev = state.get(rel)
            if prev and prev.get("sig") == sig and all((PARQUET / o).exists() for o in prev.get("outputs", [])):
                continue
            meta = job_meta(manifest, str(zip_path.relative_to(agency_dir)))
            if not meta:
                log(f"  ! {rel} is not in the manifest as downloaded; skipping")
                continue
            for o in (prev or {}).get("outputs", []):
                (PARQUET / o).unlink(missing_ok=True)
            log(f"  converting {rel}")
            t0 = time.time()
            try:
                outputs = convert_zip(con, agency, zip_path, meta)
            except zipfile.BadZipFile:
                log(f"  !! {rel} is not a valid zip (incomplete download?). Delete it and re-run fetch.py")
                continue
            state[rel] = {"sig": sig, "outputs": outputs}
            save_json(STATE_PATH, state)
            log(f"    done in {time.time() - t0:.0f}s")
    # forget zips that were removed
    for rel in list(state):
        if rel not in seen:
            for o in state[rel].get("outputs", []):
                (PARQUET / o).unlink(missing_ok=True)
            del state[rel]
    save_json(STATE_PATH, state)
    shutil.rmtree(TMP, ignore_errors=True)
    con.close()


# ----------------------------------------------------------------- database

# Unified prime_transactions columns: target -> (contract source(s), assistance source(s)).
# The first source column that exists is used; otherwise NULL.
PRIME_MAP = [
    ("transaction_key", ["contract_transaction_unique_key"], ["assistance_transaction_unique_key"]),
    ("award_key", ["contract_award_unique_key"], ["assistance_award_unique_key"]),
    ("award_id", ["award_id_piid"], ["award_id_fain", "award_id_uri"]),
    ("parent_award_id", ["parent_award_id_piid"], []),
    ("modification_number", ["modification_number"], ["modification_number"]),
    ("action_date", ["action_date"], ["action_date"]),
    ("action_type", ["action_type"], ["action_type_description"]),
    ("award_type_code", ["award_type_code", "idv_type_code"], ["assistance_type_code"]),
    ("award_type", ["award_type", "idv_type"], ["assistance_type_description"]),
    ("federal_action_obligation", ["federal_action_obligation"], ["federal_action_obligation"]),
    ("total_outlayed_amount_for_overall_award", ["total_outlayed_amount_for_overall_award"],
     ["total_outlayed_amount_for_overall_award"]),
    ("awarding_agency_code", ["awarding_agency_code"], ["awarding_agency_code"]),
    ("awarding_agency_name", ["awarding_agency_name"], ["awarding_agency_name"]),
    ("awarding_sub_agency_code", ["awarding_sub_agency_code"], ["awarding_sub_agency_code"]),
    ("awarding_sub_agency_name", ["awarding_sub_agency_name"], ["awarding_sub_agency_name"]),
    ("awarding_office_name", ["awarding_office_name"], ["awarding_office_name"]),
    ("funding_agency_code", ["funding_agency_code"], ["funding_agency_code"]),
    ("funding_agency_name", ["funding_agency_name"], ["funding_agency_name"]),
    ("funding_sub_agency_name", ["funding_sub_agency_name"], ["funding_sub_agency_name"]),
    ("recipient_uei", ["recipient_uei"], ["recipient_uei"]),
    ("recipient_name", ["recipient_name"], ["recipient_name"]),
    ("recipient_parent_uei", ["recipient_parent_uei"], ["recipient_parent_uei"]),
    ("recipient_parent_name", ["recipient_parent_name"], ["recipient_parent_name"]),
    ("recipient_city_name", ["recipient_city_name"], ["recipient_city_name"]),
    ("recipient_county_name", ["recipient_county_name"], ["recipient_county_name"]),
    ("recipient_state_code", ["recipient_state_code"], ["recipient_state_code"]),
    ("recipient_country_code", ["recipient_country_code"], ["recipient_country_code"]),
    ("recipient_cd_current", ["prime_award_transaction_recipient_cd_current"],
     ["prime_award_transaction_recipient_cd_current"]),
    ("pop_state_name", ["primary_place_of_performance_state_name"], ["primary_place_of_performance_state_name"]),
    ("pop_state_fips", ["prime_award_transaction_place_of_performance_state_fips_code"],
     ["prime_award_transaction_place_of_performance_state_fips_code"]),
    ("pop_county_name", ["primary_place_of_performance_county_name"], ["primary_place_of_performance_county_name"]),
    ("pop_cd_current", ["prime_award_transaction_place_of_performance_cd_current"],
     ["prime_award_transaction_place_of_performance_cd_current"]),
    ("program_code", ["product_or_service_code"], ["cfda_number"]),
    ("program_title", ["product_or_service_code_description"], ["cfda_title"]),
    ("naics_code", ["naics_code"], []),
    ("naics_description", ["naics_description"], []),
    ("extent_competed", ["extent_competed"], []),
    ("description", ["transaction_description"], ["transaction_description"]),
    ("base_description", ["prime_award_base_transaction_description"], ["prime_award_base_transaction_description"]),
    ("treasury_accounts_funding_this_award", ["treasury_accounts_funding_this_award"],
     ["treasury_accounts_funding_this_award"]),
    ("federal_accounts_funding_this_award", ["federal_accounts_funding_this_award"],
     ["federal_accounts_funding_this_award"]),
    ("object_classes_funding_this_award", ["object_classes_funding_this_award"], ["object_classes_funding_this_award"]),
    ("program_activities_funding_this_award", ["program_activities_funding_this_award"],
     ["program_activities_funding_this_award"]),
    ("disaster_emergency_fund_codes", ["disaster_emergency_fund_codes_for_overall_award"],
     ["disaster_emergency_fund_codes_for_overall_award"]),
    ("last_modified_date", ["last_modified_date"], ["last_modified_date"]),
    ("usaspending_permalink", ["usaspending_permalink"], ["usaspending_permalink"]),
]

DEDUPE_KEYS = {
    "contract_transactions": ["contract_transaction_unique_key"],
    "assistance_transactions": ["assistance_transaction_unique_key"],
    "contract_subawards": ["prime_award_unique_key", "subaward_sam_report_id", "subaward_number",
                           "subaward_action_date", "subaward_amount", "subawardee_uei", "subawardee_name"],
    "assistance_subawards": ["prime_award_unique_key", "subaward_sam_report_id", "subaward_number",
                             "subaward_action_date", "subaward_amount", "subawardee_uei", "subawardee_name"],
}


def columns(con, view: str) -> list[str]:
    return [r[0] for r in con.execute(f"DESCRIBE {view}").fetchall()]


def build_database() -> dict:
    tmp_db = DB_PATH.with_suffix(".building.duckdb")
    tmp_db.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp_db))
    TMP.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{_sql_path(TMP)}'")
    con.execute("SET preserve_insertion_order=false")
    if os.environ.get("FEDSPEND_MEMORY_LIMIT"):
        con.execute(f"SET memory_limit='{os.environ['FEDSPEND_MEMORY_LIMIT']}'")
    present = {}
    for ds in ACCOUNT_DATASETS + AWARD_DATASETS:
        files = list((PARQUET / ds).rglob("*.parquet")) if (PARQUET / ds).exists() else []
        if not files:
            continue
        glob = _sql_path(PARQUET / ds) + "/**/*.parquet"
        con.execute(f"CREATE VIEW raw_{ds} AS SELECT * FROM read_parquet('{glob}', union_by_name=true)")
        cols = columns(con, f"raw_{ds}")
        select = ",\n  ".join(typed_expr(c) for c in cols)
        if ds in DEDUPE_KEYS:
            keys = [k for k in DEDUPE_KEYS[ds] if k in cols]
            key_expr = "md5(concat_ws('|', " + ", ".join(f"coalesce(CAST(\"{k}\" AS VARCHAR), '')" for k in keys) + "))"
            con.execute(f"CREATE VIEW {ds}_all AS SELECT\n  {select},\n  {key_expr} AS _row_key\nFROM raw_{ds}")
            # Keep every row from the awarding pull; add funding-pull rows not already present.
            con.execute(f"""
                CREATE VIEW {ds}_v AS
                WITH a AS (SELECT * FROM {ds}_all WHERE pull_role = 'awarding'),
                     f AS (SELECT * FROM {ds}_all WHERE pull_role <> 'awarding')
                SELECT * EXCLUDE (_row_key) FROM a
                UNION ALL
                SELECT f.* EXCLUDE (_row_key) FROM f ANTI JOIN a ON f._row_key = a._row_key
            """)
        else:
            con.execute(f"CREATE VIEW {ds}_v AS SELECT\n  {select}\nFROM raw_{ds}")
        # Materialize once so every downstream query is fast (typing + dedupe are expensive).
        t0 = time.time()
        con.execute(f"CREATE TABLE {ds} AS SELECT * FROM {ds}_v")
        log(f"  table {ds:<26} {time.time() - t0:5.0f}s")
        present[ds] = len(files)

    # Unified prime_transactions
    parts = []
    for ds, cat, idx in (("contract_transactions", "contract", 1), ("assistance_transactions", "assistance", 2)):
        if ds not in present:
            continue
        cols = set(columns(con, ds))
        sel = [f"'{cat}' AS award_category", "agency_code", "fiscal_year", "pull_role"]
        for spec in PRIME_MAP:
            target, cands = spec[0], spec[idx]
            src = next((c for c in cands if c in cols), None)
            sel.append(f'"{src}" AS {target}' if src else f"NULL AS {target}")
        parts.append(f"SELECT {', '.join(sel)} FROM {ds}")
    if parts:
        con.execute("CREATE TABLE prime_transactions AS\n" + "\nUNION ALL BY NAME\n".join(parts))
        present["prime_transactions"] = 1

    # Unified subawards (column names already match across contract/assistance)
    parts = [f"SELECT '{cat}' AS award_category, * FROM {ds}"
             for ds, cat in (("contract_subawards", "contract"), ("assistance_subawards", "assistance"))
             if ds in present]
    if parts:
        con.execute("CREATE TABLE subawards AS\n" + "\nUNION ALL BY NAME\n".join(parts))
        present["subawards"] = 1

    # Hand-written analysis views
    sql_file = SQL_DIR / "models.sql"
    if sql_file.exists():
        for stmt in _split_sql(sql_file.read_text()):
            name = re.search(r"VIEW\s+(\w+)", stmt, re.IGNORECASE)
            try:
                con.execute(stmt)
                if name:
                    present[name.group(1)] = 1
            except duckdb.Error as e:
                log(f"  skipped view {name.group(1) if name else '?'}: {str(e).splitlines()[0]}")
    con.close()
    os.replace(tmp_db, DB_PATH)
    wal = tmp_db.with_suffix(tmp_db.suffix + ".wal")
    wal.unlink(missing_ok=True)
    return present


def _split_sql(text: str) -> list[str]:
    text = re.sub(r"--[^\n]*", "", text)
    return [s.strip() for s in text.split(";") if s.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="reconvert every zip")
    args = ap.parse_args()
    t0 = time.time()
    zips = list(RAW.glob("*/*/*.zip")) if RAW.exists() else []
    if not zips:
        raise SystemExit(
            f"No downloaded files found in {RAW}.\n"
            "Run  python scripts/fetch.py  first and let it finish "
            "(it ends with 'Finished in ... min: N downloaded').")
    log("Converting downloads to Parquet")
    convert_all(args.full)
    log("Building DuckDB database")
    present = build_database()
    if not present:
        log("No data found. Run fetch.py first.")
        return
    con = duckdb.connect(str(DB_PATH), read_only=True)
    log("Views:")
    for name in present:
        try:
            n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            log(f"  {name:<32} {n:>12,} rows")
        except duckdb.Error as e:
            log(f"  {name:<32} error: {str(e).splitlines()[0]}")
    con.close()
    size = sum(p.stat().st_size for p in PARQUET.rglob("*.parquet")) / 1e9
    log(f"Done in {time.time() - t0:.0f}s. Parquet size: {size:.2f} GB. Database: {DB_PATH}")
    log("Next: python scripts/validate.py")


if __name__ == "__main__":
    main()
