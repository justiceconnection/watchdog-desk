import { useState } from 'react';

type T = 'auto' | 'light' | 'dark';
export function ThemeToggle() {
  const [t, setT] = useState<T>(() => (document.documentElement.dataset.theme as T) || 'auto');
  const next = () => {
    const n: T = t === 'auto' ? 'light' : t === 'light' ? 'dark' : 'auto'; setT(n);
    if (n === 'auto') { delete document.documentElement.dataset.theme; try { localStorage.removeItem('wd-theme'); } catch { /* private mode */ } }
    else { document.documentElement.dataset.theme = n; try { localStorage.setItem('wd-theme', n); } catch { /* private mode */ } }
  };
  return <button className="btn" onClick={next} aria-label={`Colour theme: ${t}. Change theme`}>Theme: {t}</button>;
}
