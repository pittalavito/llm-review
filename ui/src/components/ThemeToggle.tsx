/**
 * "A A" theme switcher: light (default) / dark, persisted in localStorage and
 * applied as data-theme on <html> so the CSS variables swap (variables.css).
 * Each "A" chip previews its own theme; the active one is ringed.
 */
import { useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'llm-review-2.theme';
const DEFAULT_THEME: Theme = 'light';

export function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch { /* storage unavailable (private mode) — fall through */ }
  return DEFAULT_THEME;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  function select(next: Theme) {
    setTheme(next);
    applyTheme(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
  }

  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      <button
        type="button"
        className={
          'theme-toggle__opt theme-toggle__opt--light' +
          (theme === 'light' ? ' theme-toggle__opt--active' : '')
        }
        title="Light theme"
        aria-pressed={theme === 'light'}
        onClick={() => select('light')}
      >
        A
      </button>
      <button
        type="button"
        className={
          'theme-toggle__opt theme-toggle__opt--dark' +
          (theme === 'dark' ? ' theme-toggle__opt--active' : '')
        }
        title="Dark theme"
        aria-pressed={theme === 'dark'}
        onClick={() => select('dark')}
      >
        A
      </button>
    </div>
  );
}
