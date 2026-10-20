import { useCallback, useEffect, useState } from 'react';
import type { Fmt } from './cards/types';

const MINUS = '−';
const sign = (s: string) => s.replace(/^-/, MINUS);
export function money(n: number): string {
  const a = Math.abs(n); const v = a >= 1e9 ? `$${(a / 1e9).toFixed(1)}B` : a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `$${(a / 1e3).toFixed(0)}K` : `$${Math.round(a)}`;
  return (n < 0 ? MINUS : '') + v;
}
export function fmt(v: string | number | null | undefined, f: Fmt = 'text'): string {
  if (v == null || v === '') return 'n/a';
  if (typeof v === 'string') return v;
  switch (f) {
    case 'money': return money(v);
    case 'count': return sign(Math.round(v).toLocaleString('en-US'));
    case 'pct': return sign(`${(v * 100).toFixed(1)}%`);
    case 'pctpt': return sign(`${v > 0 ? '+' : ''}${(v * 100).toFixed(0)}%`);
    case 'year': return String(v);
    case 'index': return v.toFixed(0);
    case 'schange': return (v > 0 ? '+' : '') + sign(Math.round(v).toLocaleString('en-US'));
    case 'smoney': return (v > 0 ? '+' : '') + money(v);
    default: return String(v);
  }
}
/** Exact value for CSV (no rounding for display). */
export const raw = (v: string | number | null | undefined) => (v == null ? '' : String(v));

/** Our own popstate events (sent so every hook re-reads the address) are marked; a real Back/Forward is not. */
export let ownPopstate = false;
let browserNav = false;
// registered first (capture, at module load) so it is set before any hook re-reads the address
if (typeof window !== 'undefined') window.addEventListener('popstate', () => { if (!ownPopstate) browserNav = true; }, true);
/** True once after the browser's own Back or Forward moved the address. */
export function takeBrowserNav(): boolean { const b = browserNav; browserNav = false; return b; }
function ownPop() { ownPopstate = true; try { window.dispatchEvent(new PopStateEvent('popstate')); } finally { ownPopstate = false; } }

/** Query-string state so a view is linkable (?type=state_stand_out, ?card=<id>). */
export function useUrlState(key: string, dflt: string): [string, (v: string) => void] {
  const read = () => new URLSearchParams(location.search).get(key) ?? dflt;
  const [v, setV] = useState(read);
  useEffect(() => { const on = () => setV(read()); window.addEventListener('popstate', on); return () => window.removeEventListener('popstate', on); }, []);
  const set = useCallback((n: string) => {
    const u = new URL(location.href); if (n === dflt) u.searchParams.delete(key); else u.searchParams.set(key, n);
    history.pushState(null, '', u); setV(n); ownPop();
  }, [key, dflt]);
  return [v, set];
}

/** True while the media query matches (re-evaluated when it changes). */
export function useMedia(q: string): boolean {
  const [m, setM] = useState(() => matchMedia(q).matches);
  useEffect(() => { const mq = matchMedia(q); const on = () => setM(mq.matches); mq.addEventListener('change', on); on(); return () => mq.removeEventListener('change', on); }, [q]);
  return m;
}
export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
/** Change one query parameter without adding a history entry (keeps back/forward for real choices only). */
export function replaceParam(key: string, value: string) {
  const u = new URL(location.href); if (value) u.searchParams.set(key, value); else u.searchParams.delete(key);
  history.replaceState(null, '', u); ownPop();
}
