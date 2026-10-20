import type { ReactNode } from 'react';

// A small renderer for the methods text (headings, paragraphs, bullet and numbered lists, tables, **bold**). It renders the text exactly as written.
const inline = (s: string): ReactNode[] => s.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((t, i) => (t.startsWith('**') ? <strong key={i}>{t.slice(2, -2)}</strong> : <span key={i}>{t}</span>));
const cells = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());

export function Markdown({ text, extra }: { text: string; extra?: Record<string, ReactNode> }) {
  const lines = text.split('\n'); const out: ReactNode[] = []; let i = 0; let k = 0; let h1Done = false;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    const h = l.match(/^(#{2,4}) (.*)$/);
    if (h) { // the first heading is the page title; the others are section headings
      const first = !h1Done; h1Done = true;
      const title = h[2];
      out.push(first ? <h1 key={k++} id="m-h" className="headline">{title}</h1> : <h2 key={k++}>{title}</h2>);
      if (extra?.[title]) out.push(<div key={k++}>{extra[title]}</div>);
      i++; continue;
    }
    if (l.startsWith('|')) {
      const rows: string[][] = []; while (i < lines.length && lines[i].startsWith('|')) { rows.push(cells(lines[i])); i++; }
      const head = rows[0], body = rows.slice(2);
      out.push(<div key={k++} className="tablewrap" tabIndex={0} role="region" aria-label={head.join(', ')}><table><thead><tr>{head.map((c, j) => <th key={j} scope="col">{inline(c)}</th>)}</tr></thead>
        <tbody>{body.map((r, j) => r.slice(1).every(c => c === '') ? <tr key={j}><th colSpan={r.length} scope="rowgroup" className="grp">{inline(r[0])}</th></tr> : <tr key={j}>{r.map((c, m) => <td key={m}>{inline(c)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^- /.test(l)) { const items: string[] = []; while (i < lines.length && /^- /.test(lines[i])) { items.push(lines[i].slice(2)); i++; } out.push(<ul key={k++} className="mdlist">{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ul>); continue; }
    if (/^\d+\. /.test(l)) { const items: string[] = []; while (i < lines.length && /^\d+\. /.test(lines[i])) { items.push(lines[i].replace(/^\d+\. /, '')); i++; } out.push(<ol key={k++} className="mdlist">{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ol>); continue; }
    const para: string[] = []; while (i < lines.length && lines[i].trim() && !/^(#{2,4} |\||- |\d+\. )/.test(lines[i])) { para.push(lines[i]); i++; }
    out.push(<p key={k++}>{inline(para.join(' '))}</p>);
  }
  return <>{out}</>;
}
