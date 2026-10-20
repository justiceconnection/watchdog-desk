// The shape of one card (docs/specs/watchdog-desk.md, "Card anatomy"). Real cards will be built from marts with the same shape.

export type CardType = 'state_stand_out' | 'national_organizations' | 'contracts_without_competition' | 'grant_categories';
// A card type with no published cards has no filter chip. Cards that are not published are not shipped.

export const CARD_TYPES: { type: CardType; label: string; blurb: string }[] = [
  { type: 'state_stand_out', label: 'States that stand out', blurb: 'States whose change in new awards differs sharply from the rest of the country.' },
  { type: 'national_organizations', label: 'National organizations', blurb: 'How grants to nationwide organizations changed, compared with all other grant recipients.' },
  { type: 'contracts_without_competition', label: 'Contracts without competition', blurb: 'Contract dollars awarded without full competition.' },
  { type: 'grant_categories', label: 'Grant categories', blurb: 'What DOJ grants are for, and how the mix changes.' },
];

export type Fmt = 'text' | 'money' | 'count' | 'pct' | 'pctpt' | 'year' | 'index' | 'urls' | 'schange' | 'smoney';
export interface Column { key: string; label: string; fmt?: Fmt; align?: 'left' | 'right'; tipKey?: string }  // tipKey: row key whose value is shown as a tooltip (e.g. the raw code behind a plain label)
export type Row = Record<string, string | number | null>;

/** One primary chart per card. Provisional periods are hatched (`provisional` key on the row). */
export type ChartSpec =
  | { kind: 'bar'; x: string; y: string; yFmt: Fmt; label: string; provisionalKey?: string; alt: string }
  | { kind: 'stack'; x: string; y: string; series: string; yFmt: Fmt; label: string; provisionalKey?: string; hatchKey?: string; labelKey?: string; alt: string; domain?: string[]; colors?: string[] }
  | { kind: 'indexed'; label: string; alt: string }   // state vs rest of the country, prior period = 100; rows are SeriesRow
  | { kind: 'diverge'; name: string; value: string; reference: number; referenceLabel: string; highlight?: string; valueFmt: Fmt; label: string; alt: string };

export interface SeriesRow { entity: 'state' | 'rest'; entityLabel: string; role: 'prior' | 'current'; periodLabel: string; value: number; index: number | null; provisional: boolean }
export interface DriverTable { title: string; intro: string; caption: string; columns: Column[]; rows: Row[]; note?: string }
export interface YearView { key: string; label: string; headline: string; why?: string; labelText?: string | null; notes: string[]; drivers: DriverTable[] }
export interface Caveat { text: string; issue?: string; key?: string }
export interface Status { verified: string | null; report?: string | null; note?: string }   // "Verified <date>" only when the verifier has signed off

export interface Card {
  id: string;
  type: CardType;
  headline: string;      // one neutral sentence with numbers
  why: string;           // one line: the baseline and the comparison used
  chart: ChartSpec;
  chartRows: Row[];
  seriesRows?: SeriesRow[];                       // indexed chart (card 4)
  evidence?: { title: string; note: string; rows: SeriesRow[]; alt: string; table: { caption: string; columns: Column[]; rows: Row[] } };  // award-cycle panel
  labelText?: string | null;                      // pre-rendered label sentence, shown under the headline
  fixedLine?: string | null;                      // "This compares award totals; it doesn't indicate anything improper."
  drivers?: DriverTable[];
  extraCharts?: { title: string; chart: ChartSpec; rows: Row[]; note?: string; table?: { caption: string; columns: Column[]; rows: Row[] } }[];   // more charts of the same card (card 2: count share as well as dollar share)
  yearViews?: YearView[];                          // per-year headline, notes and tables, chosen with a year selector (card 2)
  csvPath?: string;                               // marts/<agency>/<csvPath>; placeholder cards generate their CSV in the browser
  category?: string;                              // reader word: grants / contracts
  categoryName?: string;                          // Justice Connection grant category (card 3), for the desk's category filter
  whyLabel?: string;                              // overrides the "Why it stands out." lead ('' = no lead)
  chartNote?: string;                             // footnote under the primary chart heading
  key?: { v: string; l: string };                 // the key number shown in the desk list: a figure already in the marts (a mart column, formatted only)
  spark?: number[];
  sparkHighlight?: boolean;                       // mark the last point (the card's own period); false when the series stops before it                                // sparkline values from series already in the marts
  chartTitle?: string;                            // heading above the primary chart when there are extra charts
  earlier?: boolean;                              // an earlier year, hidden on the desk unless asked for
  period?: string;
  table: { caption: string; columns: Column[]; rows: Row[] };
  caveats: Caveat[];
  how: { definition: string; fields: string[]; metrics: string; query?: string; steps: string[] };
  meta: { source: string; dataAsOf: string; definition: string; period: string };
  status: Status;
  placeholder: boolean;  // true while the numbers are invented to show the layout
  agency?: string;
  aliases?: string[];    // other card ids that open this card (card 2: one id per year, each opens its year)
}
