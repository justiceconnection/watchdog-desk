// Card 4 ("States that stand out") from marts/<agency>/desk/card4_*.parquet (docs/data-contract.md section 10.1).
// All reader text is pre-rendered in the marts; nothing is worded here except table headings and the "how calculated" summary.
import { query } from '../db';
import type { Card, Column, Row, SeriesRow } from './types';
import { D, columnsOf, verifiedSql } from './shared';
import { fmt } from '../util';

const arr = (x: unknown): string[] => (Array.isArray(x) ? (x as string[]) : []);
const N = (x: unknown) => (x == null ? null : Number(x));

interface CardRow {
  card_id: string; status: string; fiscal_year: number; prior_year: number; period_label: string; award_category: string; category_label: string; measure: 'count' | 'dollars';
  like_period: boolean; is_provisional: boolean; state: string; state_name: string; prior_value: number; current_value: number; change: number; pct_change: number | null;
  rest_prior: number; rest_current: number; rest_pct_change: number | null; z: number | null; headline: string; label_text: string | null; why_text: string; fixed_line: string;
  caveat_keys: string[]; csv_path: string; method_ref: string; data_as_of: string; verified_on?: string | null; verified_in?: string | null;
}

const MONEY = (m: Card['chart'] extends never ? never : 'count' | 'dollars') => (m === 'dollars' ? 'money' : 'count') as 'money' | 'count';

const HOW: Record<string, string> = {
  contract: 'A new award is the first time an award appears in the data (metrics 7.7). Only contract awards over $10,000 count. Each state’s total for the year is compared with the same total for the year before, and with the rest of the country (every other state, taken together). A state is shown when its change is far from the rest of the country’s, or the opposite direction.',
  assistance: 'A new award is the first time an award appears in the data (metrics 7.7). The state’s total for the year is compared with the year before and with the rest of the country (every other state, taken together). National organizations are left out of the comparison. A state is shown when its change is far from the rest of the country’s, or the opposite direction.',
};

export async function loadCard4(agency: string): Promise<Card[]> {
  const t = await D(agency, 'card4_cards'); if (!t) return [];
  const ver = verifiedSql(await columnsOf(t));   // verified_on / verified_in are joined in from the verification sign-offs by the desk build
  const cards = await query<CardRow>(`SELECT ${ver} card_id, status, fiscal_year, prior_year, period_label, award_category, category_label, measure, like_period, is_provisional, state, state_name,
    prior_value, current_value, change, pct_change, rest_prior, rest_current, rest_pct_change, z, headline, label_text, why_text, fixed_line, caveat_keys, csv_path, method_ref, strftime(data_as_of, '%Y-%m-%d') AS data_as_of
    FROM ${t} WHERE status IN ('card', 'label') ORDER BY CASE status WHEN 'card' THEN 0 ELSE 1 END, abs(z) DESC NULLS LAST, card_id`);
  if (!cards.length) return [];
  const [tc, ts, tco, tp, tr] = await Promise.all(['card4_caveats', 'card4_series', 'card4_components', 'card4_programs', 'card4_recipients'].map(f => D(agency, f)));
  const ids = cards.map(c => c.card_id); const inList = `(${ids.map(() => '?').join(',')})`;
  const [cav, ser, comp, prog, rec] = await Promise.all([
    query<{ card_id: string; text: string; caveat_key: string }>(`SELECT card_id, text, caveat_key FROM ${tc} WHERE card_id IN ${inList} ORDER BY card_id, sort`, ids),
    query<Record<string, unknown>>(`SELECT card_id, panel, panel_label, entity, entity_label, year_role, period_label, value, index_value, is_provisional FROM ${ts} WHERE card_id IN ${inList} ORDER BY card_id, panel, entity DESC, year`, ids),
    query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of) FROM ${tco} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids),
    tp ? query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of) FROM ${tp} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids) : Promise.resolve([]),
    query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of) FROM ${tr} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids),
  ]);
  const by = <T extends object>(rows: T[], id: string) => rows.filter(r => (r as { card_id?: unknown }).card_id === id);

  return cards.map(c => {
    const dollars = c.measure === 'dollars'; const vf = dollars ? 'money' : 'count';
    const mkSeries = (panel: string): SeriesRow[] => by(ser, c.card_id).filter(r => r.panel === panel).map(r => ({
      entity: r.entity as 'state' | 'rest', entityLabel: String(r.entity_label), role: r.year_role as 'prior' | 'current', periodLabel: String(r.period_label), value: Number(r.value), index: N(r.index_value), provisional: !!r.is_provisional }));
    const fy = mkSeries('fiscal_year'), cyc = mkSeries('award_cycle');
    const seriesTable = (rows: SeriesRow[], caption: string) => {
      const periods = [...new Map(rows.map(r => [r.role, r.periodLabel])).entries()].sort(a => (a[0] === 'prior' ? -1 : 1));
      return { caption, columns: [{ key: 'period', label: 'Period' }, { key: 'sv', label: `${c.state_name}`, fmt: vf, align: 'right' }, { key: 'si', label: `${c.state_name}, index`, fmt: 'index', align: 'right' },
        { key: 'rv', label: 'Rest of the country', fmt: vf, align: 'right' }, { key: 'ri', label: 'Rest of the country, index', fmt: 'index', align: 'right' }] as Column[],
        rows: periods.map(([role, label]) => { const s = rows.find(r => r.role === role && r.entity === 'state'), r = rows.find(r => r.role === role && r.entity === 'rest');
          return { period: label, sv: s?.value ?? null, si: s?.index ?? null, rv: r?.value ?? null, ri: r?.index ?? null } as Row; }) };
    };
    const cn = (k: string, label: string, f: 'count' | 'money'): Column[] => [{ key: `prior_${k}`, label: `${label}, ${c.prior_year}`, fmt: f, align: 'right' }, { key: `current_${k}`, label: `${label}, ${c.fiscal_year}`, fmt: f, align: 'right' }, { key: `${k}_change`, label: `${label} change`, fmt: f === 'money' ? 'smoney' : 'schange', align: 'right' }];
    const measureCols = (): Column[] => (dollars ? [...cn('dollars', 'Dollars', 'money'), ...cn('count', 'Awards', 'count')] : [...cn('count', 'Awards', 'count'), ...cn('dollars', 'Dollars', 'money')]);
    const compRows = by(comp, c.card_id) as Row[], progRows = by(prog, c.card_id) as Row[];
    const recRows = by(rec, c.card_id).map(r => ({ ...r, urls: arr(r.award_urls).join('|') })) as Row[];
    const noun = c.award_category === 'contract' ? 'contracts' : 'grants';
    const period = c.period_label;
    const caveats = by(cav, c.card_id).map(x => ({ text: x.text, key: x.caveat_key }));
    const drivers: NonNullable<Card['drivers']> = [
      { title: 'Components behind the change', intro: `Which DOJ components made the new ${noun} in ${c.state_name}. Largest changes first. Awards are new awards in the period; the rows add up to the state total.`, caption: `Components, ${c.state_name}, ${period}`, columns: [{ key: 'component', label: 'Component' }, ...measureCols()], rows: compRows },
      ...(progRows.length ? [{ title: 'Grant programs behind the change', intro: `Which grant programs (assistance listings) made the new grants. The rows add up to the state total.`, caption: `Programs, ${c.state_name}, ${period}`, columns: [{ key: 'program_name', label: 'Program' }, { key: 'listing', label: 'Listing' }, ...measureCols()], rows: progRows }] : []),
      { title: 'Largest recipients behind the change', intro: 'Up to five recipients with the largest change. Each links to their largest awards on USAspending.gov.', caption: `Recipients, ${c.state_name}, ${period}`, columns: [{ key: 'recipient_name', label: 'Recipient' }, ...measureCols(), { key: 'urls', label: 'Awards on USAspending', fmt: 'urls' }], rows: recRows },
    ];
    const card: Card = {
      id: c.card_id, type: 'state_stand_out', placeholder: false, agency, status: { verified: c.verified_on ?? null, report: c.verified_in ?? null },
      key: c.pct_change != null ? { v: fmt(c.pct_change, 'pctpt'), l: c.like_period ? 'change, October\u2013July vs a year earlier' : 'change from the year before' } : undefined, spark: fy.filter(r => r.entity === 'state').map(r => r.index).filter((x): x is number => x != null),
      headline: c.headline, why: c.why_text, labelText: c.label_text, fixedLine: c.fixed_line, category: c.category_label, period,
      chart: { kind: 'indexed', label: `New ${noun}, ${c.state_name} and the rest of the country (prior year = 100)`, alt: `Bars comparing ${c.state_name} with the rest of the country, indexed so the prior year equals 100. ${c.headline}` },
      chartRows: [], seriesRows: fy,
      evidence: cyc.length ? { title: 'Award-cycle check', note: 'Evidence only: the same comparison by award cycle (the year an award was first made), shown to check whether the change is timing. It does not decide whether a card appears.', rows: cyc, alt: `Award-cycle comparison of ${c.state_name} with the rest of the country, indexed to the prior cycle = 100.`, table: seriesTable(cyc, 'Award-cycle comparison') } : undefined,
      table: seriesTable(fy, `${c.state_name} and the rest of the country, ${period}`),
      drivers, caveats, csvPath: c.csv_path,
      how: { definition: HOW[c.award_category] ?? HOW.contract, fields: ['award_key', 'action_date', 'federal_action_obligation', 'recipient_state_code', 'awarding_agency_code'], metrics: c.method_ref, query: `marts/${agency}/desk/card4_*.parquet (docs/data-contract.md 10.1)`, steps: [
        `Take every new ${noun.replace(/s$/, '')} award to recipients in each state, for ${c.prior_year} and ${c.fiscal_year === c.prior_year ? '' : c.fiscal_year}${c.like_period ? ' (October through the data cut-off in both years)' : ''}.`,
        `Add them up as ${dollars ? 'dollars (the initial award amount)' : 'a count of awards'}.`,
        `Compare ${c.state_name}’s change with the rest of the country’s, and with how far other states usually move.`,
        'Show the components, programs and recipients that make up the change.'] },
      meta: { source: 'USAspending.gov prime award transactions, Department of Justice (agency 015)', dataAsOf: c.data_as_of, definition: `Awarding agency 015; state = recipient state of the new-award transaction; fiscal year of the new-award date; ${dollars ? 'initial award amount, nominal dollars' : 'count of new awards'}`, period },
    };
    void MONEY; return card;
  });
}

export interface Methods { params: { parameter: string; value: string }[]; text: { key: string; template: string }[]; orgs: { uei: string; name: string; basis: string }[] }
export async function loadMethods(agency: string): Promise<Methods | null> {
  const [tp, tt, to] = await Promise.all(['card4_params', 'card4_text', 'card4_national_orgs'].map(f => D(agency, f))); if (!tp || !tt || !to) return null;
  const [params, text, orgs] = await Promise.all([
    query<{ parameter: string; value: string }>(`SELECT parameter, value FROM ${tp} ORDER BY parameter`),
    query<{ key: string; template: string }>(`SELECT key, template FROM ${tt} ORDER BY key`),
    query<{ uei: string; name: string; basis: string }>(`SELECT recipient_uei AS uei, recipient_name AS name, rule_basis AS basis FROM ${to} ORDER BY recipient_name`)]);
  return { params, text, orgs };
}
