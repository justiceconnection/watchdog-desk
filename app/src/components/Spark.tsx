/** A small line from a series already in the marts (decorative: the numbers are in the card). */
export function Spark({ values, w = 80, h = 28, highlight = true }: { values?: number[]; w?: number; h?: number; highlight?: boolean }) {
  const v = (values ?? []).filter(x => Number.isFinite(x)); if (v.length < 2) return null;
  const mx = Math.max(...v), mn = Math.min(...v, 0); const x = (i: number) => 2 + (i / (v.length - 1)) * (w - 4); const y = (n: number) => h - 3 - ((n - mn) / ((mx - mn) || 1)) * (h - 8);
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline fill="none" stroke="var(--base)" strokeWidth="2" points={v.map((n, i) => `${x(i)},${y(n)}`).join(' ')} />
      {highlight && <circle cx={x(v.length - 1)} cy={y(v[v.length - 1])} r="3.5" fill="var(--accent)" />}
    </svg>
  );
}
