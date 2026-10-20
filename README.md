# Watchdog Desk

The Watchdog Desk is a public site of plain-language "pattern cards" about federal spending. It uses data from
[USAspending.gov](https://www.usaspending.gov), starting with the U.S. Department of Justice (agency code `015`).
It is built by [Justice Connection](https://www.thejusticeconnection.org).

Each card describes **what changed** in the spending data, such as a state whose grant dollars rose sharply or a
year in which more contracts were awarded without competition. Cards do not say **why** something changed, and
nothing on the site indicates that anything improper happened. Each card links to its method, shows its caveats,
and offers a CSV of the rows behind it.

## Run the site locally

You need Node.js 18 or later.

```bash
cd app
npm ci
npm run dev
```

Then open the address Vite prints (usually http://localhost:5173). `npm run build` makes the production site in
`app/dist`, and `npm run preview` serves it.

The site reads small published data files in `marts/<agency>/desk/`. Only cards that passed review are included.

## Where the numbers come from

The metric definitions, with the reasoning behind each, are in [`docs/metrics.md`](docs/metrics.md). The data
contract that the site reads is in [`docs/data-contract.md`](docs/data-contract.md). The card methods are in
[`docs/methods.md`](docs/methods.md), which is also the text of the "How the cards work" page on the site (`?page=methods`). If the site is built with `VITE_REPORT_BASE` set, each card also links to its verification report under that address; otherwise it shows the verified date only.

## Rebuild the data

The pipeline needs Python 3.9 or later. Set it up with `bash scripts/setup.sh`, or install `requirements.txt`
into a virtual environment. Then, from the repository root:

```bash
python scripts/fetch.py             # download from the USAspending API into data/raw (long; resumable)
python scripts/build.py             # convert to Parquet and build data/fedspend.duckdb
python scripts/validate.py          # check totals against USAspending's published figures
python sql/build_marts.py --agency 015    # build the small marts the site reads into marts/
```

Use any agency code in place of `015`. See [`SPEC.md`](SPEC.md) for the pipeline design. The `data/` folder is not
in this repository, because everything in it can be rebuilt from the API.

`build_marts.py` also accepts `--desk-only` to rebuild only the card data in `marts/<agency>/desk/`. Card
sign-off dates are read from `sql/seeds/desk_signoffs.csv`. The one reference file the cards read,
`reference/ojp_dashboard/2026-10-16/AwardsByStateAndCity.csv`, is a published export from the Office of Justice
Programs (OJP) awards dashboard.

## Deploy

The site deploys to GitHub Pages with the workflow in `.github/workflows/pages.yml`. Push to `main` and enable
Pages with "GitHub Actions" as the source.

## For maintainers: releasing an update

This repository is assembled from Justice Connection's private working repository by an export script, so the history
here is a plain series of releases. To publish an update:

1. In the working repository, rebuild and verify the data (`bash scripts/refresh.sh`, then
   `python sql/build_marts.py --agency 015`) and finish the review of any changed cards.
2. Clone this repository next to the working one (`git clone <url> watchdog-desk-public`).
3. From the working repository run `python scripts/export_public.py --update --out ../watchdog-desk-public`.
   Add `--message "..."` to describe the release. The script replaces the tracked files, checks the result for
   internal terms, and makes a normal new commit on top of the existing history. It refuses to run if the clone has
   uncommitted changes.
4. In the clone, check `git show --stat`, run `cd app && npm ci && npm run build`, then `git push`. A normal push is
   enough; no force-push is ever needed.

The `.gitignore` here ignores everything under `marts/` except the published files named in
`marts/<agency>/desk/manifest.json`, so rebuilding data locally cannot stage unpublished files by accident.

## Data notes

- Dollar figures are nominal (not adjusted for inflation).
- Obligations and outlays are different measures and are never added together.
- The current fiscal year is provisional.
- Sub-award amounts are self-reported by recipients and are a floor, not a total.

## License

- **Code** (`app/`, `scripts/`, `sql/`, `.github/`): [MIT License](LICENSE), copyright 2026 Justice Connection.
- **Content** (card text, documentation in `docs/`, `README.md` and `SPEC.md`, and the derived data files in `marts/`):
  [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) (see
  [`LICENSE-CONTENT`](LICENSE-CONTENT)). Please credit "Justice Connection".

The underlying USAspending.gov and OJP source data are U.S. government works in the public domain. The content
license covers only Justice Connection's selection, analysis and text.
