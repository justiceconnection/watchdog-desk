// Card 3, grants by Justice Connection category, from marts/<agency>/desk/card3_*.parquet (docs/data-contract.md section 10.8).
// One card per published (fiscal year, category). Headline, second line, label, fixed line and caveats are pre-rendered in the marts.
import { query } from '../db';
import type { Card, Column, Row } from './types';
import { D, by, columnsOf, verifiedSql } from './shared';
import { fmt } from '../util';

interface R { card_id: string; status: string; fiscal_year: number; prior_year: number; basis: 'fy' | 'like'; like_period: boolean; is_provisional: boolean; period_label: string; category: string; headline_scope: string;
  amount_prior: number; amount_current: number; share_current: number; headline: string; second_line: string; label_text: string | null; fixed_line: string; csv_path: string; method_ref: string; data_as_of: string; verified_on?: string | null; verified_in?: string | null }

const SCOPE: Record<string, string> = { doj: 'all DOJ new grant dollars', ojp: 'Office of Justice Programs new grant dollars', ojpx: 'Office of Justice Programs new grant dollars, excluding VOCA formula grants (16.575, 16.576)' };
// caveat order on the card (fixed editorial order): denominator, Crime Victims Fund cap, earmarks, COVID, OJP gap, FY2026 gap, then the tribal-first note
const CAVEAT_ORDER = ['denominator', 'cvf_cap', 'earmarks', 'covid', 'ojp_gap', 'gap_year', 'tribal_first'];
const SCAAP_SEG = 'SCAAP (jail reimbursement, above 100%)';
const COLORS = ['#c2410c', '#8a96a3', '#7a3e9d'];   // this category, everything else, SCAAP
const moneyShort = (n: number) => (n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : `$${(n / 1e6).toFixed(0)}M`);

export async function loadCard3(agency: string): Promise<Card[]> {
  const t = await D(agency, 'card3_cards'); if (!t) return [];
  const ver = verifiedSql(await columnsOf(t));
  const cards = await query<R>(`SELECT ${ver} card_id, status, fiscal_year, prior_year, basis, like_period, is_provisional, period_label, category, headline_scope, amount_prior, amount_current, share_current, headline, second_line, label_text, fixed_line, csv_path, method_ref,
    strftime(data_as_of, '%Y-%m-%d') AS data_as_of FROM ${t} WHERE status IN ('card', 'label') ORDER BY fiscal_year DESC, abs(change) DESC, card_id`);
  if (!cards.length) return [];
  const [tc, tm, tl, tx] = await Promise.all(['card3_caveats', 'card3_mix', 'card3_listings', 'card3_text'].map(f => D(agency, f)));
  const ids = cards.map(c => c.card_id); const inList = `(${ids.map(() => '?').join(',')})`;
  const scopes = [...new Set(cards.map(c => c.headline_scope))];
  const [cav, mix, lst, txt] = await Promise.all([
    query<{ card_id: string; text: string; caveat_key: string }>(`SELECT card_id, text, caveat_key FROM ${tc} WHERE card_id IN ${inList} ORDER BY card_id, sort`, ids),
    query<Record<string, unknown>>(`SELECT scope, basis, year, segment, is_scaap_segment, amount, display_share, trigger_share, scope_total, scope_total_excl_scaap, is_hatched FROM ${tm} WHERE scope IN (${scopes.map(() => '?').join(',')}) ORDER BY scope, basis, year`, scopes),
    query<Record<string, unknown>>(`SELECT * EXCLUDE (agency_code, data_as_of, scope) FROM ${tl} WHERE card_id IN ${inList} ORDER BY card_id, rank`, ids),
    query<{ key: string; template: string }>(`SELECT key, template FROM ${tx} WHERE key LIKE 'note%'`)]);
  const note = (k: string) => txt.find(x => x.key === k)?.template ?? '';
  const latestFy = Math.max(...cards.map(c => c.fiscal_year));

  return cards.map(c => {
    const rowsOf = (basis: string, years?: number[]) => mix.filter(m => m.scope === c.headline_scope && m.basis === basis && (!years || years.includes(Number(m.year))));
    // chart rows: this category, SCAAP (its own segment) and everything else, per year; shares of the scope's new grant dollars
    const shape = (basis: string, years?: number[]) => {
      const m = rowsOf(basis, years); const ys = [...new Set(m.map(x => Number(x.year)))].sort((a, b) => a - b);
      const out: Row[] = []; const table: Row[] = [];
      for (const y of ys) {
        const yr = m.filter(x => Number(x.year) === y); const cat = yr.find(x => x.segment === c.category); const sc = yr.find(x => x.is_scaap_segment);
        // chart and table use the same numbers: shares of the scope's total without SCAAP. SCAAP is drawn above the bar as its own dotted segment, labelled in dollars.
        const cs = Number(cat?.trigger_share ?? 0); const tot = Number(yr[0]?.scope_total_excl_scaap ?? 0); const sAmt = Number(sc?.amount ?? 0); const ss = tot > 0 ? sAmt / tot : 0; const hatched = yr.some(x => x.is_hatched) ? 1 : 0;
        out.push({ y, seg: c.category, share: cs, prov: hatched, hatch: 0 }, { y, seg: 'All other categories', share: Math.max(0, 1 - cs), prov: hatched, hatch: 0 },
          { y, seg: SCAAP_SEG, share: ss, prov: 0, hatch: 1, top: 1 + ss, label: sAmt > 0 ? `SCAAP ${moneyShort(sAmt)}` : null });
        table.push({ year: `${y}${hatched ? ' (so far)' : ''}`, amt: Number(cat?.amount ?? 0), cs, tot });
      }
      return { out, table, hasScaap: out.some(r => r.seg === SCAAP_SEG && Number(r.share) > 0), ys };
    };
    const spec = (label: string, alt: string) => ({ kind: 'stack' as const, x: 'y', y: 'share', series: 'seg', yFmt: 'pct' as const, label, provisionalKey: 'prov', hatchKey: 'hatch', domain: [c.category, 'All other categories', SCAAP_SEG], colors: COLORS, labelKey: 'label', alt });
    const cols = (what: string): Column[] => [{ key: 'year', label: 'Year' }, { key: 'amt', label: `${what}, new grants`, fmt: 'money', align: 'right' }, { key: 'cs', label: `Share of ${SCOPE[c.headline_scope]} (SCAAP left out)`, fmt: 'pct', align: 'right' }, { key: 'tot', label: 'All new grant dollars in this scope (SCAAP left out)', fmt: 'money', align: 'right' }];
    const fy = shape('fy'); const like = shape('like'); const cyc = shape('cycle_le');
    const gap = c.basis === 'like';
    const notes = [fy.hasScaap ? `${note('note_scaap_shares')}` : '', fy.ys[0] === 2017 ? `FY2017: ${note('note_fy2017')}.` : ''].filter(Boolean).join(' ');
    const extra: NonNullable<Card['extraCharts']> = [];
    if (gap) extra.push({ title: `Same months, October to July: FY${c.prior_year} and FY${c.fiscal_year}`, note: `${note('note_gap_year')[0].toUpperCase()}${note('note_gap_year').slice(1)}. The hatched year is provisional. This is the comparison the card is based on.`, chart: spec(`Share of ${SCOPE[c.headline_scope]}, October to July`, `Stacked bars of ${c.category}'s share of ${SCOPE[c.headline_scope]} for October to July of FY${c.prior_year} and FY${c.fiscal_year}; FY${c.fiscal_year} is provisional and hatched.`), rows: like.out, table: { caption: `Same months (October to July), ${c.category}`, columns: cols(c.category), rows: like.table } });
    extra.push({ title: 'Award-cycle check', note: `Evidence only: the same shares counted by award cycle (the year an award was first made), each cycle through the same point of its life. It does not decide whether a card appears.`, chart: spec(`Share of ${SCOPE[c.headline_scope]}, by award cycle`, `Stacked bars of ${c.category}'s share by award cycle.`), rows: cyc.out, table: { caption: `Award-cycle shares, ${c.category}`, columns: cols(c.category), rows: cyc.table } });
    const lrows = by(lst, c.card_id).map(r => { const x = r as Record<string, unknown>; return { ...x, _hl: x.is_top_driver ? 1 : 0 } as Row; });
    const top = lrows.filter(r => r._hl === 1).length;
    return {
      id: c.card_id, type: 'grant_categories', placeholder: false, agency, status: { verified: c.verified_on ?? null, report: c.verified_in ?? null }, earlier: c.fiscal_year < latestFy - 1,
      key: { v: fmt(c.share_current, 'pct'), l: `of ${c.headline.match(/% of (.+?) new grant dollars/)?.[1] ?? 'DOJ\u2019s'} new grant dollars` }, spark: fy.out.filter(r => r.seg === c.category && Number(r.y) <= c.fiscal_year).map(r => Number(r.share)), sparkHighlight: fy.ys.includes(c.fiscal_year),
      headline: c.headline, why: c.second_line, whyLabel: '', labelText: c.label_text, fixedLine: c.fixed_line, category: 'grants', categoryName: c.category, period: c.period_label,
      chart: spec(`Share of ${SCOPE[c.headline_scope]}, by fiscal year`, `Stacked bars of ${c.category}'s share of ${SCOPE[c.headline_scope]} by fiscal year, with SCAAP as its own segment and all other categories together.`), chartRows: fy.out,
      chartNote: notes || undefined, chartTitle: gap ? 'By fiscal year (complete years)' : 'By fiscal year', extraCharts: extra,
      table: { caption: `${c.category}: share of ${SCOPE[c.headline_scope]}, by fiscal year`, columns: cols(c.category), rows: fy.table },
      drivers: [{ title: 'The programs behind the change', intro: `Grant programs (assistance listings) in this category, largest change first${top ? `; the ${top} biggest drivers are highlighted` : ''}. Amounts are new awards in ${c.period_label}${gap ? ' and the same months a year earlier' : ` and ${c.prior_year}`}.`, caption: `Programs in ${c.category}, ${c.period_label}`,
        columns: [{ key: 'program_name', label: 'Program' }, { key: 'listing', label: 'Listing' }, { key: 'subcategory', label: 'Kind of program' }, { key: 'prior_amount', label: `Dollars, ${c.prior_year}`, fmt: 'money', align: 'right' }, { key: 'current_amount', label: `Dollars, ${c.fiscal_year}`, fmt: 'money', align: 'right' }, { key: 'change', label: 'Dollars change', fmt: 'smoney', align: 'right' },
          { key: 'prior_count', label: `Awards, ${c.prior_year}`, fmt: 'count', align: 'right' }, { key: 'current_count', label: `Awards, ${c.fiscal_year}`, fmt: 'count', align: 'right' }, { key: 'current_share_of_scope', label: 'Share of scope now', fmt: 'pct', align: 'right' }], rows: lrows }],
      caveats: by(cav, c.card_id).sort((x, y) => CAVEAT_ORDER.indexOf(x.caveat_key) - CAVEAT_ORDER.indexOf(y.caveat_key)).map(x => ({ text: x.text, key: x.caveat_key })), csvPath: c.csv_path,
      how: { definition: `Every new grant (metrics 7.7) is assigned to one of twelve Justice Connection categories by the program it belongs to. The card compares this category’s share of ${SCOPE[c.headline_scope]} with the year before. A card appears when the share moved by at least 5 points and the dollar change is large, and the award-cycle check agrees.`,
        fields: ['award_key', 'assistance_listing_number', 'federal_action_obligation', 'action_date', 'awarding_agency_code'], metrics: c.method_ref, query: `marts/${agency}/desk/card3_*.parquet (docs/data-contract.md 10.8); category scheme: docs/specs/grant-categories.csv`,
        steps: ['Assign each new grant to a category through its assistance listing.', `Add up the dollars by category for ${c.prior_year} and ${c.fiscal_year}${gap ? ' (October through the data cut-off in both years)' : ''}.`, 'Compare each category’s share of the total, and check it against the award-cycle shares.', 'List the programs that make up the change.'] },
      meta: { source: 'USAspending.gov prime award transactions, Department of Justice (agency 015)', dataAsOf: c.data_as_of, definition: `Awarding agency 015; new grants by fiscal year of the new-award date; initial award amount, nominal dollars; scope: ${SCOPE[c.headline_scope]}`, period: c.period_label },
    } satisfies Card;
  });
}
