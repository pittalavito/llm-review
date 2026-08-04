/**
 * RunFlowView — the full flow of one review-graph run, rendered with the
 * reusable AgentTable (one row per agent invocation, grouped by round). Each
 * row expands into the structured payload field-by-field (schema keys from
 * src/models/domain/chat.py) with a graceful raw-JSON fallback for
 * unknown/mock payloads, plus a collapsed "Dettagli tecnici" block with the
 * verbatim trace (system prompt, input, context, tokens).
 */
import { useState } from 'react';
import { ApiError, createInstruction, getOpenReviewData } from '../api/client';
import type { AgentResponseRecord, GraphReviewRecord, OpenReviewItem } from '../api/types';
import AgentTable, { ROLE_META } from './AgentTable';
import CompareView from './CompareView';

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

/** The esito badges of one row: decision/recommendation and overall score. */
function CardBadges({ record }: { record: AgentResponseRecord }) {
  const payload = record.response_payload ?? {};
  const score = num(payload, 'overall_score');
  const recommendation = text(payload, 'recommendation');
  const decision = text(payload, 'decision');
  return (
    <span className="run-flow__badges">
      {decision && <Badge variant={DECISION_VARIANT[decision] ?? 'score'}>{decision}</Badge>}
      {recommendation && <Badge variant={DECISION_VARIANT[recommendation] ?? 'score'}>{recommendation}</Badge>}
      {score !== null && <Badge variant="score">score {score}</Badge>}
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

/** The OpenReview role matching one agent role (author has no counterpart). */
const COMPARE_ROLE: Record<string, OpenReviewItem['reviewer_type'] | undefined> = {
  reviewer: 'reviewer',
  meta_reviewer: 'meta_reviewer',
  area_chair: 'area_chair',
};

/** Inline form to register a `calibration` instruction written after eyeballing
 * the compare table — anchored to the run via `run_id` and bound to the
 * compared agent's role. */
function CalibrationForm({ agentRole, runId }: { agentRole: string; runId: string }) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState('');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [savedLabel, setSavedLabel] = useState<string | null>(null);

  async function onSave() {
    if (busy || !label.trim() || !text.trim()) return;
    setBusy(true);
    setError('');
    try {
      const saved = await createInstruction({
        type: 'calibration',
        label: label.trim(),
        instruction: text.trim(),
        description: `Calibration from run ${runId}`,
        agent_role: agentRole,
        run_id: runId,
      });
      setSavedLabel(saved.label);
      setOpen(false);
      setLabel('');
      setText('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rf-calibrate">
      <button className="btn btn--ghost btn--sm" type="button" onClick={() => setOpen(!open)}>
        {open ? '✕ Annulla' : '🎯 Calibra da questa review'}
      </button>
      {savedLabel && !open && (
        <span className="rf-calibrate__saved">
          Istruzione "calibration/{savedLabel}" salvata — selezionabile in "Configura review".
        </span>
      )}
      {open && (
        <div className="rf-calibrate__form">
          <label className="paper-form__label" htmlFor="rf-calibrate-label">Label</label>
          <input
            className="paper-form__input"
            id="rf-calibrate-label"
            type="text"
            placeholder="es. severita_rating_paper_x"
            value={label}
            disabled={busy}
            onChange={(e) => setLabel(e.target.value)}
          />
          <label className="paper-form__label" htmlFor="rf-calibrate-text">Istruzione</label>
          <textarea
            className="paper-form__input rf-calibrate__textarea"
            id="rf-calibrate-text"
            rows={4}
            placeholder="es. Your ratings tend to be 2 points above the human reviewers on borderline papers: weigh unresolved weaknesses more heavily…"
            value={text}
            disabled={busy}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="rf-calibrate__actions">
            <button
              className="btn btn--primary btn--sm"
              type="button"
              disabled={busy || !label.trim() || !text.trim()}
              onClick={onSave}
            >
              {busy ? 'Salvataggio…' : 'Salva istruzione'}
            </button>
            <span className="rf-calibrate__hint">
              Ancorata a run <span className="paper-list__id">{runId}</span> · ruolo {agentRole}
            </span>
          </div>
          {error && <p className="paper-form__error">{error}</p>}
        </div>
      )}
    </div>
  );
}

export default function RunFlowView({ record, compareEnabled = false }: { record: GraphReviewRecord; compareEnabled?: boolean }) {
  const [compareAgent, setCompareAgent] = useState<AgentResponseRecord | null>(null);
  const [openReviews, setOpenReviews] = useState<OpenReviewItem[] | null>(null);
  const [openReviewsError, setOpenReviewsError] = useState('');

  const records = record.agent_records ?? [];
  if (records.length === 0) return <LegacyFlow record={record} />;

  const lastAreaChair = [...records].reverse().find((r) => r.agent_role === 'area_chair') ?? null;

  const handleCompare = (agent: AgentResponseRecord) => {
    setCompareAgent(agent);
    if (openReviews === null) {
      setOpenReviewsError('');
      getOpenReviewData(record.paper_id)
        .then(setOpenReviews)
        .catch((err) => setOpenReviewsError(err instanceof ApiError ? err.message : String(err)));
    }
  };

  // ── Compare view: field-by-field table — agent column vs the real
  // OpenReview counterpart(s), numeric mean included. ──
  if (compareAgent !== null) {
    const agentMeta = ROLE_META[compareAgent.agent_role] ?? { icon: '❓', label: compareAgent.agent_role, modifier: 'reviewer' };
    const agentTitle = compareAgent.agent_role === 'reviewer' && compareAgent.agent_index != null
      ? `${agentMeta.label} ${compareAgent.agent_index}`
      : agentMeta.label;
    const counterpartRole = COMPARE_ROLE[compareAgent.agent_role];
    const humans = (openReviews ?? []).filter((r) => r.reviewer_type === counterpartRole);

    return (
      <div className="run-flow">
        <div className="rf-compare__back">
          <button className="btn btn--ghost btn--sm" type="button" onClick={() => setCompareAgent(null)}>
            ← Torna alla run
          </button>
          <span className="rf-compare__title">{agentMeta.icon} {agentTitle} vs OpenReview</span>
        </div>
        {openReviewsError && <p className="paper-form__error">{openReviewsError}</p>}
        {!openReviewsError && openReviews === null && <p className="paper-list__empty">Caricamento…</p>}
        {openReviews !== null && humans.length === 0 && (
          <p className="paper-list__empty">Nessun dato OpenReview per questo ruolo.</p>
        )}
        {humans.length > 0 && <CompareView agent={compareAgent} humans={humans} />}
        <CalibrationForm agentRole={compareAgent.agent_role} runId={record.run_id} />
      </div>
    );
  }

  return (
    <div className="run-flow">
      <AgentTable
        records={records}
        isFinal={(r) => r === lastAreaChair}
        renderBadges={(r) => <CardBadges record={r} />}
        renderActions={compareEnabled ? (r) => (
          COMPARE_ROLE[r.agent_role] ? (
            <button
              className="btn btn--ghost btn--sm"
              type="button"
              title="Confronta con OpenReview"
              onClick={() => handleCompare(r)}
            >
              🔄 Confronta
            </button>
          ) : null
        ) : undefined}
        renderDetail={(r) => (
          <>
            <PayloadBody role={r.agent_role} payload={r.response_payload ?? {}} />
            <TechnicalDetails record={r} />
          </>
        )}
      />
    </div>
  );
}
