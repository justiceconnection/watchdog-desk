# Watchdog Desk (app)

The public site of pattern cards (spec: `docs/specs/watchdog-desk.md`).

Vite + React + TypeScript, Observable Plot, DuckDB-WASM (`src/db.ts`, ready for the card marts; not used yet).

    cd app && npm install
    npm run dev      # http://127.0.0.1:5190
    npm run build    # type-check + production build (copies only marts/<agency>/desk/ into dist/marts)

## What is here

- `src/cards/types.ts`: the card shape (headline, why it stands out, chart, table, caveats, how calculated, status, meta).
- `src/cards/card4.ts`: card 4 ("States that stand out") read from `marts/<agency>/desk/card4_*.parquet` through DuckDB-WASM (docs/data-contract.md section 10.1). Only rows with status `card` or `label` are shown. All reader text (headline, label sentence, why it stands out, fixed line, caveats) is pre-rendered in the marts and shown as is. The chart is state vs rest of the country indexed to the prior year = 100, with hatching for provisional periods; driver tables show components, programs and recipients; an award-cycle panel appears for complete grant years. The methods page (`?page=methods`, "How the cards work") shows the fiscal analyst's reader text verbatim: `scripts-methods.mjs` copies Appendix C of `docs/methods.md` (HTML source notes removed, never rendered) into `src/methodsContent.ts` on every dev start and build. It also lists the national organizations from `card4_national_orgs`.
- `src/cards/natorg.ts`: the national-organizations card (`natorg_*`, data contract 10.4): group vs all other grant recipients, indexed chart, award-cycle evidence, components, programs, top-10 organizations, caveats (including the DC footnote).
- `src/cards/card2.ts`: Card 2, contracts without competition (`card2_*`, data contract 10.5): one card for all years (dollar and count share by year, utilities as a separate band, provisional year hatched), with a year selector for the reasons, recipient types (business flags shown as overlapping, never summed) and the top awards (when `show_top_awards`).
- `src/cards/card3.ts`: Card 3, grants by Justice Connection category (`card3_*`, data contract 10.8): one card per published (fiscal year, category). The chart shows the category, SCAAP (its own segment) and all other categories as shares of the headline scope; gap years add a same-months (October to July) chart with the provisional year hatched, and every card has an award-cycle check. Listings table highlights the top 3 drivers. Fiscal years before the latest two are behind "Include earlier years" on the desk; the desk also filters by grant category.
- There are no placeholder cards. A card type with no published cards has no filter chip.
- Every card shows "Not yet verified" until the verifier's sign-off date is set in `status.verified`.
- `src/cards/csv.ts`: "Download CSV". Real cards download the prebuilt `desk/csv/<card_id>.csv` (its `#` header lines are kept; a status line is added on top). Placeholder cards generate theirs in the browser: the file starts with `#` metadata lines (card, status, definition, period, source, data date, each caveat, how calculated), then the column header and the rows.
- `src/components/`: `CardView` (full card, in the spec's order), `CardPreview` (desk list item), `CardChart` (bar, stacked, and diverging chart; provisional periods hatched; redraws on theme change), `CardTable`, `Status`.
- The desk is a split list and detail from 760 px up (a vertical tablist on the left, the selected card on the right) and an accordion below 760 px (one card open at a time; focus moves to its heading). List rows show the headline, type and period, a sparkline and a key number, all taken from fields and series already in the marts (`key` and `spark` on each card). The type and category filters and the earlier-years switch apply to the list. The URL keeps `?card=`, `?type=` (the old `?type=state_anomaly` still works), `?category=` and `?earlier=1`; with no `?card=` the first visible card is selected.

## Adding a real card

Build a `Card` from a mart (read through `src/db.ts`) and return it from the card source in `App.tsx`. Set `placeholder: false`, and set `status.verified` to a date only after the verifier signs off. Nothing else changes.

## Design notes

Plain language, serif headlines, one signal colour; light and dark (follows the system, with a toggle); 44 px touch targets; charts have a text alternative and the same numbers in the table; works at 390 px. Screenshots: `screenshots/`.

`npm run dev`/`build` first run `scripts-link-desk.mjs`, which links only the files listed in `marts/<agency>/desk/manifest.json` (parquet and published CSVs) into `public/marts/`. If the manifest is missing it stops with a message instead of linking everything; `marts/` is never written. Add `?agency=XXX` to the URL for another agency that has a desk folder.

## Deploy and embed

The site is static and path-independent (`base: './'` in `vite.config.ts`): it works at a project-pages subpath (`https://<org>.github.io/<repo>/`), at a custom domain, and inside an iframe. Every fetch, worker and wasm URL is relative to the page.

Deploy: the public repo keeps the same layout as the private one. `deploy/github-pages.yml` is copied to `.github/workflows/pages.yml`; on push to `main` (or manual run) it runs `npm ci` and `npm run build` in `app/`, adds `.nojekyll`, and publishes `app/dist` with the official Pages actions. In the repo settings, set Pages source to "GitHub Actions".

Files the build needs outside `app/` (the prebuild scripts read them):
- `marts/<agency>/desk/manifest.json` and every file it lists (`card_types.*.parquet` and `card_types.*.published_csvs`, paths relative to `marts/<agency>/`). Nothing else under `marts/` is read.
- `docs/methods.md` (only its "Appendix C: Reader text for the methods page" is used).
- Inside `app/`: `package.json`, `package-lock.json`, `index.html`, `tsconfig.json`, `vite.config.ts`, `scripts-*.mjs`, `src/`, `deploy/`. Not needed: `node_modules`, `dist`, `public/marts` (regenerated), `screenshots`.

Embed on another site (replace the address):

    <iframe src="https://<org>.github.io/<repo>/" title="Watchdog Desk: patterns in Justice Department spending"
      loading="lazy" style="width:100%;min-height:900px;border:0" allow="fullscreen"></iframe>
    <p><a href="https://<org>.github.io/<repo>/" target="_blank" rel="noopener">Open the Watchdog Desk in its own page</a></p>

The page does not resize the iframe, so the card detail scrolls inside it; use a height of 900 px or more (taller on phones if the host allows). Links to USAspending open in a new tab (`target="_blank" rel="noreferrer"`, which implies noopener), theme storage is wrapped in try/catch (blocked third-party storage falls back to the system theme), and nothing touches `window.top`. Deep links work in the iframe `src`, for example `?card=<card_id>`.

## Frozen-state hash (for verification runs)

Run from `app/`; it covers the source and config but not `node_modules`, `dist`, `public` (the linked marts) or `screenshots`:

    find . -path ./node_modules -prune -o -path ./dist -prune -o -type f -print | grep -v screenshots | grep -v '^./public' | sort | xargs shasum | shasum

## Reports and repo paths

Reader text never shows repo paths. The "Verified <date>" badge and the "How this is calculated" links to metrics, queries and reports appear only when `VITE_REPORT_BASE` is set at build time (the public address where the reports are published); otherwise the badge reads "Verified <date>" with no link.
