"""Watchdog Desk publishing helpers: verification sign-offs and the manifest.

- Sign-offs: a CSV with columns card_id, card_type, verified_date (other columns are ignored). It is read from the
  review records when they are present, otherwise from sql/seeds/desk_signoffs.csv (see signoffs_path()). A row with
  card_id applies to that card; a row with only card_type applies to every card of that type. The card_id match wins;
  among several matches the latest verified_date wins. Missing file -> NULL verified_on. verified_in is always NULL
  (kept as a column so the table shape does not change).
- Public subset (held means not public): marts/<agency>/desk/public/<same name>.parquet holds, for every table the UI
  reads, only the rows of PUBLISHED cards = status card/label AND verified_on set AND card_id listed in the sign-offs.
  Same names and schemas as the full marts in desk/, which stay for internal use and checks.
- Manifest: marts/<agency>/desk/manifest.json lists, per card type, the PUBLIC Parquet files and the CSVs of published
  cards. Written with sorted keys and no build time, so it is reproducible.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# Sign-off file: the review records' copy when present, else the seed copy (card_id, card_type, verified_date).
SIGNOFFS_CANDIDATES = (ROOT / "docs" / "qa" / "desk_signoffs.csv", ROOT / "sql" / "seeds" / "desk_signoffs.csv")


def signoffs_path() -> Path:
    """The first sign-off file that exists; the seed path when neither does (callers treat a missing file as empty)."""
    return next((p for p in SIGNOFFS_CANDIDATES if p.exists()), SIGNOFFS_CANDIDATES[-1])


PUBLISHED = ("card", "label")
# How each UI table is reduced to published cards. "card_id": rows of published cards; "card2_fy": Card 2 rows for
# fiscal years whose card2-<agency>-<fy> card is published; "whole": no card-specific rows or text (templates, params,
# scheme, chart aggregates); reconcile_desk.sql checks that no held-card id or held-only text reaches a public file.
PUBLIC_TABLES = {
    "card4_cards": "card_id", "card4_caveats": "card_id", "card4_components": "card_id", "card4_programs": "card_id",
    "card4_recipients": "card_id", "card4_series": "card_id", "card4_national_orgs": "whole", "card4_params": "whole",
    "card4_text": "whole",
    "natorg_cards": "card_id", "natorg_caveats": "card_id", "natorg_components": "card_id", "natorg_organizations": "card_id",
    "natorg_programs": "card_id", "natorg_series": "card_id",
    "card3_cards": "card_id", "card3_caveats": "card_id", "card3_listings": "card_id", "card3_categories": "whole",
    "card3_cvf_cap": "whole", "card3_mix": "whole", "card3_periods": "whole", "card3_text": "whole",
    "card2_summary": "card2_fy", "card2_reasons": "card2_fy", "card2_recipient_types": "card2_fy", "card2_top_awards": "card2_fy",
    "card2_text": "whole",
}
CARD_TABLES = ("desk_card4_cards", "desk_natorg_cards", "desk_card3_cards", "desk_card2_summary")


def write_public(con, desk_dir: Path, agency: str) -> list[Path]:
    """Write desk/public/*.parquet: the UI tables reduced to published cards (deterministic: ORDER BY ALL, zstd)."""
    ids = sorted({r["card_id"] for r in load_signoffs() if r.get("card_id")})
    con.execute("CREATE OR REPLACE TEMP TABLE _desk_signoff_ids AS SELECT unnest(?::VARCHAR[]) AS card_id", [ids])
    con.execute("CREATE OR REPLACE TEMP TABLE _desk_pub AS " + " UNION ".join(
        f"SELECT card_id FROM {t} WHERE status IN ('card', 'label') AND verified_on IS NOT NULL "
        f"AND card_id IN (SELECT card_id FROM _desk_signoff_ids)" for t in CARD_TABLES))
    out = desk_dir / "public"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.parquet"):
        old.unlink()
    paths = []
    for name, rule in sorted(PUBLIC_TABLES.items()):
        where = {"card_id": "card_id IN (SELECT card_id FROM _desk_pub)",
                 "card2_fy": f"('card2-{agency}-' || fiscal_year) IN (SELECT card_id FROM _desk_pub)",
                 "whole": "true"}[rule]
        p = out / f"{name}.parquet"
        con.execute(f"COPY (SELECT * FROM desk_{name} WHERE {where} ORDER BY ALL) TO '{p.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        paths.append(p)
    return paths


def load_signoffs() -> list[dict]:
    path = signoffs_path()
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f)]


def apply_signoffs(rows: list[dict], card_type: str, signoffs: list[dict]) -> None:
    for r in rows:
        by_id = [s for s in signoffs if (s.get("card_id") or "") == r["card_id"]]
        # card_type rows match the current id and the pre-rename alias (state_anomaly -> state_stand_out)
        alias = {"state_stand_out": {"state_stand_out", "state_anomaly"}}.get(card_type, {card_type})
        by_type = [s for s in signoffs if not (s.get("card_id") or "") and (s.get("card_type") or "") in alias]
        pick = sorted(by_id or by_type, key=lambda s: s.get("verified_date") or "")
        r["verified_on"] = pick[-1].get("verified_date") or None if pick else None
        # The review report is never written into the card tables: verified_in stays as a column, always NULL,
        # so a build from the stripped sign-off file (card_id, card_type, verified_date) gives the same bytes.
        r["verified_in"] = None


def write_manifest(desk_dir: Path, agency: str, data_as_of, types: dict, published_ids: set) -> list[Path]:
    """Two files, sorted keys, no build time (reproducible):
    - manifest.json (deployed; the app loads it): published cards only, i.e. published_ids (status card/label, verified,
      signed off), their CSVs, and the desk/public Parquet files. It never names a held or suppressed card.
    - manifest_internal.json (not deployed: the link script copies only manifest.json and what it lists): every card,
      with status and CSV path, for the build and the checks.
    types: {card_type: [(card_id, status, csv_relpath), ...]}; Parquet files are matched by prefix."""
    prefixes = {"state_stand_out": "card4_", "national_organizations": "natorg_", "contracts_without_competition": "card2_", "grant_categories": "card3_"}
    pub, internal = {"agency_code": agency, "data_as_of": str(data_as_of), "published_statuses": list(PUBLISHED), "card_types": {}}, \
        {"agency_code": agency, "data_as_of": str(data_as_of), "published_statuses": list(PUBLISHED), "card_types": {},
         "note": "Internal: not deployed. Lists every card, including held and suppressed ones."}
    for ct, cards in sorted(types.items()):
        pq = sorted(f"desk/public/{p.name}" for p in (desk_dir / "public").glob(f"{prefixes[ct]}*.parquet"))
        shown = [c for c in cards if c[0] in published_ids]
        pub["card_types"][ct] = {
            "parquet": pq,
            "cards": [{"card_id": cid, "status": st, "csv": csvp} for cid, st, csvp in sorted(shown)],
            "published_csvs": sorted({csvp for _, _, csvp in shown if csvp}),
        }
        internal["card_types"][ct] = {
            "parquet_public": pq,
            "parquet_full": sorted(f"desk/{p.name}" for p in desk_dir.glob(f"{prefixes[ct]}*.parquet")),
            "cards": [{"card_id": cid, "status": st, "csv": csvp, "published": cid in published_ids} for cid, st, csvp in sorted(cards)],
        }
    paths = []
    for name, obj in (("manifest.json", pub), ("manifest_internal.json", internal)):
        p = desk_dir / name
        p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(p)
    return paths
