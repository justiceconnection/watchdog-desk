"""Shared paths, constants and helpers for the fed spending pipeline."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PARQUET = DATA / "parquet"
DB_PATH = DATA / "fedspend.duckdb"
LOGS = ROOT / "logs"
SQL_DIR = ROOT / "sql"

API_BASE = os.environ.get("USASPENDING_API", "https://api.usaspending.gov")
FILES_BASE = os.environ.get("USASPENDING_FILES", "https://files.usaspending.gov")

DEFAULT_AGENCY = "015"  # Department of Justice (CGAC toptier code)
FIRST_ACCOUNT_FY = 2017  # DATA Act account reporting begins FY2017

# Every prime award type the bulk download accepts (contracts, IDVs, assistance).
PRIME_AWARD_TYPES = [
    "A", "B", "C", "D",
    "IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E",
    "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "-1",
]
SUB_AWARD_TYPES = ["procurement", "grant"]
ACCOUNT_SUBMISSION_TYPES = ["account_balances", "object_class_program_activity", "award_financial"]

# Map a CSV inside a downloaded zip to a dataset name, by filename fragment.
# Order matters: first match wins.
DATASET_PATTERNS = [
    ("AccountBreakdownByAward", "award_financial"),
    ("AccountBreakdownByPA-OC", "account_activity"),
    ("AccountBalances", "account_balances"),
    ("Contracts_PrimeTransactions", "contract_transactions"),
    ("Assistance_PrimeTransactions", "assistance_transactions"),
    ("Contracts_Subawards", "contract_subawards"),
    ("Assistance_Subawards", "assistance_subawards"),
]


def classify_csv(name: str) -> str | None:
    base = Path(name).name
    for frag, ds in DATASET_PATTERNS:
        if frag in base:
            return ds
    return None


def current_fiscal_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year + 1 if today.month >= 10 else today.year


def fy_bounds(fy: int) -> tuple[str, str]:
    return f"{fy - 1}-10-01", f"{fy}-09-30"


def agency_raw_dir(agency: str) -> Path:
    return RAW / agency


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)
