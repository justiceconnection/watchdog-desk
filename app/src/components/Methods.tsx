import { useState } from 'react';
import { loadMethods } from '../cards/card4';
import { METHODS_MD } from '../methodsContent';
import { SPEC_TEXT } from '../methodsText';
import { useAsync } from '../useAsync';
import { Markdown } from './Markdown';

/** "How the cards work": the fiscal analyst's reader text (docs/specs/watchdog-cards.md, Appendix C), shown verbatim, then the list of national organizations from the desk data. */
export function MethodsPage({ agency, onBack }: { agency: string; onBack: () => void }) {
  const m = useAsync(() => loadMethods(agency), [agency]); const [all, setAll] = useState(false);
  return (
    <article className="card" aria-labelledby="m-h">
      <button className="back" onClick={onBack}>&larr; All cards</button>
      <Markdown text={METHODS_MD} />
      {m.data && m.data.orgs.length > 0 && (
        <section><h2>The national organizations on the list ({m.data.orgs.length})</h2>
          <button className="btn" aria-expanded={all} onClick={() => setAll(!all)}>{all ? 'Hide the list' : 'Show the list'}</button>
          {all && <div className="tablewrap" tabIndex={0} role="region" aria-label="National organizations" style={{ marginTop: 10 }}><table><caption>National organizations</caption><thead><tr><th scope="col">Organization</th><th scope="col">Recipient ID</th><th scope="col">Why it is on the list</th></tr></thead>
            <tbody>{m.data.orgs.map(o => <tr key={o.uei}><td>{o.name}</td><td>{o.uei}</td><td>{o.basis.split('+').map(k => SPEC_TEXT.natorgBasis[k] ?? '').filter(Boolean).join('; ') || 'n/a'}</td></tr>)}</tbody></table></div>}</section>)}
      {m.error && <p className="err" role="alert">The organization list could not be loaded: {m.error}</p>}
    </article>
  );
}
