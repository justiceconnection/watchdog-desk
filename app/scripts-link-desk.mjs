// Makes only the published desk files visible to Vite, as listed by marts/<agency>/desk/manifest.json
// (card_types.*.parquet and card_types.*.published_csvs): public/marts/<agency>/desk/<file> -> marts/<agency>/desk/<file>.
// If an agency has a desk folder but no manifest, this fails rather than linking everything. marts/ is never written.
import { existsSync, readdirSync, readFileSync, symlinkSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url)); const marts = resolve(here, '../marts'); const pub = resolve(here, 'public/marts');
rmSync(pub, { recursive: true, force: true });
if (!existsSync(marts)) { console.error(`[link-desk] ${marts} not found.`); process.exit(1); }
let n = 0, files = 0;
for (const a of readdirSync(marts)) {
  const base = resolve(marts, a); const desk = resolve(base, 'desk'); if (!existsSync(desk)) continue;
  const mf = resolve(desk, 'manifest.json');
  if (!existsSync(mf)) { console.error(`[link-desk] marts/${a}/desk/ has no manifest.json. Rebuild it with: python sql/build_marts.py --agency ${a} --desk-only. Nothing was linked.`); process.exit(1); }
  const m = JSON.parse(readFileSync(mf, 'utf8'));
  const list = [...new Set(Object.values(m.card_types ?? {}).flatMap(t => [...(t.parquet ?? []), ...(t.published_csvs ?? [])]))];
  const link = (rel) => {
    const src = resolve(base, rel); if (!existsSync(src)) { console.error(`[link-desk] the manifest lists ${rel}, which does not exist.`); process.exit(1); }
    const dst = resolve(pub, a, rel); mkdirSync(dirname(dst), { recursive: true }); symlinkSync(src, dst); files++;
  };
  // the deployed manifest names published cards only (only published cards are listed; cards that are not published are dropped), same shape otherwise
  const ok = new Set(m.published_statuses ?? ['card', 'label']);
  const pub_m = { ...m, card_types: Object.fromEntries(Object.entries(m.card_types ?? {}).map(([k, t]) => [k, { ...t, cards: (t.cards ?? []).filter(c => ok.has(c.status)) }])) };
  mkdirSync(resolve(pub, a, 'desk'), { recursive: true }); writeFileSync(resolve(pub, a, 'desk/manifest.json'), JSON.stringify(pub_m, null, 2)); files++;
  list.forEach(link); n++;
}
console.log(`[link-desk] ${n} agency desk folder(s), ${files} published file(s) linked under public/marts/`);
