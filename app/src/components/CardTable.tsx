import { useState } from 'react';
import type { Card } from '../cards/types';
import { fmt } from '../util';

export function CardTable({ card, stack = true, limit }: { card: Card; stack?: boolean; limit?: number }) {
  const { columns, caption } = card.table; const [all, setAll] = useState(false);
  const narrow = typeof matchMedia !== 'undefined' && matchMedia('(max-width: 480px)').matches; const lim = limit ? (narrow ? Math.min(limit, 5) : limit) : 0;
  const rows = lim && !all ? card.table.rows.slice(0, lim) : card.table.rows;
  return (
    <>
    <div className={`tablewrap${stack ? ' stack' : ''}`} tabIndex={0} role="region" aria-label={caption}>
      <table>
        <caption>{caption}</caption>
        <thead><tr>{columns.map(c => <th key={c.key} scope="col" className={c.align === 'right' ? 'n' : ''}>{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className={r._hl === 1 ? 'hl' : undefined}>{columns.map((c, ci) => <td key={c.key} data-label={c.label} className={c.align === 'right' ? 'n' : ''}>{ci === 0 && r._hl === 1 && <span className="tagtop">Top driver</span>}{c.fmt === 'urls' ? <Links value={r[c.key]} /> : c.tipKey && r[c.tipKey] !== r[c.key] ? <span title={`Code as reported: ${r[c.tipKey]}`}>{fmt(r[c.key], c.fmt)}</span> : fmt(r[c.key], c.fmt)}</td>)}</tr>)}</tbody>
      </table>
    </div>
      {lim > 0 && card.table.rows.length > lim && <button className="btn more" aria-expanded={all} onClick={() => setAll(!all)}>{all ? `Show the first ${lim} rows` : `Show all ${card.table.rows.length} rows`}</button>}
    </>
  );
}

function Links({ value }: { value: string | number | null }) {
  const urls = String(value ?? '').split('|').filter(Boolean);
  if (!urls.length) return <>n/a</>;
  return <>{urls.map((u, i) => <span key={u}>{i > 0 && ', '}<a href={u} target="_blank" rel="noreferrer" aria-label={`Award ${i + 1} on USAspending.gov (opens in a new tab)`}>{i + 1}</a></span>)}</>;
}
