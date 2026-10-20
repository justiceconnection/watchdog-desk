import { useEffect, useRef, useState } from 'react';
import type { Card } from '../cards/types';
import { CARD_TYPES } from '../cards/types';
import { reducedMotion, takeBrowserNav, useMedia } from '../util';
import { CardView } from './CardView';
import { Spark } from './Spark';

const typeLabel = (c: Card) => CARD_TYPES.find(t => t.type === c.type)?.label ?? '';
const rowId = (c: Card) => `tab-${c.id}`;

interface P { cards: Card[]; selected: Card; requestedId: string; onSelect: (id: string) => void }

/** The desk list and card: a split list and detail from 760 px up, an accordion below that. */
export function Desk(p: P) {
  const wide = useMedia('(min-width: 760px)');
  return wide ? <Split {...p} /> : <Accordion {...p} />;
}

const Key = ({ c }: { c: Card }) => (c.key ? <span className="lkw"><span className="lk">{c.key.v}</span><span className="lkl">{c.key.l}</span></span> : null);

function Split({ cards, selected, requestedId, onSelect }: P) {
  const focusNext = useRef<string | null>(null);
  useEffect(() => {
    const nav = takeBrowserNav();
    if (focusNext.current || nav) { focusNext.current = null; const el = document.getElementById(rowId(selected)); el?.focus(); el?.scrollIntoView({ block: 'nearest' }); }
  }, [selected.id]);
  const i = cards.findIndex(c => c.id === selected.id);
  const go = (n: number) => { const c = cards[Math.max(0, Math.min(cards.length - 1, n))]; if (c.id === selected.id) return; focusNext.current = c.id; onSelect(c.id); };   // no change, no history entry
  const keys = (e: React.KeyboardEvent) => {
    const d: Record<string, number> = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: cards.length - 1 }; if (!(e.key in d)) return; e.preventDefault(); go(d[e.key]);
  };
  return (
    <div className="split">
      <div className="list" role="tablist" aria-orientation="vertical" aria-label={`Cards, ${cards.length} shown. Use the up and down arrow keys.`} onKeyDown={keys}>
        {cards.map(c => (
          <button key={c.id} id={rowId(c)} role="tab" className="lrow" aria-selected={c.id === selected.id} aria-controls="desk-panel" tabIndex={c.id === selected.id ? 0 : -1} onClick={() => { focusNext.current = c.id; onSelect(c.id); }}>
            <span className="lh">{c.headline}</span>
            <span className="lt">{typeLabel(c)} &middot; {c.period}</span>
            <span className="lr"><Spark values={c.spark} w={56} h={22} highlight={c.sparkHighlight !== false} /><Key c={c} /></span>
          </button>))}
      </div>
      <div id="desk-panel" role="tabpanel" aria-labelledby={rowId(selected)} className="panel-pane">
        <CardView key={selected.id} card={selected} requestedId={requestedId} embedded />
      </div>
    </div>
  );
}

function Accordion({ cards, selected, requestedId, onSelect }: P) {
  const moved = useRef(false); const [closed, setClosed] = useState(false);
  useEffect(() => {   // a new selection (from a tap, the address or Back/Forward) opens that card
    setClosed(false);
    const nav = takeBrowserNav();
    if (moved.current || nav) { moved.current = false; setTimeout(() => { document.getElementById(`acc-${selected.id}`)?.scrollIntoView({ block: 'start', behavior: reducedMotion() ? 'auto' : 'smooth' }); document.getElementById('card-h')?.focus({ preventScroll: true }); }, 0); }
  }, [selected.id]);
  const open = (c: Card) => c.id === selected.id && !closed;
  const toggle = (c: Card) => {
    if (c.id === selected.id) { const next = !closed; setClosed(next); if (!next) { moved.current = true; setTimeout(() => { document.getElementById('card-h')?.focus({ preventScroll: true }); }, 0); } else document.getElementById(`acch-${c.id}`)?.focus(); return; }
    setClosed(false); moved.current = true; onSelect(c.id);
  };
  return (
    <div className="acclist">
      {cards.map(c => { const o = open(c); return (
        <article key={c.id} id={`acc-${c.id}`} className={`acc${o ? ' open' : ''}`}>
          <h3 className="acch3"><button id={`acch-${c.id}`} className="acch" aria-expanded={o} aria-controls={`accp-${c.id}`} onClick={() => toggle(c)}>
            <span className="acctext"><span className="eyebrow">{typeLabel(c)}<span className="tag">{c.period}</span></span>{o ? <span className="ah hide">Hide this card</span> : <span className="ah">{c.headline}</span>}</span>
            {!o && <Key c={c} />}
          </button></h3>
          <div id={`accp-${c.id}`} role="region" aria-labelledby={`acch-${c.id}`} hidden={!o}>
            {o && <CardView key={c.id} card={c} requestedId={requestedId} embedded bare />}
          </div>
        </article>); })}
    </div>
  );
}
