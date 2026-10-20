// "Download CSV": built in the browser from the card's own pre-filtered rows. No server call.
import type { Card } from './types';
import { raw } from '../util';

const q = (v: string) => (/[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
const comment = (k: string, v: string) => `# ${k}: ${v.replace(/\s*\n\s*/g, ' ')}`;

export function cardCsv(c: Card, generated = new Date()): string {
  const head = [
    comment('Watchdog Desk card', c.headline),
    comment('Card id', c.id),
    comment('Status', c.status.verified ? `Verified ${c.status.verified}` : 'NOT YET VERIFIED: do not cite as verified'),
    ...(c.placeholder ? [comment('WARNING', 'PLACEHOLDER DATA: these numbers are invented to show the layout and are not real DOJ figures')] : []),
    comment('Definition', c.meta.definition),
    comment('Period', c.meta.period),
    comment('Source', c.meta.source),
    comment('Data date', c.meta.dataAsOf),
    ...c.caveats.map((x, i) => comment(`Caveat ${i + 1}`, x.text)),
    comment('How calculated', `${c.how.metrics}; fields: ${c.how.fields.join(', ')}`),
    comment('Generated', generated.toISOString().slice(0, 10)),
    comment('Note', 'Lines starting with # are metadata. Dollar amounts are nominal. Obligations and outlays are never added together.'),
  ];
  const cols = c.table.columns;
  const rows = c.table.rows.map(r => cols.map(k => q(raw(r[k.key]))).join(','));
  return [...head, cols.map(k => q(k.label)).join(','), ...rows].join('\r\n') + '\r\n';
}

/** Real cards: the CSV is a prebuilt file in the mart folder (desk/csv/<card_id>.csv); the status line is added on top. Placeholder cards: built here. */
export async function downloadCsv(c: Card): Promise<void> {
  let text: string;
  if (c.csvPath && c.agency) {
    const res = await fetch(`${import.meta.env.BASE_URL}marts/${c.agency}/${c.csvPath}`);
    if (!res.ok) throw new Error(`The data file could not be loaded (${res.status}).`);
    text = `# Status: ${c.status.verified ? `Verified ${c.status.verified}` : 'NOT YET VERIFIED: do not cite as verified'}\r\n` + (await res.text());
  } else text = cardCsv(c);
  const blob = new Blob(['\uFEFF', text], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `watchdog-desk-${c.id}.csv`; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
