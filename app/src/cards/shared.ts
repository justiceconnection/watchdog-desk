// Helpers shared by the real cards: the desk marts' common shapes (series, driver tables, caveats). Text is never composed here.
import { query, tryMart } from '../db';
import type { Column, Row, SeriesRow } from './types';

export const arr = (x: unknown): string[] => (Array.isArray(x) ? (x as string[]) : []);
export const N = (x: unknown) => (x == null ? null : Number(x));
// The deployed file names come from marts/<agency>/desk/manifest.json (the build may publish them under a subfolder); nothing is hard-coded.
const manifests = new Map<string, Promise<string[]>>();
function listed(a: string): Promise<string[]> {
  let p = manifests.get(a);
  if (!p) {
    p = fetch(`${import.meta.env.BASE_URL}marts/${a}/desk/manifest.json`).then(r => { if (!r.ok) throw new Error(`The desk manifest for agency ${a} could not be loaded (${r.status}).`); return r.json(); })
      .then(m => Object.values((m.card_types ?? {}) as Record<string, { parquet?: string[] }>).flatMap(t => t.parquet ?? []));
    manifests.set(a, p);
  }
  return p;
}
export async function D(a: string, f: string): Promise<string | null> {
  const rel = (await listed(a)).find(x => x.endsWith(`/${f}.parquet`) || x === `${f}.parquet`);
  return rel ? tryMart(`${a}/${rel}`) : null;
}
export const by = <T extends object>(rows: T[], id: string) => rows.filter(r => (r as { card_id?: unknown }).card_id === id);

/** Does the table have this column? (verified_on / verified_in arrive when the verifier's sign-offs are joined in) */
export async function columnsOf(t: string): Promise<Set<string>> {
  return new Set((await query<{ column_name: string }>(`SELECT column_name FROM (DESCRIBE SELECT * FROM ${t})`)).map(r => r.column_name));
}
export const verifiedSql = (have: Set<string>) => (have.has('verified_on') ? `strftime(verified_on, '%Y-%m-%d') AS verified_on, ${have.has('verified_in') ? 'verified_in' : 'NULL AS verified_in'},` : '');

/** Series rows of one panel. `group` entities are drawn like `state` (the highlighted side). */
export function seriesOf(rows: Record<string, unknown>[], cardId: string, panel: string): SeriesRow[] {
  return by(rows, cardId).filter(r => (r as Record<string, unknown>).panel === panel).map(x => { const r = x as Record<string, unknown>; return {
    entity: (r.entity === 'rest' ? 'rest' : 'state') as 'state' | 'rest', entityLabel: String(r.entity_label), role: r.year_role as 'prior' | 'current', periodLabel: String(r.period_label), value: Number(r.value), index: N(r.index_value), provisional: !!r.is_provisional }; });
}
export function seriesTable(rows: SeriesRow[], caption: string, a: string, b: string, vf: 'money' | 'count') {
  const periods = [...new Map(rows.map(r => [r.role, r.periodLabel])).entries()].sort(x => (x[0] === 'prior' ? -1 : 1));
  return { caption, columns: [{ key: 'period', label: 'Period' }, { key: 'sv', label: a, fmt: vf, align: 'right' }, { key: 'si', label: `${a}, index`, fmt: 'index', align: 'right' },
    { key: 'rv', label: b, fmt: vf, align: 'right' }, { key: 'ri', label: `${b}, index`, fmt: 'index', align: 'right' }] as Column[],
    rows: periods.map(([role, label]) => { const s = rows.find(r => r.role === role && r.entity === 'state'), r = rows.find(r => r.role === role && r.entity === 'rest');
      return { period: label, sv: s?.value ?? null, si: s?.index ?? null, rv: r?.value ?? null, ri: r?.index ?? null } as Row; }) };
}
/** Count and dollar columns of the driver tables (prior year, current year, signed change); the card's own measure first. */
export function measureCols(dollars: boolean, prior: number, current: number): Column[] {
  const cn = (k: string, label: string, f: 'count' | 'money'): Column[] => [{ key: `prior_${k}`, label: `${label}, ${prior}`, fmt: f, align: 'right' }, { key: `current_${k}`, label: `${label}, ${current}`, fmt: f, align: 'right' }, { key: `${k}_change`, label: `${label} change`, fmt: f === 'money' ? 'smoney' : 'schange', align: 'right' }];
  return dollars ? [...cn('dollars', 'Dollars', 'money'), ...cn('count', 'Awards', 'count')] : [...cn('count', 'Awards', 'count'), ...cn('dollars', 'Dollars', 'money')];
}
