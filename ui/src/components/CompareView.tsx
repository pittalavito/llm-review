/**
 * CompareView — field-by-field comparison table between one graph agent and
 * the real OpenReview counterparts: rows are schema fields (numbers first,
 * then texts), columns are 🤖 Grafo | one per human | Media (numeric mean).
 * The agent's numeric cells carry the delta vs the human mean; long texts are
 * clamped and expandable per row so the two sides stay aligned.
 */
import { useState } from 'react';
import type { AgentResponseRecord, OpenReviewItem } from '../api/types';
import { ROLE_META } from './AgentTable';

type Kind = 'num' | 'enum' | 'text' | 'list';

type Row = {
  key: string;
  label: string;
  kind: Kind;
  agent: unknown;
  human: (h: OpenReviewItem) => unknown;
};

const asNum = (v: unknown): number | null => (typeof v === 'number' ? v : null);

/** The comparable fields per role: numbers/enums first, texts after. */
function rowsForRole(role: string, payload: Record<string, unknown>): Row[] {
  switch (role) {
    case 'reviewer':
      return [
        { key: 'rating', label: 'rating', kind: 'num', agent: payload.rating, human: (h) => h.rating },
        { key: 'confidence', label: 'confidence', kind: 'num', agent: payload.confidence, human: (h) => h.confidence },
        { key: 'summary', label: 'summary', kind: 'text', agent: payload.summary, human: (h) => h.summary },
        { key: 'significance', label: 'significance & novelty', kind: 'text', agent: payload.significance_and_novelty, human: (h) => h.significance_and_novelty },
        { key: 'acceptance', label: 'reasons for acceptance', kind: 'list', agent: payload.reasons_for_acceptance, human: () => null },
        { key: 'rejection', label: 'reasons for rejection', kind: 'list', agent: payload.reasons_for_rejection, human: () => null },
        { key: 'suggestions', label: 'suggestions', kind: 'list', agent: payload.suggestions, human: () => null },
        { key: 'review', label: 'review completa', kind: 'text', agent: null, human: (h) => h.review_text },
      ];
    case 'meta_reviewer':
      return [
        { key: 'score', label: 'overall score', kind: 'num', agent: payload.overall_score, human: (h) => h.overall_score },
        { key: 'recommendation', label: 'recommendation', kind: 'enum', agent: payload.recommendation, human: (h) => h.recommendation },
        { key: 'summary', label: 'summary', kind: 'text', agent: payload.summary, human: (h) => h.summary },
        { key: 'key_points', label: 'key points', kind: 'list', agent: payload.key_points, human: () => null },
      ];
    case 'area_chair':
      return [
        { key: 'decision', label: 'decision', kind: 'enum', agent: payload.decision, human: (h) => h.decision },
        { key: 'confidence', label: 'confidence', kind: 'num', agent: payload.confidence, human: (h) => h.confidence },
        { key: 'summary', label: 'summary', kind: 'text', agent: payload.summary, human: (h) => h.summary },
        { key: 'justification', label: 'justification', kind: 'text', agent: payload.justification, human: (h) => h.justification },
      ];
    default:
      return [];
  }
}

/** Column label of one human note: R1/R2… for reviewers, role name otherwise. */
function humanLabel(item: OpenReviewItem): string {
  if (item.reviewer_type === 'reviewer') {
    return item.reviewer_index != null ? `R${item.reviewer_index}` : (item.reviewer_id ?? 'R?');
  }
  return ROLE_META[item.reviewer_type]?.label ?? item.reviewer_type;
}

function formatDelta(delta: number): string {
  const rounded = Math.round(delta * 10) / 10;
  return `${rounded > 0 ? '+' : ''}${rounded}`;
}

function CellValue({ value, kind, expanded }: { value: unknown; kind: Kind; expanded: boolean }) {
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return <span className="cmp-table__empty">—</span>;
  }
  if (kind === 'num' || kind === 'enum') return <>{String(value)}</>;
  if (kind === 'list') {
    return (
      <ul className={`cmp-table__list${expanded ? '' : ' cmp-table__clamp'}`}>
        {(value as unknown[]).map((v, i) => <li key={i}>{String(v)}</li>)}
      </ul>
    );
  }
  return <div className={expanded ? undefined : 'cmp-table__clamp'}>{String(value)}</div>;
}

export default function CompareView({ agent, humans }: { agent: AgentResponseRecord; humans: OpenReviewItem[] }) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const payload = agent.response_payload ?? {};
  const rows = rowsForRole(agent.agent_role, payload);
  const showMedia = humans.length > 1;

  const toggleRow = (key: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <table className="cmp-table">
      <thead>
        <tr>
          <th className="cmp-table__field">Campo</th>
          <th className="cmp-table__agent">🤖 Grafo</th>
          {humans.map((h) => <th key={h.note_id}>👤 {humanLabel(h)}</th>)}
          {showMedia && <th className="cmp-table__media">Media</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const expanded = expandedRows.has(row.key);
          const expandable = row.kind === 'text' || row.kind === 'list';
          const humanValues = humans.map((h) => row.human(h));
          const humanNums = humanValues.map(asNum).filter((v): v is number => v !== null);
          const mean = humanNums.length > 0 ? humanNums.reduce((a, b) => a + b, 0) / humanNums.length : null;
          const agentNum = row.kind === 'num' ? asNum(row.agent) : null;
          const delta = agentNum !== null && mean !== null ? agentNum - mean : null;
          return (
            <tr key={row.key}>
              <td className="cmp-table__field">
                {expandable ? (
                  <button className="cmp-table__toggle" type="button" onClick={() => toggleRow(row.key)} aria-expanded={expanded}>
                    {expanded ? '▼' : '▸'} {row.label}
                  </button>
                ) : row.label}
              </td>
              <td className={`cmp-table__agent${row.kind === 'num' || row.kind === 'enum' ? ' cmp-table__num' : ''}`}>
                <CellValue value={row.agent} kind={row.kind} expanded={expanded} />
                {delta !== null && <span className="cmp-table__delta">Δ {formatDelta(delta)} vs {showMedia ? 'media' : 'umano'}</span>}
              </td>
              {humans.map((h, i) => (
                <td key={h.note_id} className={row.kind === 'num' || row.kind === 'enum' ? 'cmp-table__num' : undefined}>
                  <CellValue value={humanValues[i]} kind={row.kind} expanded={expanded} />
                </td>
              ))}
              {showMedia && (
                <td className="cmp-table__num cmp-table__media">
                  {row.kind === 'num' && mean !== null ? Math.round(mean * 10) / 10 : '—'}
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
