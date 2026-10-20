import * as Plot from '@observablehq/plot';
import { useEffect, useRef, useState } from 'react';
import type { Card, SeriesRow } from '../cards/types';
import { fmt } from '../util';

const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
/** Redraw when the theme changes (data-theme attribute or the OS preference). */
function useThemeTick() {
  const [t, setT] = useState(0);
  useEffect(() => {
    const bump = () => setT(x => x + 1); const mo = new MutationObserver(bump); mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const mq = matchMedia('(prefers-color-scheme: dark)'); mq.addEventListener('change', bump); return () => { mo.disconnect(); mq.removeEventListener('change', bump); };
  }, []);
  return t;
}
const OKABE = ['#0072b2', '#d55e00', '#009e73', '#cc79a7', '#8a8a8a'];

/** One primary chart per card, drawn to scale from zero; provisional periods are hatched. The data is in the table below. */
export function CardChart({ card, series: series0, alt: alt0, spec, rows: rows0 }: { card: Card; series?: SeriesRow[]; alt?: string; spec?: Card['chart']; rows?: Card['chartRows'] }) {
  const ref = useRef<HTMLDivElement>(null); const tick = useThemeTick(); const c = spec ?? card.chart; const rows = rows0 ?? card.chartRows; const series = series0 ?? card.seriesRows ?? []; const alt = alt0 ?? c.alt; const sid = spec ? `${card.id}-${rows0 === card.chartRows ? 'a' : 'b'}` : card.id;
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ink = css('--ink'), dim = css('--dim'), accent = css('--accent'), base = css('--base'), grid = css('--line'), bg = css('--card');
    const draw = () => {
      const w = Math.max(260, el.clientWidth), narrow = w < 480; const hatchId = `hatch-${sid}`;
      const hatchId0 = sid; const common = { width: w, style: { background: 'transparent', color: ink, fontSize: narrow ? '12px' : '13px' } };
      let svg: SVGSVGElement | HTMLElement;
      if (c.kind === 'indexed') {
        const per = [...new Map(series.map(r => [r.role, r.periodLabel])).entries()].sort(a => (a[0] === 'prior' ? -1 : 1)).map(x => x[1]);
        const ent = [...new Map(series.map(r => [r.entity, r.entityLabel])).entries()].sort(a => (a[0] === 'state' ? -1 : 1));
        const col = (e: string) => (e === 'state' ? accent : base); const hid = (e: string) => `${hatchId}-${e}`;
        const ok = series.filter(r => r.index != null);
        const mk = (rs: SeriesRow[], hatch: boolean) => Plot.barY(rs, { fx: 'periodLabel', x: 'entityLabel', y: 'index', fill: (r: SeriesRow) => (hatch ? `url(#${hid(r.entity)})` : col(r.entity)), stroke: hatch ? (r: SeriesRow) => col(r.entity) : undefined, strokeWidth: 1.5,
          title: (r: SeriesRow) => `${r.entityLabel}, ${r.periodLabel}: ${fmt(r.value, card.table.columns[1].fmt)} (index ${fmt(r.index, 'index')})${r.provisional ? ', provisional' : ''}` });
        svg = Plot.plot({ ...common, height: 300, marginBottom: 34, marginTop: 24, fx: { label: null, domain: per, padding: 0.2 }, x: { label: null, domain: ent.map(e => e[1]), axis: null }, y: { label: '↑ Index (prior year = 100)', grid: true, tickFormat: (d: number) => String(d), domain: [0, Math.max(120, ...ok.map(r => r.index as number)) * 1.1] },
          marks: [Plot.ruleY([0]), mk(ok.filter(r => !r.provisional), false), mk(ok.filter(r => r.provisional), true), Plot.ruleY([100], { stroke: dim, strokeDasharray: '4 3' }),
            Plot.text(ok, { fx: 'periodLabel', x: 'entityLabel', y: 'index', text: (r: SeriesRow) => fmt(r.index, 'index'), dy: -8, fill: ink, fontWeight: 700 })] });
        const sv = svg as SVGSVGElement; const NS2 = 'http://www.w3.org/2000/svg'; const dfs = document.createElementNS(NS2, 'defs');
        dfs.innerHTML = ent.map(([e]) => `<pattern id="${hid(e)}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="${bg}"/><rect width="3" height="7" fill="${col(e)}"/></pattern>`).join('');
        sv.prepend(dfs);
      } else if (c.kind === 'diverge') {
        const sorted = [...rows].sort((a, b) => Number(b[c.value]) - Number(a[c.value])); const names = sorted.map(r => String(r[c.name]));
        const tx = (r: typeof rows[number]) => fmt(Number(r[c.value]), c.valueFmt);
        svg = Plot.plot({ ...common, height: 70 + names.length * 30, marginTop: 30, marginLeft: narrow ? 74 : 96, marginRight: 52, marginBottom: 44,
          x: { label: c.label, tickFormat: (d: number) => fmt(d, 'pctpt'), grid: true, nice: true, domain: [Math.min(0, ...sorted.map(r => Number(r[c.value]))) * (narrow ? 1.5 : 1.3), Math.max(0, ...sorted.map(r => Number(r[c.value]))) * 1.3] }, y: { label: null, domain: names },
          marks: [
            Plot.ruleX([0], { stroke: dim }),
            Plot.barX(sorted, { y: c.name, x: c.value, fill: (r: typeof rows[number]) => (r[c.name] === c.highlight ? accent : base), insetTop: 3, insetBottom: 3 }),
            Plot.text(sorted.filter(r => Number(r[c.value]) >= 0), { y: c.name, x: c.value, text: tx, textAnchor: 'start', dx: 5, fill: ink, fontWeight: 600 }),
            Plot.text(sorted.filter(r => Number(r[c.value]) < 0), { y: c.name, x: c.value, text: tx, textAnchor: 'end', dx: -5, fill: ink, fontWeight: 600 }),
            Plot.ruleX([c.reference], { stroke: ink, strokeDasharray: '5 3', strokeWidth: 1.5 }),
            Plot.text([{ x: c.reference }], { x: 'x', frameAnchor: 'top', dy: -20, text: () => c.referenceLabel, fill: ink, fontWeight: 700 }),
          ] });
      } else if (c.kind === 'bar') {
        const xs = rows.map(r => r[c.x]); const prov = rows.filter(r => c.provisionalKey && r[c.provisionalKey] === 1); const done = rows.filter(r => !(c.provisionalKey && r[c.provisionalKey] === 1));
        svg = Plot.plot({ ...common, height: 260, marginLeft: 52, marginBottom: 36, x: { label: null, type: 'band', domain: xs as number[], tickFormat: (d: number) => (prov.some(r => r[c.x] === d) ? `${d} (so far)` : String(d)), tickRotate: narrow ? -30 : 0 },
          y: { label: c.label, tickFormat: (d: number) => fmt(d, c.yFmt), grid: true },
          marks: [Plot.ruleY([0]), Plot.barY(done, { x: c.x, y: c.y, fill: base }), Plot.barY(prov, { x: c.x, y: c.y, fill: `url(#${hatchId})`, stroke: base, strokeWidth: 1.5 }),
            Plot.text(rows, { x: c.x, y: c.y, text: (r: typeof rows[number]) => fmt(Number(r[c.y]), c.yFmt), dy: -8, fill: ink, fontWeight: 600 })] });
      } else {
        const names = c.domain ?? [...new Set(rows.map(r => String(r[c.series])))]; const pk = c.provisionalKey, hk = c.hatchKey; const isP = (r: typeof rows[number]) => (!!pk && r[pk] === 1) || (!!hk && r[hk] === 1);
        const palette = c.colors ?? OKABE; const colr = (n: string) => palette[Math.max(0, names.indexOf(n)) % palette.length]; const pid = (n: string) => `${hatchId}-s${names.indexOf(n)}`;
        const years = [...new Set(rows.map(r => r[c.x]))] as number[]; const provYears = new Set(rows.filter(r => !!pk && r[pk] === 1).map(r => r[c.x]));
        const lk = c.labelKey; const aboveRows = rows.filter(r => r.top != null && Number(r[c.y]) > 0); const base0 = rows.filter(r => r.top == null);
        const topY = (r: typeof rows[number]) => Number(r.top ?? 0);
        const mkS = (rs: typeof rows, hatch: boolean) => Plot.barY(rs, { x: c.x, y: c.y, fill: hatch ? (r: typeof rows[number]) => `url(#${hk && r[hk] === 1 ? pid(String(r[c.series])) + 'd' : pid(String(r[c.series]))})` : c.series, stroke: hatch ? (r: typeof rows[number]) => colr(String(r[c.series])) : undefined, strokeWidth: 1,
          order: names, title: (r: typeof rows[number]) => `${r[c.x]}, ${r[c.series]}: ${fmt(Number(r[c.y]), c.yFmt)}${hatch && pk && r[pk] === 1 ? ' (provisional)' : ''}` });
        svg = Plot.plot({ ...common, height: 300, marginLeft: 52, marginBottom: narrow ? 44 : 30, x: { label: null, type: 'band', domain: years, tickFormat: (d: number) => (provYears.has(d) ? `${d} (so far)` : String(d)), tickRotate: narrow ? -35 : 0 }, y: { label: c.label, tickFormat: (d: number) => fmt(d, c.yFmt), grid: true, ...(aboveRows.length ? { domain: [0, Math.max(...aboveRows.map(r => 1 + Number(r[c.y]))) * 1.08] } : {}) },
          color: { domain: names, range: names.map(colr), legend: true },
          marks: [Plot.ruleY([0]), mkS(base0.filter(r => !isP(r)), false), mkS(base0.filter(isP), true),
            // rows with a `top` (SCAAP) are not part of the stack: they are drawn from 100% up to 100% + their share
            ...(aboveRows.length ? [Plot.barY(aboveRows, { x: c.x, y1: 1, y2: (r: typeof rows[number]) => 1 + Number(r[c.y]), fill: (r: typeof rows[number]) => `url(#${pid(String(r[c.series]))}d)`, stroke: (r: typeof rows[number]) => colr(String(r[c.series])), strokeWidth: 1, title: (r: typeof rows[number]) => `${r[c.x]}, ${r[c.series]}: ${r[lk ?? 'label'] ?? ''}` })] : []), ...(lk ? [Plot.text(rows.filter(r => r[lk]), { x: c.x, y: topY, text: (r: typeof rows[number]) => String(r[lk]), dy: -7, fill: ink, fontSize: 11, fontWeight: 700 })] : [])] });
        const sv2 = svg as SVGSVGElement; const dfs2 = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        dfs2.innerHTML = names.map(n => `<pattern id="${pid(n)}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="${bg}"/><rect width="3" height="7" fill="${colr(n)}"/></pattern><pattern id="${pid(n)}d" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="${bg}"/><circle cx="3" cy="3" r="1.8" fill="${colr(n)}"/></pattern>`).join('');
        (sv2.tagName === 'svg' ? sv2 : sv2.querySelector('svg'))?.prepend(dfs2);
      }
      const s = svg as SVGSVGElement;
      if (c.kind !== 'indexed' && c.kind !== 'stack' && s.querySelector && !s.querySelector(`#${hatchId}`)) { // hatch pattern for provisional periods
        const NS = 'http://www.w3.org/2000/svg'; const defs = document.createElementNS(NS, 'defs');
        defs.innerHTML = `<pattern id="${hatchId}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="${bg}"/><rect width="3" height="7" fill="${base}"/></pattern>`;
        (s.tagName === 'svg' ? s : s.querySelector('svg'))?.prepend(defs);
      }
      s.setAttribute('role', 'img'); s.setAttribute('aria-label', alt);
      const wrap = svg.tagName === 'FIGURE' ? svg : svg; el.replaceChildren(wrap);
    };
    draw(); const ro = new ResizeObserver(draw); ro.observe(el); return () => ro.disconnect();
  }, [card, c, rows, series, alt, sid, tick]);
  const ent = c.kind === 'indexed' ? [...new Map(series.map(r => [r.entity, r.entityLabel])).entries()].sort(a => (a[0] === 'state' ? -1 : 1)) : [];
  return <><div ref={ref} className="chart" />{ent.length > 0 && <ul className="legend" aria-hidden="true">{ent.map(([e, l]) => <li key={e}><i className={`sw ${e}`} />{l}</li>)}{series.some(r => r.provisional) && <li><i className="sw hatch" />Hatched = provisional (year not finished)</li>}</ul>}</>;
}
