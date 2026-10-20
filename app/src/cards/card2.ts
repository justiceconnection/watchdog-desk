// Card 2, contracts awarded without competition, from marts/<agency>/desk/card2_*.parquet (docs/data-contract.md section 10.5).
// One card for the whole period: the chart shows every year; the reasons, recipient types and top awards follow a year selector.
import { query } from '../db';
import type { Card, DriverTable, Row, YearView } from './types';
import { D, columnsOf, verifiedSql } from './shared';
import { fmt } from '../util';

interface S { fiscal_year: number; period_label: string; is_provisional: boolean; n_universe: number; n_not_competed: number; n_not_reported: number; dollars_universe: number; dollars_not_competed: number;
  share_count: number; share_dollars: number; dollars_utilities: number; n_utilities: number; share_count_utilities: number; share_dollars_utilities: number; dollars_not_competed_excl_utilities: number;
  top_award_share: number | null; fixed_line: string | null; why_text: string | null; show_top_awards: boolean; headline: string; concentration_line: string | null; provisional_note: string | null; csv_path: string; card_id: string; data_as_of: string; verified_on?: string | null; verified_in?: string | null }

const pc = (x: number) => `${(x * 100).toFixed(0)}%`;


export async function loadCard2(agency: string): Promise<Card[]> {
  const t = await D(agency, 'card2_summary'); if (!t) return [];
  const ver = verifiedSql(await columnsOf(t));
  const have = await columnsOf(t);
  if (!have.has('why_text')) throw new Error('card2_summary has no why_text column: the desk data needs to be rebuilt.');
  const sum = await query<S>(`SELECT ${ver} why_text, fixed_line, card_id, fiscal_year, period_label, is_provisional, n_universe, n_not_competed, n_not_reported, dollars_universe, dollars_not_competed, share_count, share_dollars, dollars_utilities, n_utilities,
    share_count_utilities, share_dollars_utilities, dollars_not_competed_excl_utilities, top_award_share, show_top_awards, headline, concentration_line, provisional_note, csv_path, strftime(data_as_of, '%Y-%m-%d') AS data_as_of FROM ${t} WHERE status = 'card' ORDER BY fiscal_year`);
  if (!sum.length) return [];
  const [tr, tt, ta, tx] = await Promise.all(['card2_reasons', 'card2_recipient_types', 'card2_top_awards', 'card2_text'].map(f => D(agency, f)));
  if (!(await columnsOf(tt!)).has('category_label')) throw new Error('card2_recipient_types has no category_label column: the desk data needs to be rebuilt.');
  const [reasons, types, tops, text] = await Promise.all([
    query<Record<string, unknown>>(`SELECT fiscal_year, reason_label, band, sort, n_awards, dollars, share_count_of_universe, share_dollars_of_universe FROM ${tr} ORDER BY fiscal_year, sort`),
    query<Record<string, unknown>>(`SELECT fiscal_year, dimension, category, category_label, is_additive, n_awards, dollars FROM ${tt} ORDER BY fiscal_year, dimension, dollars DESC`),
    query<Record<string, unknown>>(`SELECT fiscal_year, rank, recipient_name, amount, share_of_not_competed_dollars, reason_label, sub_agency, psc_description, strftime(action_date, '%Y-%m-%d') AS action_date, usaspending_url FROM ${ta} ORDER BY fiscal_year, rank`),
    query<{ key: string; text: string }>(`SELECT key, text FROM ${tx}`)]);
  const txt = (k: string) => text.find(x => x.key === k)?.text ?? '';
  const latest = sum[sum.length - 1];

  // chart rows: share of the year's new contracts above the small-purchase threshold, with utilities as a separate band
  const mk = (kind: 'dollars' | 'count') => sum.flatMap(s => {
    const ut = kind === 'dollars' ? s.share_dollars_utilities : s.share_count_utilities, all = kind === 'dollars' ? s.share_dollars : s.share_count;
    return [{ fy: s.fiscal_year, band: 'Not competed, excluding utilities', share: all - ut, provisional: s.is_provisional ? 1 : 0 }, { fy: s.fiscal_year, band: 'Utilities (not competed)', share: ut, provisional: s.is_provisional ? 1 : 0 }];
  }) as Row[];
  const spec = (kind: 'dollars' | 'count') => ({ kind: 'stack' as const, x: 'fy', y: 'share', series: 'band', yFmt: 'pct' as const, provisionalKey: 'provisional', domain: ['Not competed, excluding utilities', 'Utilities (not competed)'],
    label: kind === 'dollars' ? 'Share of new contract dollars awarded without competition' : 'Share of new contracts awarded without competition',
    alt: `Stacked bars of the share of new DOJ contract ${kind === 'dollars' ? 'dollars' : 'contracts'} above the small-purchase threshold that were awarded without competition, by fiscal year, FY${sum[0].fiscal_year} to FY${latest.fiscal_year}, with utilities as a separate band. The last year is provisional and hatched.` });

  const yv: YearView[] = sum.map(s => {
    const fyr = (r: Record<string, unknown>) => r.fiscal_year === s.fiscal_year;
    const drivers: DriverTable[] = [];
    drivers.push({ title: 'The reasons given', intro: 'The reason the contracting office recorded for not competing each award. These codes are as reported and can be wrong; they do not show intent. Utilities are shown as a separate band.', caption: `Reasons given, ${s.period_label}`,
      columns: [{ key: 'reason', label: 'Reason' }, { key: 'band', label: 'Band' }, { key: 'n', label: 'Contracts', fmt: 'count', align: 'right' }, { key: 'sc', label: 'Share of all new contracts', fmt: 'pct', align: 'right' }, { key: 'd', label: 'Dollars', fmt: 'money', align: 'right' }, { key: 'sd', label: 'Share of all new dollars', fmt: 'pct', align: 'right' }],
      rows: reasons.filter(fyr).map(r => ({ reason: r.reason_label as string, band: r.band === 'utilities' ? 'Utilities' : 'Other', n: Number(r.n_awards), sc: Number(r.share_count_of_universe), d: Number(r.dollars), sd: Number(r.share_dollars_of_universe) })) });
    const dim = (d: string) => types.filter(r => fyr(r) && r.dimension === d).map(r => ({ category: (r.category_label as string | null) ?? (r.category as string), code: r.category as string, n: Number(r.n_awards), d: Number(r.dollars) })) as Row[];
    const cols = (first: string) => [{ key: 'category', label: first, tipKey: 'code' }, { key: 'n', label: 'Contracts', fmt: 'count' as const, align: 'right' as const }, { key: 'd', label: 'Dollars', fmt: 'money' as const, align: 'right' as const }];
    const size = dim('size'), org = dim('organization_type'), aside = dim('set_aside'), flags = dim('flag');
    if (size.length) drivers.push({ title: 'Who receives them: business size', intro: 'Not-competed contracts by the size the recipient reported. The two rows add up to the year’s not-competed contracts.', caption: `Business size, ${s.period_label}`, columns: cols('Business size'), rows: size });
    if (org.length) drivers.push({ title: 'Who receives them: organization type', intro: 'Organization type is reported reliably only from FY2019, so earlier years are not shown.', caption: `Organization type, ${s.period_label}`, columns: cols('Organization type'), rows: org });
    if (aside.length) drivers.push({ title: 'Who receives them: set-aside program', intro: 'The set-aside code recorded on the contract. Each contract has one code, so these rows add up to the year’s not-competed contracts.', caption: `Set-aside, ${s.period_label}`, columns: cols('Set-aside'), rows: aside });
    if (flags.length) drivers.push({ title: 'Who receives them: business flags (overlapping)', intro: txt('flags_note') + ' Do not add these rows.', caption: `Business flags, ${s.period_label} (overlapping, not additive)`, columns: cols('Business flag'), rows: flags, note: 'Overlapping: a contract can carry several flags, so these rows are never summed.' });
    if (s.show_top_awards) drivers.push({ title: 'The largest not-competed awards', intro: `Shown because the largest award is ${pc(s.top_award_share ?? 0)} or more of the year’s not-competed dollars. Each links to USAspending.gov.`, caption: `Largest not-competed awards, ${s.period_label}`,
      columns: [{ key: 'recipient', label: 'Recipient' }, { key: 'amount', label: 'Amount', fmt: 'money', align: 'right' }, { key: 'share', label: 'Share of not-competed dollars', fmt: 'pct', align: 'right' }, { key: 'reason', label: 'Reason' }, { key: 'what', label: 'What it buys, and the office' }, { key: 'date', label: 'Date' }, { key: 'url', label: 'Award', fmt: 'urls' }],
      rows: tops.filter(fyr).map(r => ({ recipient: r.recipient_name as string, amount: Number(r.amount), share: Number(r.share_of_not_competed_dollars), reason: r.reason_label as string, what: `${String(r.psc_description ?? '').toLowerCase().replace(/^./, c => c.toUpperCase())}. ${r.sub_agency}`, date: r.action_date as string, url: r.usaspending_url as string })) });
    const notes = [...(s.provisional_note ? [s.provisional_note] : []), txt('statutory_note'), txt('flags_note'), txt('org_type_note')].filter(Boolean);
    return { key: String(s.fiscal_year), label: s.period_label, headline: s.headline, why: s.why_text ?? '', labelText: s.show_top_awards ? s.concentration_line : null, notes, drivers };
  }).reverse();

  const tableRows: Row[] = [...sum].reverse().map(s => ({ fy: s.period_label, nu: s.n_universe, nn: s.n_not_competed, sc: s.share_count, du: s.dollars_universe, dn: s.dollars_not_competed, sd: s.share_dollars, ut: s.share_dollars_utilities }));
  const view0 = yv[0];
  return [{
    id: latest.card_id, aliases: sum.map(s => s.card_id), type: 'contracts_without_competition', placeholder: false, agency, status: { verified: latest.verified_on ?? null, report: latest.verified_in ?? null },
    key: { v: fmt(latest.share_dollars, 'pct'), l: 'of new contract dollars' }, spark: sum.map(s => s.share_dollars),
    headline: latest.headline, why: latest.why_text ?? '', fixedLine: latest.fixed_line, labelText: view0.labelText, category: 'contracts', period: `FY${sum[0].fiscal_year} to ${latest.period_label}`,
    chart: spec('dollars'), chartRows: mk('dollars'), extraCharts: [{ title: 'By number of contracts', chart: spec('count'), rows: mk('count') }],
    table: { caption: 'Contracts above the small-purchase threshold and the share awarded without competition, by fiscal year', columns: [
      { key: 'fy', label: 'Fiscal year' }, { key: 'nu', label: 'New contracts', fmt: 'count', align: 'right' }, { key: 'nn', label: 'Not competed', fmt: 'count', align: 'right' }, { key: 'sc', label: 'Share of contracts', fmt: 'pct', align: 'right' },
      { key: 'du', label: 'New contract dollars', fmt: 'money', align: 'right' }, { key: 'dn', label: 'Not competed dollars', fmt: 'money', align: 'right' }, { key: 'sd', label: 'Share of dollars', fmt: 'pct', align: 'right' }, { key: 'ut', label: 'Of which utilities (share of dollars)', fmt: 'pct', align: 'right' }], rows: tableRows },
    yearViews: yv, drivers: [], caveats: view0.notes.map(text => ({ text })), csvPath: latest.csv_path,
    how: { definition: txt('explainer'), fields: ['extent_competed_code', 'solicitation_procedures_code', 'number_of_offers', 'federal_action_obligation', 'modification_number', 'base_and_all_options_value'], metrics: 'docs/specs/watchdog-cards.md Card 2; docs/metrics.md 7.7', query: `marts/${agency}/desk/card2_*.parquet (docs/data-contract.md 10.5)`,
      steps: ['Take each new contract (the first record of the award).', 'Leave out small purchases: simplified-acquisition codes, or an anticipated value of $250,000 or less.', 'Count the award as not competed when the competition code says so, and as competed otherwise; contracts with no code are left out of the share.', 'Add up the contracts and the dollars of each class by fiscal year, with utilities as a separate band.'] },
    meta: { source: 'USAspending.gov prime award transactions, Department of Justice (agency 015)', dataAsOf: latest.data_as_of, definition: 'Awarding agency 015; new contract awards above the small-purchase threshold; dollars = initial award obligations; nominal', period: `FY${sum[0].fiscal_year} to ${latest.period_label}` },
  }];
}
