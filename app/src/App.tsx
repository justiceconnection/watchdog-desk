import { useEffect, useRef } from 'react';
import { loadCard4 } from './cards/card4';
import { loadCard2 } from './cards/card2';
import { loadCard3 } from './cards/card3';
import { loadNatorg } from './cards/natorg';
import { MethodsPage } from './components/Methods';
import { useAsync } from './useAsync';
import { CARD_TYPES, type CardType } from './cards/types';
import { Desk } from './components/Desk';
import { ThemeToggle } from './components/ThemeToggle';
import { replaceParam, useUrlState } from './util';

export default function App() {
  const [cardId, setCard] = useUrlState('card', '');
  const [typeRaw, setType] = useUrlState('type', 'all');
  const type = typeRaw === 'state_anomaly' ? 'state_stand_out' : CARD_TYPES.some(t => t.type === typeRaw) ? typeRaw : 'all';   // old ?type=state_anomaly links; an unknown type shows all cards
  const [page, setPage] = useUrlState('page', '');
  const [agencyRaw] = useUrlState('agency', '015'); const agency = /^[0-9A-Za-z]{1,8}$/.test(agencyRaw) ? agencyRaw : '015';
  const real = useAsync(async () => (await Promise.all([loadCard4(agency), loadNatorg(agency), loadCard2(agency), loadCard3(agency)])).flat(), [agency]);
  const [catRaw, setCat] = useUrlState('category', 'all'); const [oldRaw, setOld] = useUrlState('earlier', '0');
  const all = real.data ?? []; const hasEarlier = all.some(c => c.earlier);
  const asked = all.find(c => c.id === cardId || c.aliases?.includes(cardId));
  const showOld = oldRaw === '1' || !!asked?.earlier;   // a link to an earlier-year card shows the earlier years
  const cards = all.filter(c => showOld || !c.earlier); // earlier years (card 3) stay behind a switch
  const categories = [...new Set(cards.map(c => c.categoryName).filter((x): x is string => !!x))].sort();
  const cat = categories.includes(catRaw) ? catRaw : 'all';
  const shown = cards.filter(c => (type === 'all' || c.type === (type as CardType)) && (cat === 'all' || c.categoryName === cat));
  const sel = shown.find(c => c.id === cardId || c.aliases?.includes(cardId)) ?? shown[0];   // no ?card= (or one that is filtered out): the first visible card
  // keep the address in step with what is shown (no extra history entry)
  useEffect(() => { if (sel && cardId && sel.id !== cardId && !sel.aliases?.includes(cardId)) replaceParam('card', sel.id); }, [sel?.id, cardId]);
  useEffect(() => { document.title = page === 'methods' ? 'How the cards work | Watchdog Desk' : sel ? `${sel.headline} | Watchdog Desk` : 'Watchdog Desk: patterns in Justice Department spending'; }, [sel?.id, page]);
  const said = useRef<string | null>(null); const live = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!sel) return; if (said.current !== null && said.current !== sel.id && live.current) live.current.textContent = `Showing: ${sel.headline}`; said.current = sel.id; }, [sel?.id]);
  const count = (t: CardType) => cards.filter(c => c.type === t).length;
  const types = CARD_TYPES.filter(t => count(t.type) > 0);
  return (
    <>
      <a className="skip" href="#main">Skip to the content</a>
      <header className="top">
        <a className="brand" href="?" onClick={e => { e.preventDefault(); setPage(''); setCard(''); }}><span className="mark" aria-hidden="true" />Watchdog Desk</a>
        <nav className="nav" aria-label="Site"><a href="?page=methods" onClick={e => { e.preventDefault(); setCard(''); setPage('methods'); }}>How the cards work</a><ThemeToggle /></nav>
      </header>
      <main id="main" className={`wrap${page === 'methods' ? '' : ' wide'}`}>
        <div ref={live} className="sr" role="status" aria-live="polite" />
        {page === 'methods' ? <MethodsPage agency={agency} onBack={() => setPage('')} /> : (
          <>
            <section className="intro">
              <h1>Patterns in Justice Department spending</h1>
              <p>Each card points out one pattern in how the Department of Justice spends money, shows the numbers behind it, and lets you download them. Cards say what the data shows. They do not say why.</p>
            </section>
            <p className="intro-note">Choose a card to see its chart, the numbers behind it, how they were worked out, and a CSV you can download.</p>
            <nav aria-label="Filter cards by type" className="filters">
              <button className="chip" aria-pressed={type === 'all'} onClick={() => setType('all')}>All cards ({cards.length})</button>
              {types.map(t => <button key={t.type} className="chip" aria-pressed={type === t.type} onClick={() => setType(t.type)} title={t.blurb}>{t.label} ({count(t.type)})</button>)}
            </nav>
            {(categories.length > 0 || hasEarlier) && <div className="more-filters">
              {categories.length > 0 && <><label htmlFor="cat">Grant category </label><select id="cat" value={cat} onChange={e => setCat(e.target.value)}><option value="all">All categories</option>{categories.map(x => <option key={x} value={x}>{x}</option>)}</select></>}
              {hasEarlier && <label className="check"><input type="checkbox" checked={showOld} onChange={e => setOld(e.target.checked ? '1' : '0')} /> Include earlier years ({all.filter(c => c.earlier).length} more cards)</label>}
            </div>}
            {real.loading && <p aria-live="polite">Loading cards...</p>}
            {real.error && <p className="err" role="alert">The cards could not be loaded: {real.error}</p>}
            {!real.loading && !real.error && shown.length === 0 && <p>No cards match these filters.</p>}
            {shown.length > 0 && <p className="small dim" aria-live="polite">{shown.length} {shown.length === 1 ? 'card' : 'cards'}{type !== 'all' ? `: ${CARD_TYPES.find(t => t.type === type)?.blurb ?? ''}` : ''}</p>}
            {sel && <Desk cards={shown} selected={sel} requestedId={cardId} onSelect={id => { if (id !== sel.id) setCard(id); }} />}
          </>
        )}
      </main>
      <footer className="foot wrap small dim">
        <p>Data: USAspending.gov, Department of Justice (agency code 015), nominal dollars. A Justice Connection project. Amounts are never combined across obligations and outlays; fiscal years follow the federal year (October to September).</p>
      </footer>
    </>
  );
}
