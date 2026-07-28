/** Admin section: app config + links to the service dashboards.
 * Everything comes from GET /admin/config (the backend .env, secrets already
 * masked by the BE): the Config card opens a modal with the whole table, the
 * dashboard links take their ports from it and the host from the browser
 * location. Dashboards run as separate containers
 * (resource/scripts/2-start-docker.py) and open in a dedicated tab. */
import { useEffect, useState, type ReactNode } from 'react';
import { getAdminConfig } from '../api/client';
import type { AppConfig } from '../api/types';

const DEFAULT_REDIS_PORT = 8083;
const DEFAULT_POSTGRES_PORT = 8084;

function dashboardUrl(port: number): string {
  return `http://${window.location.hostname}:${port}`;
}

function portOf(config: AppConfig | null, key: string, fallback: number): number {
  const value = config?.[key];
  return typeof value === 'number' ? value : fallback;
}

interface DashboardLinkProps {
  title: string;
  description: ReactNode;
  /** Omit while the card's target isn't available yet: the button renders disabled. */
  url?: string;
  actionLabel?: string;
  onAction?: () => void;
}

function AdminCard({ title, url, description, actionLabel = 'Apri ↗', onAction }: DashboardLinkProps) {
  return (
    <section className="admin-card">
      <div className="admin-card__info">
        <h3 className="admin-card__title">
          {title}
          {!url && !onAction && <span className="badge badge--todo">TODO</span>}
        </h3>
        <p className="admin-card__desc">{description}</p>
      </div>
      {url ? (
        <a className="btn btn--primary admin-card__btn" href={url} target="_blank" rel="noreferrer">
          {actionLabel}
        </a>
      ) : (
        <button
          className="btn btn--primary admin-card__btn"
          type="button"
          disabled={!onAction}
          onClick={onAction}
        >
          {actionLabel}
        </button>
      )}
    </section>
  );
}

function ConfigModal({ config, error, onClose }: { config: AppConfig | null; error: boolean; onClose: () => void }) {
  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="config-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="config-modal-title">Config</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        {error && <p className="paper-form__error">Impossibile caricare la config dal backend.</p>}
        {!error && !config && <p className="admin-card__desc">Caricamento…</p>}
        {config && (
          <table className="config-table">
            <tbody>
              {Object.entries(config).map(([key, value]) => (
                <tr key={key}>
                  <td className="config-table__key">{key}</td>
                  <td className="config-table__value">{value === null || value === '' ? '—' : String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function Admin() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    getAdminConfig()
      .then((data) => { if (alive) setConfig(data); })
      .catch(() => { if (alive) setConfigError(true); });
    return () => { alive = false; };
  }, []);

  const redisPort = portOf(config, 'redis_dashboard_port', DEFAULT_REDIS_PORT);
  const postgresPort = portOf(config, 'postgres_dashboard_port', DEFAULT_POSTGRES_PORT);

  return (
    <div className="section-wrap admin-section">
      <h2 className="section-title">Admin</h2>
      <p className="section-description">
        Config dell'app e dashboard di servizio — le dashboard si aprono in una scheda dedicata.
        Avvia i container con <code>python resource/scripts/2-start-docker.py</code>.
      </p>

      <AdminCard
        title="Config"
        description={<>Tutta la configurazione dell'app (dal <code>.env</code>), con i segreti mascherati.</>}
        actionLabel="Apri"
        onAction={() => setConfigOpen(true)}
      />

      <AdminCard
        title="Redis Dashboard"
        url={dashboardUrl(redisPort)}
        description={
          <>
            Cache Redis via redis-commander su <code>:{redisPort}</code>.
          </>
        }
      />

      <AdminCard
        title="SQL Dashboard"
        url={dashboardUrl(postgresPort)}
        description={
          <>
            Database Postgres via Adminer su <code>:{postgresPort}</code> — server{' '}
            <code>postgres</code>, credenziali dal <code>.env</code>.
          </>
        }
      />

      <AdminCard
        title="Files Store"
        description={
          <>
            Gestione dei paper in <code>PAPERS_DIR</code> — in preparazione.
          </>
        }
      />

      <AdminCard
        title="Back-up"
        description={<>Backup e restore degli store — in preparazione.</>}
      />

      {configOpen && <ConfigModal config={config} error={configError} onClose={() => setConfigOpen(false)} />}
    </div>
  );
}
