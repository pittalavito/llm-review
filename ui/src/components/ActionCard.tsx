/** Action card (Admin-style): title + description + one action.
 * Three flavors:
 *  - ``url``       → anchor opening the target in a new tab (external dashboards);
 *  - ``onAction``  → button running a callback (open a modal, ...);
 *  - neither       → TODO placeholder: loud badge, disabled button. */
import type { ReactNode } from 'react';

interface ActionCardProps {
  title: string;
  description: ReactNode;
  actionLabel?: string;
  url?: string;
  onAction?: () => void;
}

export default function ActionCard({ title, description, actionLabel = 'Apri ↗', url, onAction }: ActionCardProps) {
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
