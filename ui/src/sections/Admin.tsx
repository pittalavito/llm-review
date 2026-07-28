/** Admin section: links to the service dashboards.
 * Both run as separate containers (resource/scripts/2-start-docker.py):
 *   - Redis  → redis-commander on :8083 (REDIS_DASHBOARD_PORT)
 *   - SQL    → Adminer on :8084 (POSTGRES_DASHBOARD_PORT)
 * They open in a dedicated tab (different origin than the app). */
import type { ReactNode } from 'react';

const REDIS_DASHBOARD_URL = 'http://localhost:8083';
const SQL_DASHBOARD_URL = 'http://localhost:8084';

interface DashboardLinkProps {
  title: string;
  description: ReactNode;
  /** Omit while the card's target isn't available yet: the button renders disabled. */
  url?: string;
}

function DashboardLink({ title, url, description }: DashboardLinkProps) {
  return (
    <section className="admin-card">
      <div className="admin-card__info">
        <h3 className="admin-card__title">
          {title}
          {!url && <span className="badge badge--todo">TODO</span>}
        </h3>
        <p className="admin-card__desc">{description}</p>
      </div>
      {url ? (
        <a className="btn btn--primary admin-card__btn" href={url} target="_blank" rel="noreferrer">
          Apri ↗
        </a>
      ) : (
        <button className="btn btn--primary admin-card__btn" type="button" disabled>
          Apri ↗
        </button>
      )}
    </section>
  );
}

export default function Admin() {
  return (
    <div className="section-wrap admin-section">
      <h2 className="section-title">Admin</h2>
      <p className="section-description">
        Dashboard di servizio — si aprono in una scheda dedicata. Avvia i container con{' '}
        <code>python resource/scripts/2-start-docker.py</code>.
      </p>

      <DashboardLink
        title="Redis Dashboard"
        url={REDIS_DASHBOARD_URL}
        description={
          <>
            Cache Redis via redis-commander su <code>:8083</code>.
          </>
        }
      />

      <DashboardLink
        title="SQL Dashboard"
        url={SQL_DASHBOARD_URL}
        description={
          <>
            Database Postgres via Adminer su <code>:8084</code> — server{' '}
            <code>postgres</code>, credenziali dal <code>.env</code>.
          </>
        }
      />

      <DashboardLink
        title="Files Store"
        description={
          <>
            Gestione dei paper in <code>PAPERS_DIR</code> — in preparazione.
          </>
        }
      />

      <DashboardLink
        title="Back-up"
        description={<>Backup e restore degli store — in preparazione.</>}
      />
    </div>
  );
}
