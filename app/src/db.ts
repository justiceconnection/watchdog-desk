// DuckDB-WASM loader, ready for the real card marts (marts/<agency>/cards/*.parquet, built by the analytics engineer).
// Same approach as the archived dashboards: fetch the Parquet once, register it in memory, query in the browser.
// Not used yet: the desk shows placeholder cards until the card 4 mart exists.
import * as duckdb from '@duckdb/duckdb-wasm';
import wasmMvp from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url';
import workerMvp from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url';
import wasmEh from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import workerEh from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';

let dbP: Promise<duckdb.AsyncDuckDB> | null = null;
export const getDb = () => (dbP ??= (async () => {
  const bundle = await duckdb.selectBundle({ mvp: { mainModule: wasmMvp, mainWorker: workerMvp }, eh: { mainModule: wasmEh, mainWorker: workerEh } });
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(bundle.mainWorker!));
  await db.instantiate(bundle.mainModule);
  return db;
})());

const loaded = new Map<string, Promise<string | null>>();
/** Table expression for a mart file, or null when it does not exist. rel e.g. "015/cards/card_state_anomalies.parquet". */
export function tryMart(rel: string): Promise<string | null> {
  const file = rel.replace(/\//g, '__');
  let p = loaded.get(file);
  if (!p) {
    p = (async () => {
      const res = await fetch(`${import.meta.env.BASE_URL}marts/${rel}`); if (!res.ok) return null;
      const buf = new Uint8Array(await res.arrayBuffer()); if (String.fromCharCode(...buf.slice(0, 4)) !== 'PAR1') return null;
      await (await getDb()).registerFileBuffer(file, buf); return `read_parquet('${file}')`;
    })();
    loaded.set(file, p);
  }
  return p;
}
export async function query<T = Record<string, unknown>>(sql: string, params: (string | number)[] = []): Promise<T[]> {
  const conn = await (await getDb()).connect();
  try {
    const stmt = await conn.prepare(sql); const r = await stmt.query(...params); await stmt.close();
    return r.toArray().map(x => { const o = x.toJSON() as Record<string, unknown>; for (const k in o) { const v = o[k]; if (typeof v === 'bigint') o[k] = Number(v); else if (v && typeof v === 'object' && typeof (v as { toArray?: unknown }).toArray === 'function') o[k] = Array.from((v as { toArray(): ArrayLike<unknown> }).toArray()); } return o as T; });
  } finally { await conn.close(); }
}
