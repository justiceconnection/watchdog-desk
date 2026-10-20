import { useEffect, useState } from 'react';

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; loading: boolean; error?: string } {
  const [s, setS] = useState<{ data: T | null; loading: boolean; error?: string }>({ data: null, loading: true });
  useEffect(() => {
    let dead = false; setS(p => ({ ...p, loading: true }));
    fn().then(d => { if (!dead) setS({ data: d, loading: false }); }).catch(e => { if (!dead) setS({ data: null, loading: false, error: String(e?.message ?? e) }); });
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return s;
}
