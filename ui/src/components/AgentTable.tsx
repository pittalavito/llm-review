/**
 * AgentTable — the per-round table of agent invocations: one aligned grid
 * (toggle | agente | rating | confidence | tokens | esito | azioni) with a
 * sticky column header and collapsible rows.
 *
 * The table structure is fixed; what varies per usage travels as render
 * props: `renderDetail` (the panel opened by the row toggle), `renderBadges`
 * (the esito cell) and `renderActions` (the right-most cell). Omitting
 * `renderDetail` hides the toggle entirely.
 */
import { Fragment, useState, type ReactNode } from 'react';
import type { AgentResponseRecord } from '../api/types';

export const ROLE_META: Record<string, { icon: string; label: string; modifier: string }> = {
  reviewer: { icon: '🔬', label: 'Reviewer', modifier: 'reviewer' },
  meta_reviewer: { icon: '📋', label: 'Meta Reviewer', modifier: 'meta' },
  area_chair: { icon: '🪑', label: 'Area Chair', modifier: 'ac' },
  author_agent: { icon: '✍️', label: 'Author', modifier: 'author' },
};

type AgentTableProps = {
  records: AgentResponseRecord[];
  renderDetail?: (record: AgentResponseRecord) => ReactNode;
  renderBadges?: (record: AgentResponseRecord) => ReactNode;
  renderActions?: (record: AgentResponseRecord) => ReactNode;
  /** Marks the row that carries the final decision (subtle ring). */
  isFinal?: (record: AgentResponseRecord) => boolean;
};

function payloadNum(payload: Record<string, unknown>, key: string): number | null {
  const value = payload[key];
  return typeof value === 'number' ? value : null;
}

/** Rounds in insertion order (the BE persists chronologically), keyed by the
 * stored round number — normalized for display via minRound. */
function groupRounds(records: AgentResponseRecord[]): [number, AgentResponseRecord[]][] {
  const rounds = new Map<number, AgentResponseRecord[]>();
  for (const record of records) {
    rounds.set(record.round, [...(rounds.get(record.round) ?? []), record]);
  }
  return [...rounds.entries()].sort(([a], [b]) => a - b);
}

function AgentRow({ record, final, renderDetail, renderBadges, renderActions }: {
  record: AgentResponseRecord;
  final: boolean;
  renderDetail?: (record: AgentResponseRecord) => ReactNode;
  renderBadges?: (record: AgentResponseRecord) => ReactNode;
  renderActions?: (record: AgentResponseRecord) => ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta = ROLE_META[record.agent_role] ?? { icon: '❓', label: record.agent_role, modifier: 'reviewer' };
  const title = record.agent_role === 'reviewer' && record.agent_index != null
    ? `${meta.label} ${record.agent_index}`
    : meta.label;

  const payload = record.response_payload ?? {};
  const rating = payloadNum(payload, 'rating');
  const confidence = payloadNum(payload, 'confidence');

  return (
    <>
      <div className={`agent-table__row agent-table__row--${meta.modifier}${final ? ' agent-table__row--final' : ''}`}>
        <div className="agent-table__cell agent-table__cell-toggle">
          {renderDetail && (
            <button
              className="agent-table__toggle"
              type="button"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
            >
              {expanded ? '▼' : '▸'}
            </button>
          )}
        </div>
        <div className="agent-table__cell agent-table__cell-agent">
          <span className="agent-table__title">{meta.icon} {title}</span>
        </div>
        <div className="agent-table__cell agent-table__cell-model" title={record.model ?? undefined}>
          {record.model ?? '—'}
        </div>
        <div className="agent-table__cell agent-table__cell-rating">
          {rating !== null ? rating : '—'}
        </div>
        <div className="agent-table__cell agent-table__cell-confidence">
          {confidence !== null ? confidence : '—'}
        </div>
        <div className="agent-table__cell agent-table__cell-tokens">
          {record.total_tokens != null ? record.total_tokens : '—'}
        </div>
        <div className="agent-table__cell agent-table__cell-badges">
          {renderBadges?.(record)}
        </div>
        <div className="agent-table__cell agent-table__cell-actions">
          {renderActions?.(record)}
        </div>
      </div>
      {expanded && renderDetail && (
        <div className="agent-table__row-detail">
          {renderDetail(record)}
        </div>
      )}
    </>
  );
}

export default function AgentTable({ records, renderDetail, renderBadges, renderActions, isFinal }: AgentTableProps) {
  const rounds = groupRounds(records);
  if (rounds.length === 0) return null;
  const minRound = rounds[0][0];

  return (
    <div className="agent-table">
      <div className="agent-table__header">
        <div className="agent-table__cell agent-table__cell-toggle"></div>
        <div className="agent-table__cell agent-table__cell-agent">Agente</div>
        <div className="agent-table__cell agent-table__cell-model">Modello</div>
        <div className="agent-table__cell agent-table__cell-rating">Rating</div>
        <div className="agent-table__cell agent-table__cell-confidence">Confidence</div>
        <div className="agent-table__cell agent-table__cell-tokens">Tokens</div>
        <div className="agent-table__cell agent-table__cell-badges">Esito</div>
        <div className="agent-table__cell agent-table__cell-actions">Azioni</div>
      </div>
      {rounds.map(([round, roundRecords]) => (
        <Fragment key={round}>
          <h4 className="agent-table__round-title">Round {round - minRound + 1}</h4>
          <div className="agent-table__round">
            {roundRecords.map((record, i) => (
              <AgentRow
                key={`${record.agent_role}-${record.agent_index ?? 0}-${round}-${i}`}
                record={record}
                final={isFinal?.(record) ?? false}
                renderDetail={renderDetail}
                renderBadges={renderBadges}
                renderActions={renderActions}
              />
            ))}
          </div>
        </Fragment>
      ))}
    </div>
  );
}
