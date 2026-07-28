/**
 * App shell: header + sidebar navigation + routed content.
 * Mirrors llm_review/ui-react structure and classes so the CSS applies.
 * For now the sidebar exposes a single section: Ping Chat.
 */
import { useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import ThemeToggle from '../components/ThemeToggle';

interface NavEntry {
  to: string;
  icon: string;
  label: string;
}

const CHAT_ENTRIES: NavEntry[] = [
  { to: '/ping-chat', icon: '✎', label: 'Ping Chat' },
];

function NavItem({ entry }: { entry: NavEntry }) {
  return (
    <NavLink to={entry.to} style={{ textDecoration: 'none', color: 'inherit' }}>
      {({ isActive }) => (
        <li className={`nav__item${isActive ? ' nav__item--active' : ''}`}>
          <span className="nav__icon">{entry.icon}</span>
          <span className="nav__label">{entry.label}</span>
        </li>
      )}
    </NavLink>
  );
}

export default function AppLayout() {
  const location = useLocation();

  useEffect(() => {
    const entry = CHAT_ENTRIES.find((e) => e.to === location.pathname);
    document.title = entry
      ? `${entry.label} — LLM Review 2`
      : 'LLM Review 2 — Academic Review Platform';
  }, [location.pathname]);

  return (
    <>
      <header className="header">
        <h1 className="header__title">LLM Review 2</h1>
        <p className="header__subtitle">Academic Peer Review Platform</p>
        <div className="header__actions">
          <ThemeToggle />
        </div>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <nav>
            <ul className="nav__list">
              <li className="nav__group-title">Chat</li>
              {CHAT_ENTRIES.map((entry) => <NavItem key={entry.to} entry={entry} />)}
            </ul>
          </nav>
        </aside>

        <main className="content" id="content-area">
          <Outlet />
        </main>
      </div>
    </>
  );
}
