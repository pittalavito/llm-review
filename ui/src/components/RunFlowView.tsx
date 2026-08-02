/**
 * RunFlowView — the full flow of one review-graph run, as a timeline per
 * round: reviewer cards → meta review → area chair (→ author rebuttal when the
 * committee asked for a revision). The last area-chair card carries the final
 * decision. Every card renders its structured payload field-by-field (schema
 * keys from src/models/domain/chat.py) with a graceful raw-JSON fallback for
 * unknown/mock payloads, plus a collapsed "Dettagli tecnici" block with the
 * verbatim trace (system prompt, input, context, tokens).
 */
import { Fragment } from 'react';
import type { AgentResponseRecord, GraphReviewRecord } from '../api/types';

const ROLE_META: Record<string, { icon: string; label: string; modifier: string }> = {
  reviewer: { icon: '🔬', label: 'Reviewer', modifier: 'reviewer' },
  meta_reviewer: { icon: '📋', label: 'Meta Reviewer', modifier: 'meta' },
  area_chair: { icon: '🪑', label: 'Area Chair', modifier: 'ac' },
  author_agent: { icon: '✍️', label: 'Author', modifier: 'author' },
};

const DECISION_VARIANT: Record<string, string> = {
  accept: 'accept',
  minor_revision: 'revise',
  major_revision: 'revise',
  reject: 'reject',
};

// ---------------------------------------------------------------------------
// Payload helpers — every read is defensive: keys may be missing (mock runs).
// ---------------------------------------------------------------------------

function text(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function items(payload: Record<string, unknown>, key: string): string[] {
  const value = payload[key];
  return Array.isArray(value) ? value.map((v) => String(v)) : [];
}

function num(payload: Record<string, unknown>, key: string): number | null {
  const value = payload[key];
  return typeof value === 'number' ? value : null;
}

/** Keys not consumed by the structured renderer — dumped as raw JSON. */
function leftoverKeys(payload: Record<string, unknown>, used: string[]): Record<string, unknown> {
  const rest: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (!used.includes(key)) rest[key] = value;
  }
  return rest;
}

function Badge({ variant, children }: { variant?: string; children: React.ReactNode }) {
  return <span className={`run-flow__badge${variant ? ` run-flow__badge--${variant}` : ''}`}>{children}</span>;
}

function FieldBlock({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="run-flow__field">
      <span className="prompts__field-label">{label}</span>
      <p className="run-flow__text">{value}</p>
    </div>
  );
}

function FieldList({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div className="run-flow__field">
      <span className="prompts__field-label">{label}</span>
      <ul className="run-flow__list">
        {values.map((value, i) => <li key={i}>{value}</li>)}
      </ul>
    </div>
  );
}

function RawJson({ payload }: { payload: Record<string, unknown> }) {
  if (Object.keys(payload).length === 0) return null;
  return <pre className="run-flow__pre">{JSON.stringify(payload, null, 2)}</pre>;
}

// ---------------------------------------------------------------------------
// Per-role payload renderers — schema keys from models/domain/chat.py.
// ---------------------------------------------------------------------------

function ReviewerBody({ payload }: { payload: Record<string, unknown> }) {
  const used = ['summary', 'significance_and_novelty', 'reasons_for_acceptance', 'reasons_for_rejection', 'suggestions', 'rating', 'confidence'];
  return (
    <>
      <FieldBlock label="summary" value={text(payload, 'summary')} />
      <FieldBlock label="significance & novelty" value={text(payload, 'significance_and_novelty')} />
      <FieldList label="reasons for acceptance" values={items(payload, 'reasons_for_acceptance')} />
      <FieldList label="reasons for rejection" values={items(payload, 'reasons_for_rejection')} />
      <FieldList label="suggestions" values={items(payload, 'suggestions')} />
      <RawJson payload={leftoverKeys(payload, used)} />
    </>
  );
}

function MetaBody({ payload }: { payload: Record<string, unknown> }) {
  const used = ['summary', 'key_points', 'overall_score', 'recommendation'];
  return (
    <>
      <FieldBlock label="summary" value={text(payload, 'summary')} />
      <FieldList label="key points" values={items(payload, 'key_points')} />
      <RawJson payload={leftoverKeys(payload, used)} />
    </>
  );
}

function AreaChairBody({ payload }: { payload: Record<string, unknown> }) {
  const used = ['summary', 'justification', 'decision', 'confidence'];
  return (
    <>
      <FieldBlock label="summary" value={text(payload, 'summary')} />
      <FieldBlock label="justification" value={text(payload, 'justification')} />
      <RawJson payload={leftoverKeys(payload, used)} />
    </>
  );
}

function AuthorBody({ payload }: { payload: Record<string, unknown> }) {
  const used = ['rebuttal', 'reviewer_rebuttals', 'revised_sections', 'key_changes'];
  const rebuttals = Array.isArray(payload.reviewer_rebuttals) ? payload.reviewer_rebuttals as Record<string, unknown>[] : [];
  const sections = Array.isArray(payload.revised_sections) ? payload.revised_sections as Record<string, unknown>[] : [];
  return (
    <>
      <FieldBlock label="rebuttal" value={text(payload, 'rebuttal')} />
      {rebuttals.map((r, i) => (
        <FieldBlock key={i} label={`risposta a ${String(r.reviewer_name ?? `reviewer ${i + 1}`)}`} value={typeof r.response === 'string' ? r.response : null} />
      ))}
      {sections.length > 0 && (
        <div className="run-flow__field">
          <span className="prompts__field-label">sezioni riviste</span>
          {sections.map((s, i) => (
            <details key={i} className="run-flow__section">
              <summary>{String(s.section_name ?? `sezione ${i + 1}`)}</summary>
              <p className="run-flow__text">{String(s.content ?? '')}</p>
            </details>
          ))}
        </div>
      )}
      <FieldList label="key changes" values={items(payload, 'key_changes')} />
      <RawJson payload={leftoverKeys(payload, used)} />
    </>
  );
}

function PayloadBody({ role, payload }: { role: string; payload: Record<string, unknown> }) {
  switch (role) {
    case 'reviewer': return <ReviewerBody payload={payload} />;
    case 'meta_reviewer': return <MetaBody payload={payload} />;
    case 'area_chair': return <AreaChairBody payload={payload} />;
    case 'author_agent': return <AuthorBody payload={payload} />;
    default: return <RawJson payload={payload} />;
  }
}

/** The badges next to the card title, per role. */
function CardBadges({ record, isFinal }: { record: AgentResponseRecord; isFinal: boolean }) {
  const payload = record.response_payload ?? {};
  const rating = num(payload, 'rating');
  const confidence = num(payload, 'confidence');
  const score = num(payload, 'overall_score');
  const recommendation = text(payload, 'recommendation');
  const decision = text(payload, 'decision');
  return (
    <span className="run-flow__badges">
      {isFinal && <Badge variant="final">Decisione finale</Badge>}
      {decision && <Badge variant={DECISION_VARIANT[decision] ?? 'score'}>{decision}</Badge>}
      {recommendation && <Badge variant={DECISION_VARIANT[recommendation] ?? 'score'}>{recommendation}</Badge>}
      {rating !== null && <Badge variant="score">rating {rating}</Badge>}
      {score !== null && <Badge variant="score">score {score}</Badge>}
      {confidence !== null && <Badge>confidence {confidence}</Badge>}
    </span>
  );
}

function TechnicalDetails({ record }: { record: AgentResponseRecord }) {
  const tokens = [
    record.input_tokens != null ? `input ${record.input_tokens}` : null,
    record.output_tokens != null ? `output ${record.output_tokens}` : null,
    record.total_tokens != null ? `totale ${record.total_tokens}` : null,
    record.latency_seconds != null ? `${record.latency_seconds.toFixed(1)}s` : null,
  ].filter(Boolean).join(' · ');
  return (
    <details className="run-flow__tech">
      <summary>Dettagli tecnici</summary>
      {tokens && <p className="run-flow__tokens">token: {tokens}</p>}
      {record.system_prompt && (
        <>
          <span className="prompts__field-label">system prompt</span>
          <pre className="run-flow__pre">{record.system_prompt}</pre>
        </>
      )}
      {record.input_message && (
        <>
          <span className="prompts__field-label">input message</span>
          <pre className="run-flow__pre">{record.input_message}</pre>
        </>
      )}
      {record.context_used && (
        <>
          <span className="prompts__field-label">context</span>
          <pre className="run-flow__pre">{record.context_used}</pre>
        </>
      )}
    </details>
  );
}

function AgentCard({ record, isFinal }: { record: AgentResponseRecord; isFinal: boolean }) {
  const meta = ROLE_META[record.agent_role] ?? { icon: '❓', label: record.agent_role, modifier: 'reviewer' };
  const title = record.agent_role === 'reviewer' && record.agent_index != null
    ? `${meta.label} ${record.agent_index}`
    : meta.label;
  return (
    <section className={`run-flow__card run-flow__card--${meta.modifier}${isFinal ? ' run-flow__card--final' : ''}`}>
      <header className="run-flow__card-header">
        <span className="run-flow__card-title">{meta.icon} {title}</span>
        <CardBadges record={record} isFinal={isFinal} />
      </header>
      <PayloadBody role={record.agent_role} payload={record.response_payload ?? {}} />
      <TechnicalDetails record={record} />
    </section>
  );
}

/** Rounds in insertion order (the BE persists chronologically), keyed by the
 * stored round number — 0-based today, normalized for display via minRound. */
function groupRounds(records: AgentResponseRecord[]): [number, AgentResponseRecord[]][] {
  const rounds = new Map<number, AgentResponseRecord[]>();
  for (const record of records) {
    rounds.set(record.round, [...(rounds.get(record.round) ?? []), record]);
  }
  return [...rounds.entries()].sort(([a], [b]) => a - b);
}

/** Legacy runs without agent_records: render the aggregate payloads flat. */
function LegacyFlow({ record }: { record: GraphReviewRecord }) {
  return (
    <div className="run-flow">
      <p className="paper-list__empty">
        Nessun dettaglio per-agente disponibile per questa run — mostro le risposte aggregate.
      </p>
      {(record.reviews_response ?? []).map((payload, i) => (
        <section key={i} className="run-flow__card run-flow__card--reviewer">
          <header className="run-flow__card-header"><span className="run-flow__card-title">🔬 Reviewer {i + 1}</span></header>
          <ReviewerBody payload={payload} />
        </section>
      ))}
      {record.meta_review_response && (
        <section className="run-flow__card run-flow__card--meta">
          <header className="run-flow__card-header"><span className="run-flow__card-title">📋 Meta Reviewer</span></header>
          <MetaBody payload={record.meta_review_response} />
        </section>
      )}
      {record.area_chair_response && (
        <section className="run-flow__card run-flow__card--ac">
          <header className="run-flow__card-header"><span className="run-flow__card-title">🪑 Area Chair</span></header>
          <AreaChairBody payload={record.area_chair_response} />
        </section>
      )}
      {record.author_response && (
        <section className="run-flow__card run-flow__card--author">
          <header className="run-flow__card-header"><span className="run-flow__card-title">✍️ Author</span></header>
          <AuthorBody payload={record.author_response} />
        </section>
      )}
    </div>
  );
}

export default function RunFlowView({ record }: { record: GraphReviewRecord }) {
  const records = record.agent_records ?? [];
  if (records.length === 0) return <LegacyFlow record={record} />;

  const rounds = groupRounds(records);
  const minRound = rounds[0][0];
  const lastAreaChair = [...records].reverse().find((r) => r.agent_role === 'area_chair') ?? null;

  return (
    <div className="run-flow">
      {rounds.map(([round, roundRecords]) => (
        <Fragment key={round}>
          <h4 className="run-flow__round-title">Round {round - minRound + 1}</h4>
          <div className="run-flow__round">
            {roundRecords.map((agentRecord, i) => (
              <AgentCard
                key={`${agentRecord.agent_role}-${agentRecord.agent_index ?? 0}-${round}-${i}`}
                record={agentRecord}
                isFinal={agentRecord === lastAreaChair}
              />
            ))}
          </div>
        </Fragment>
      ))}
    </div>
  );
}
