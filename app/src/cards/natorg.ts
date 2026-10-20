// National organizations card from marts/<agency>/desk/natorg_*.parquet (docs/data-contract.md section 10.4). All reader text is pre-rendered.
import { query } from '../db';
import type { Card, Column, Row } from './types';
import { fmt } from '../util';
import { D, by, arr, columnsOf, measureCols, seriesOf, seriesTable, verifiedSql } from './shared';

interface R { pct_change: number | null; card_id: string; status: string; fiscal_year: number; prior_year: number; period_label: string; measure: 'count' | 'dollars'; like_period: boolean; is_provisional: boolean; group_label: string; rest_label: string;
  headline: string; why_text: string; fixed_line: string; csv_path: string; method_ref: string; data_as_of: string; verified_on?: string | null; verified_in?: string | null }

export async function loadNatorg(agency: string): Promise<Card[]> {
  const t = await D(agency, 'natorg_cards'); if (!t) return [];
  const ver = verifiedSql(await columnsOf(t));
  const cards = await query<R>(`SELECT ${ver} pct_change, card_id, status, fiscal_year, prior_year, period_label, measure, like_period, is_provisional, group_label, rest_label, headline, why_text, fixed_line, csv_path, method_ref, strftime(data_as_of, '%Y-%m-%d') AS data_as_of
    FROM ${t} WHERE status IN ('card', 'label') ORDER BY card_id`);
  if (!cards.length) return [];
  const [tc, ts, tco, tp, to] = await Promise.all(['natorg_caveats', 'natorg_series', 'natorg_components', 'natorg_programs', 'natorg_organizations'].map(f => D(agency, f)));
  const ids = cards.map(c => c.card_id); const inList = `(${ids.map(() => '?').join(',')})`;
  const [cav, ser, comp, prog, org] = await Promise.all([
    query<{ card_id: string; text: string; caveat_key: string }>(`SELECT card_id, text, caveat_key FROM ${tc} WHERE card_id IN ${inList} ORDER BY card_id, sort`, ids),
    query<Record<string, unknown>>(`SELECT card_id, panel, entity, entity_label, year_role, period_label, value, index_value, is_provisional FROM ${ts} WHERE card_id IN ${inList} ORDER BY card_id, panel, entity, year`, ids),
    query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of) FROM ${tco} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids),
    query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of) FROM ${tp} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids),
    query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of) FROM ${to} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids)]);
  return cards.map(c => {
    const dollars = c.measure === 'dollars'; const vf = dollars ? 'money' : 'count';
    const fy = seriesOf(ser, c.card_id, 'fiscal_year'), cyc = seriesOf(ser, c.card_id, 'award_cycle');
    const mc = measureCols(dollars, c.prior_year, c.fiscal_year);
    const orgRows = by(org, c.card_id).map(r => ({ ...r, urls: arr((r as Record<string, unknown>).award_urls).join('|') })) as Row[];
    const caption = `${c.group_label} and ${c.rest_label.toLowerCase()}, ${c.period_label}`;
    return {
      id: c.card_id, type: 'national_organizations', placeholder: false, agency, status: { verified: c.verified_on ?? null, report: c.verified_in ?? null },
      key: c.pct_change != null ? { v: fmt(c.pct_change, 'pctpt'), l: c.like_period ? 'change, October\u2013July vs a year earlier' : 'change from the year before' } : undefined, spark: fy.filter(r => r.entity === 'state').map(r => r.index).filter((x): x is number => x != null),
      headline: c.headline, why: c.why_text, fixedLine: c.fixed_line, category: 'grants', period: c.period_label,
      chart: { kind: 'indexed', label: `New grants, ${c.group_label.toLowerCase()} and ${c.rest_label.toLowerCase()} (prior year = 100)`, alt: `Bars comparing ${c.group_label.toLowerCase()} with ${c.rest_label.toLowerCase()}, indexed so the prior year equals 100. ${c.headline}` },
      chartRows: [], seriesRows: fy,
      evidence: cyc.length ? { title: 'Award-cycle check', note: 'Evidence only: the same comparison by award cycle (the year an award was first made), used to check whether the change is timing. It does not decide whether a card appears.', rows: cyc, alt: `Award-cycle comparison of ${c.group_label.toLowerCase()} with ${c.rest_label.toLowerCase()}, indexed to the prior cycle = 100.`, table: seriesTable(cyc, 'Award-cycle comparison', c.group_label, c.rest_label, vf) } : undefined,
      table: seriesTable(fy, caption, c.group_label, c.rest_label, vf),
      drivers: [
        { title: 'Components behind the change', intro: 'Which DOJ components made the new grants to national organizations. Largest changes first. The rows add up to the group total.', caption: `Components, ${c.group_label}, ${c.period_label}`, columns: [{ key: 'component', label: 'Component' }, ...mc], rows: by(comp, c.card_id) as Row[] },
        { title: 'Grant programs behind the change', intro: 'Which grant programs (assistance listings) made the new grants. The rows add up to the group total.', caption: `Programs, ${c.group_label}, ${c.period_label}`, columns: [{ key: 'program_name', label: 'Program' }, { key: 'listing', label: 'Listing' }, ...mc], rows: by(prog, c.card_id) as Row[] },
        { title: 'The ten organizations with the largest change', intro: 'Each links to their largest awards on USAspending.gov.', caption: `Organizations, ${c.period_label}`, columns: [{ key: 'recipient_name', label: 'Organization' }, ...mc, { key: 'urls', label: 'Awards on USAspending', fmt: 'urls' } as Column], rows: orgRows },
      ],
      caveats: by(cav, c.card_id).map(x => ({ text: x.text, key: x.caveat_key })), csvPath: c.csv_path,
      how: { definition: 'The group is every new grant (metrics 7.7) to the national organizations: recipients that are mainly non-government and are either headquartered in Washington, DC, or pass DOJ money on to five or more states. "All other grant recipients" is every other new grant, except other recipients in Washington, DC, which are in neither group. A card appears when the two groups moved at least 1.5-fold apart.',
        fields: ['award_key', 'action_date', 'federal_action_obligation', 'recipient_uei', 'awarding_agency_code'], metrics: c.method_ref, query: `marts/${agency}/desk/natorg_*.parquet (docs/data-contract.md 10.4)`,
        steps: [`Add up new grants to the national organizations in ${c.prior_year} and ${c.fiscal_year}.`, 'Do the same for all other grant recipients.', 'Index each to its prior year (= 100) and compare how far apart they moved.', 'Show the components, programs and organizations that make up the change.'] },
      meta: { source: 'USAspending.gov prime award transactions, Department of Justice (agency 015)', dataAsOf: c.data_as_of, definition: 'Awarding agency 015; new grants by fiscal year of the new-award date; initial award amount, nominal dollars', period: c.period_label },
    } satisfies Card;
  });
}
