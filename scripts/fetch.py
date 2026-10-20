#!/usr/bin/env python3
"""Download USAspending data for one agency into data/raw/<agency>/.

What it pulls (see SPEC.md section 2):
  * Account data (Files A, B, C) per fiscal year, at the latest revealed period
  * Prime award transactions + sub-awards per fiscal year, once with the agency
    as AWARDING agency and once as FUNDING agency
  * Reference snapshots used by validate.py

Usage:
  python scripts/fetch.py                     # DOJ, FY2017 -> current FY
  python scripts/fetch.py --dry-run           # show what would be requested
  python scripts/fetch.py --only accounts     # just account data
  python scripts/fetch.py --start-fy 2022     # narrower window
  python scripts/fetch.py --agency 070        # another agency (e.g. DHS)

Safe to stop (Ctrl-C) and re-run: progress is tracked in manifest.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.client as httpclient
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    API_BASE, FIRST_ACCOUNT_FY, PRIME_AWARD_TYPES, SUB_AWARD_TYPES,
    agency_raw_dir, current_fiscal_year, fy_bounds, load_json, log, save_json,
)

USER_AGENT = "fedspend-pipeline/1.0 (research; contact via thejusticeconnection.org)"
POLL_SECONDS = int(os.environ.get("FEDSPEND_POLL_SECONDS", "20"))
JOB_TIMEOUT_SECONDS = 3 * 60 * 60
MAX_ATTEMPTS = 3


# --------------------------------------------------------------------------- HTTP

def _ssl_context():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL_CTX = _ssl_context()


def http(method: str, url: str, body: dict | None = None, retries: int = 5, timeout: int = 120):
    if not url.startswith("http"):
        url = API_BASE.rstrip("/") + url
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    delay = 5
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                log(f"  HTTP {e.code} from {url}; retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
            raise RuntimeError(f"HTTP {e.code} {method} {url}: {detail}") from None
        except NETWORK_ERRORS as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError) or "CERTIFICATE" in str(e):
                raise RuntimeError(
                    "SSL certificate error. Run:  pip install certifi   (inside the venv), "
                    "or run 'Install Certificates.command' from your Python folder."
                ) from None
            if attempt < retries:
                log(f"  network error ({e}); retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
            raise


NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, httpclient.HTTPException, OSError)


def download_file(url: str, dest: Path, retries: int = 5) -> int:
    if not url.startswith("http"):
        url = API_BASE.rstrip("/") + url
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    delay = 10
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        total = 0
        try:
            with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as resp, open(part, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            os.replace(part, dest)
            return total
        except NETWORK_ERRORS as e:
            if attempt == retries:
                raise
            log(f"  download interrupted ({type(e).__name__}); retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------- reference

def fetch_reference(agency: str, start_fy: int, end_fy: int, ref_dir: Path) -> dict:
    """Save reference snapshots and return agency info + latest period per FY."""
    log("Fetching reference data")
    agencies = http("GET", "/api/v2/references/toptier_agencies/")
    save_json(ref_dir / "toptier_agencies.json", agencies)
    match = [a for a in agencies.get("results", []) if a.get("toptier_code") == agency]
    if not match:
        raise SystemExit(f"Agency code {agency} not found in /references/toptier_agencies/")
    info = match[0]
    log(f"  agency {agency} = {info['agency_name']} ({info.get('abbreviation')}), id {info.get('agency_id')}")

    periods = http("GET", "/api/v2/references/submission_periods/")
    save_json(ref_dir / "submission_periods.json", periods)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    latest: dict[int, int] = {}
    for p in periods.get("available_periods", []):
        if (p.get("submission_reveal_date") or "9999") <= now:
            fy = int(p["submission_fiscal_year"])
            latest[fy] = max(latest.get(fy, 0), int(p["submission_fiscal_month"]))

    budg = http("GET", f"/api/v2/agency/{agency}/budgetary_resources/")
    save_json(ref_dir / "budgetary_resources.json", budg)

    start, end = fy_bounds(start_fy)[0], fy_bounds(end_fy)[1]
    for sub in (False, True):
        body = {
            "group": "fiscal_year",
            "subawards": sub,
            "filters": {
                "agencies": [{"type": "awarding", "tier": "toptier", "name": info["agency_name"]}],
                "time_period": [{"start_date": start, "end_date": end}],
            },
        }
        res = http("POST", "/api/v2/search/spending_over_time/", body)
        save_json(ref_dir / f"spending_over_time_awarding_{'subawards' if sub else 'prime'}.json", res)

    snap = {"fetched_at": now, "agency": info, "latest_period_by_fy": {str(k): v for k, v in sorted(latest.items())}}
    save_json(ref_dir / "snapshot_info.json", snap)
    return {"info": info, "latest": latest}


def fetch_federal_accounts(agency: str, fy: int, ref_dir: Path) -> list[dict]:
    """List the agency's federal accounts for a fiscal year (used to split File C)."""
    path = ref_dir / "federal_accounts" / f"FY{fy}.json"
    results, page = [], 1
    while True:
        res = http("POST", "/api/v2/federal_accounts/", {
            "filters": {"agency_identifier": agency, "fy": str(fy)},
            "limit": 100, "page": page,
            "sort": {"field": "budgetary_resources", "direction": "desc"},
        })
        results.extend(res.get("results", []))
        if not res.get("hasNext"):
            break
        page += 1
    save_json(path, results)
    return results


# ---------------------------------------------------------------------- job plan

def plan_jobs(agency: str, info: dict, latest: dict, start_fy: int, end_fy: int, only: str | None,
              roles: list[str], manifest: dict, force: bool, max_age_days: int,
              with_file_c: bool = False, fed_accounts: dict | None = None) -> list[dict]:
    jobs = []
    fed_accounts = fed_accounts or {}
    cur_fy = current_fiscal_year()
    now = dt.datetime.now()

    def stale(prev: dict | None) -> bool:
        if prev is None or prev.get("status") not in ("downloaded",):
            return True
        if force:
            return True
        got = dt.datetime.fromisoformat(prev["downloaded_at"])
        return (now - got).days >= max_age_days

    if only in (None, "accounts"):
        for fy in range(max(start_fy, FIRST_ACCOUNT_FY), end_fy + 1):
            period = latest.get(fy)
            if not period:
                log(f"  FY{fy}: no account submissions revealed yet; skipping account data")
                continue
            # One job per file type: asking for A+B+C together fails server-side for DOJ.
            # File C (award financial) is too large even alone, so it is split by federal account.
            labels = [("account_balances", "A"), ("object_class_program_activity", "B")]
            for sub_type, label in labels + ([("award_financial", "C")] if with_file_c else []):
                if label == "C":
                    parts = [(str(a["account_id"]), a.get("account_number") or str(a["account_id"]))
                             for a in fed_accounts.get(fy, [])]
                else:
                    parts = [(None, None)]
                for fa_id, fa_num in parts:
                    key = f"accounts_FY{fy}_{label}" + (f"_{fa_num}" if fa_num else "")
                    prev = manifest["jobs"].get(key)
                    needs = (prev is None or prev.get("status") != "downloaded" or force
                             or int(prev.get("period", 0)) < period)
                    if not needs:
                        continue
                    filters = {
                        "agency": info.get("abbreviation") or str(info["agency_id"]),
                        "fy": str(fy),
                        "period": str(max(period, 2)),
                        "submission_types": [sub_type],
                    }
                    if fa_id:
                        filters["federal_account"] = fa_id
                    body = {"account_level": "treasury_account", "file_format": "csv", "filters": filters}
                    dest = f"accounts/FY{fy}_{label}" + (f"_{fa_num}" if fa_num else "") + ".zip"
                    jobs.append({"key": key, "kind": "accounts", "fy": fy, "period": period, "file": label,
                                 "endpoint": "/api/v2/download/accounts/", "request": body, "dest": dest})

    if only in (None, "awards"):
        for fy in range(start_fy, end_fy + 1):
            for role in roles:
                key = f"awards_FY{fy}_{role}"
                prev = manifest["jobs"].get(key)
                recent = fy >= cur_fy - 1  # recent years keep changing; refresh them
                if prev and prev.get("status") == "downloaded" and not force and not (recent and stale(prev)):
                    continue
                start, end = fy_bounds(fy)
                body = {
                    "file_format": "csv",
                    "filters": {
                        "prime_award_types": PRIME_AWARD_TYPES,
                        "sub_award_types": SUB_AWARD_TYPES,
                        "date_type": "action_date",
                        "date_range": {"start_date": start, "end_date": end},
                        "agencies": [{"type": role, "tier": "toptier", "name": info["agency_name"]}],
                    },
                }
                jobs.append({"key": key, "kind": "awards", "fy": fy, "role": role,
                             "endpoint": "/api/v2/bulk_download/awards/", "request": body,
                             "dest": f"awards/FY{fy}_{role}.zip"})
    return jobs


# ---------------------------------------------------------------------- runner

class Runner:
    def __init__(self, agency: str, max_in_flight: int):
        self.dir = agency_raw_dir(agency)
        self.manifest_path = self.dir / "manifest.json"
        self.manifest = load_json(self.manifest_path, {"agency": agency, "jobs": {}})
        self.max_in_flight = max_in_flight
        self.attempts: dict[str, int] = {}  # submissions per job in this run

    def save(self):
        save_json(self.manifest_path, self.manifest)

    def record(self, job: dict, **fields):
        entry = self.manifest["jobs"].setdefault(job["key"], {})
        entry.update({k: v for k, v in job.items() if k != "request"})
        entry["request"] = job["request"]
        entry.update(fields)
        self.save()
        return entry

    def submit(self, job: dict) -> dict:
        resp = http("POST", job["endpoint"], job["request"])
        log(f"  submitted {job['key']} -> {resp.get('file_name')}")
        self.attempts[job["key"]] = self.attempts.get(job["key"], 0) + 1
        return self.record(job, status="submitted", file_name=resp["file_name"],
                           file_url=resp.get("file_url"), submitted_at=dt.datetime.now().isoformat(),
                           error=None)

    def run(self, jobs: list[dict]):
        queue = list(jobs)
        in_flight: dict[str, dict] = {}
        # Resume jobs that were submitted in an earlier run and never downloaded.
        for job in list(queue):
            prev = self.manifest["jobs"].get(job["key"])
            if prev and prev.get("status") == "submitted" and prev.get("request") == job["request"]:
                in_flight[job["key"]] = job
                queue.remove(job)
                log(f"  resuming {job['key']} ({prev.get('file_name')})")

        done = failed = 0
        while queue or in_flight:
            while queue and len(in_flight) < self.max_in_flight:
                job = queue.pop(0)
                if self.attempts.get(job["key"], 0) >= MAX_ATTEMPTS:
                    log(f"  !! {job['key']}: giving up after {MAX_ATTEMPTS} attempts")
                    self.record(job, status="failed", error="too many attempts")
                    failed += 1
                    continue
                try:
                    self.submit(job)
                    in_flight[job["key"]] = job
                except Exception as e:  # noqa: BLE001
                    log(f"  !! could not submit {job['key']}: {e}")
                    self.record(job, status="failed", error=str(e))
                    failed += 1
            if not in_flight:
                break
            time.sleep(POLL_SECONDS)
            for key in list(in_flight):
                job = in_flight[key]
                entry = self.manifest["jobs"][key]
                try:
                    st = http("GET", "/api/v2/download/status/?file_name="
                              + urllib.parse.quote(entry["file_name"]))
                except RuntimeError as e:
                    if "HTTP 4" in str(e):  # job unknown/expired: resubmit
                        log(f"  {key}: status lookup failed ({e}); resubmitting")
                        del in_flight[key]
                        queue.append(job)
                        continue
                    log(f"  {key}: status check error ({e}); will check again")
                    continue
                except NETWORK_ERRORS as e:
                    log(f"  {key}: status check interrupted ({type(e).__name__}); will check again")
                    continue
                status = st.get("status")
                if status == "finished":
                    dest = self.dir / job["dest"]
                    log(f"  {key}: finished ({st.get('total_rows')} rows); downloading")
                    try:
                        nbytes = download_file(st.get("file_url") or entry["file_url"], dest)
                    except NETWORK_ERRORS as e:
                        log(f"  {key}: download failed ({type(e).__name__}); will try again next round")
                        continue
                    self.record(job, status="downloaded", downloaded_at=dt.datetime.now().isoformat(),
                                bytes=nbytes, total_rows=st.get("total_rows"), path=job["dest"])
                    log(f"  {key}: saved {job['dest']} ({nbytes / 1e6:.1f} MB)")
                    del in_flight[key]
                    done += 1
                elif status == "failed":
                    msg = st.get("message")
                    del in_flight[key]
                    if self.attempts.get(key, 1) < MAX_ATTEMPTS:
                        log(f"  {key}: generation failed ({msg}); will retry")
                        queue.append(job)
                    else:
                        log(f"  !! {key}: failed {MAX_ATTEMPTS} times ({msg})")
                        self.record(job, status="failed", error=msg)
                        failed += 1
                else:
                    started = dt.datetime.fromisoformat(entry["submitted_at"])
                    waited = (dt.datetime.now() - started).total_seconds()
                    if waited > JOB_TIMEOUT_SECONDS:
                        log(f"  !! {key}: still {status} after {waited / 3600:.1f}h; resubmitting")
                        del in_flight[key]
                        queue.append(job)
            if in_flight:
                running = ", ".join(sorted(in_flight))
                log(f"  waiting on {len(in_flight)} job(s) [{running}], {len(queue)} queued, {done} done, "
                    f"{failed} failed")
        return done, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agency", default="015", help="toptier agency code (default 015 = DOJ)")
    ap.add_argument("--start-fy", type=int, default=FIRST_ACCOUNT_FY)
    ap.add_argument("--end-fy", type=int, default=current_fiscal_year())
    ap.add_argument("--only", choices=["accounts", "awards"], help="pull just one family")
    ap.add_argument("--roles", default="awarding,funding",
                    help="award pulls to make: awarding, funding, or both (default)")
    ap.add_argument("--max-in-flight", type=int, default=4, help="concurrent server-side jobs")
    ap.add_argument("--max-age-days", type=int, default=7,
                    help="re-pull current/previous FY award files older than this")
    ap.add_argument("--with-file-c", action="store_true",
                    help="also pull File C (award financial), split into one job per federal account; slow")
    ap.add_argument("--force", action="store_true", help="re-download everything in range")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, submit nothing")
    args = ap.parse_args()

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    for r in roles:
        if r not in ("awarding", "funding"):
            raise SystemExit(f"bad role {r!r}")

    runner = Runner(args.agency, args.max_in_flight)
    ref = fetch_reference(args.agency, args.start_fy, args.end_fy, runner.dir / "reference")
    fed_accounts = {}
    if args.with_file_c and args.only in (None, "accounts"):
        log("Listing federal accounts (for File C)")
        for fy in range(max(args.start_fy, FIRST_ACCOUNT_FY), args.end_fy + 1):
            if ref["latest"].get(fy):
                fed_accounts[fy] = fetch_federal_accounts(args.agency, fy, runner.dir / "reference")
                log(f"  FY{fy}: {len(fed_accounts[fy])} federal accounts")
    jobs = plan_jobs(args.agency, ref["info"], ref["latest"], args.start_fy, args.end_fy, args.only,
                     roles, runner.manifest, args.force, args.max_age_days, args.with_file_c, fed_accounts)

    log(f"Plan: {len(jobs)} download job(s)")
    for j in jobs:
        extra = f"File {j['file']}, period P{j['period']:02d}" if j["kind"] == "accounts" else f"role={j['role']}"
        log(f"  {j['key']:<28} {extra}")
    if args.dry_run or not jobs:
        if not jobs:
            log("Everything is up to date.")
        return

    t0 = time.time()
    try:
        done, failed = runner.run(jobs)
    except KeyboardInterrupt:
        log("Interrupted. Progress saved; re-run the same command to resume.")
        sys.exit(130)
    log(f"Finished in {(time.time() - t0) / 60:.1f} min: {done} downloaded, {failed} failed")
    if failed:
        log("Re-run the same command to retry failed jobs.")
        sys.exit(1)
    log("Next: python scripts/build.py")


if __name__ == "__main__":
    main()
