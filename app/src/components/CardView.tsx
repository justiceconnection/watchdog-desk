import { useState } from 'react';
import type { Card } from '../cards/types';
import { CARD_TYPES } from '../cards/types';
import { downloadCsv } from '../cards/csv';
import { CardChart } from './CardChart';
import { CardTable } from './CardTable';
import { StatusBadge } from './Status';
import { REPORT_BASE } from './Status';

/** The full card, in the order of the spec's card anatomy. */
export function CardView({ card, onBack, requestedId, embedded, bare }: { card: Card; onBack?: () => void; requestedId?: string; embedded?: boolean; bare?: boolean }) {
  const t = CARD_TYPES.find(x => x.type === card.type)!;
  const asked = requestedId?.match(/-(\d{4})$/)?.[1] ?? null;
  const [yk, setYk] = useState<string | null>(asked);
  const view = card.yearViews ? (card.yearViews.find(v => v.key === yk) ?? card.yearViews[0]) : null;
  const why = view?.why || card.why;
  const headline = view?.headline ?? card.headline, labelText = view ? view.labelText : card.labelText;
  const drivers = view?.drivers ?? card.drivers, caveats = view ? view.notes.map(text => ({ text } as { text: string; issue?: string; key?: string })) : card.caveats;
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const download = async () => { setErr(null); setBusy(true); try { await downloadCsv(card); } catch (e) { setErr(String((e as Error).message ?? e)); } finally { setBusy(false); } };
  return (
    <article className={`card${embedded ? ' embedded' : ''}`} aria-labelledby="card-h">
      {!embedded && onBack && <button className="back" onClick={onBack}>&larr; All cards</button>}
      {!bare && <p className="eyebrow">{t.label}{card.category && <span className="tag">{card.category}</span>}{card.period && <span className="tag">{card.period}</span>}</p>}
      {embedded ? <h2 id="card-h" className="headline" tabIndex={-1}>{headline}</h2> : <h1 id="card-h" className="headline" tabIndex={-1}>{headline}</h1>}
      {labelText && <p className="label-text">{labelText}</p>}
      <StatusBadge status={card.status} placeholder={card.placeholder} />
      {card.placeholder && <p className="ph-note" role="note"><strong>Placeholder.</strong> This card type is not built yet. The numbers are invented to show the layout. They are not DOJ figures.</p>}
      <p className="why">{card.whyLabel !== '' && <strong>{card.whyLabel ?? 'Why it stands out.'} </strong>}{why}</p>
      {card.fixedLine && <p className="fixed">{card.fixedLine}</p>}

      <section aria-labelledby="chart-h"><h2 id="chart-h" className={card.extraCharts ? '' : 'sr'}>{card.chartTitle ?? (card.extraCharts ? 'By dollars' : 'Chart')}</h2>{card.chartNote && <p className="section-note">{card.chartNote}</p>}<CardChart card={card} />
        {card.extraCharts?.filter(x => !x.table).map((x, i) => <div key={i}><h2>{x.title}</h2>{x.note && <p className="section-note">{x.note}</p>}<CardChart card={card} spec={x.chart} rows={x.rows} /></div>)}</section>

      <section aria-labelledby="table-h">
        <div className="sechead"><h2 id="table-h">The numbers behind the chart</h2>
          <button className="btn primary" onClick={download} disabled={busy}>{busy ? 'Preparing...' : 'Download CSV'}</button></div>
        {err && <p className="err" role="alert">{err}</p>}
        <CardTable card={card} stack={card.table.rows.length <= 4} />
        <p className="small dim">{card.csvPath ? 'The CSV lists the individual awards behind this card, with totals, and a header that states the definition, source, data date and caveats.' : 'The CSV has the same rows as this table, with a header that states the definition, source, data date and caveats.'}</p>
      </section>

      {card.extraCharts?.filter(x => x.table).map((x, i) => (
        <section key={`x${i}`} aria-labelledby={`xc-${i}`}><h2 id={`xc-${i}`}>{x.title}</h2>{x.note && <p className="section-note">{x.note}</p>}
          <CardChart card={card} spec={x.chart} rows={x.rows} /><CardTable card={{ ...card, table: x.table! }} stack={x.table!.rows.length <= 4} /></section>))}

      {card.yearViews && <div className="yearpick"><label htmlFor="yv">Show the details for </label><select id="yv" value={view!.key} onChange={e => setYk(e.target.value)}>{card.yearViews.map(v => <option key={v.key} value={v.key}>{v.label}</option>)}</select>
        <span className="small dim"> The chart and table above show every year; the sections below follow this choice.</span></div>}
      {drivers?.map((d, i) => (
        <section key={i} aria-labelledby={`drv-${i}`}><h2 id={`drv-${i}`}>{d.title}</h2><p className="section-note">{d.intro}</p>
          {d.note && <p className="nonadd" role="note">{d.note}</p>}<CardTable limit={10} card={{ ...card, table: { caption: d.caption, columns: d.columns, rows: d.rows } }} /></section>))}

      {card.evidence && (
        <section aria-labelledby="ev-h"><h2 id="ev-h">{card.evidence.title}</h2><p className="section-note">{card.evidence.note}</p>
          <CardChart card={card} series={card.evidence.rows} alt={card.evidence.alt} />
          <CardTable card={{ ...card, table: card.evidence.table }} /></section>)}

      <section aria-labelledby="cav-h"><h2 id="cav-h">Things to keep in mind</h2>
        <ul className="caveats">{caveats.map((c, i) => <li key={i}>{c.key === 'contractor_address' ? c.text.split(/(?<=[.!?])\s+/).map((x, j) => <span key={j} className="sentence">{x}</span>) : c.text}{c.issue && <span className="dim small"> ({c.issue})</span>}</li>)}</ul></section>

      <section aria-labelledby="how-h"><h2 id="how-h">How this is calculated</h2>
        <p>{card.how.definition}</p>
        <details><summary>Steps, fields and sources</summary>
          <ol>{card.how.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <dl className="facts">
            <dt>Source</dt><dd>{card.meta.source}</dd>
            <dt>Data date</dt><dd>{card.meta.dataAsOf}</dd>
            <dt>Definition</dt><dd>{card.meta.definition}</dd>
            <dt>Period</dt><dd>{card.meta.period}</dd>
            <dt>Fields</dt><dd>{card.how.fields.map(f => <code key={f}>{f}</code>)}</dd>
            {REPORT_BASE && <><dt>Metric definition</dt><dd>{card.how.metrics}</dd>{card.how.query && <><dt>Query</dt><dd>{card.how.query}</dd></>}</>}
          </dl>
          <p className="small"><a href="?page=methods">How the cards work</a></p></details></section>

      <section aria-labelledby="status-h"><h2 id="status-h">Status</h2>
        <p>{card.status.verified ? <>Verified {card.status.verified} by an independent check against the source data.{REPORT_BASE && card.status.report && <> Report: <a href={`${REPORT_BASE}${card.status.report}`} target="_blank" rel="noreferrer">{card.status.report}</a></>}</> : 'Not yet verified. Cards are published only after an independent check against the source data.'}</p></section>
    </article>
  );
}
