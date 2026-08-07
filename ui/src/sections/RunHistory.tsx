/**
 * RunHistory — dedicated page (/review-graph/storico) for the run history.
 * Compact accordion rows (date · paper · decision badge · meta score · rounds);
 * expanding a run loads the full record and shows the insight panel: metric
 * cards, final rating/confidence per reviewer, mean sub-scores, then the
 * existing round-by-round RunFlowView collapsed as technical drill-down.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, getGraphRun, listGraphRuns, listPapers } from '../api/client';
import type { GraphReviewRecord, GraphReviewSummary, Paper } from '../api/types';
import { BarRow, MetricCard } from '../components/charts';
import RunFlowView from '../components/RunFlowView';
import { finalReviewers, formatNum, formatTokens, mean, payloadNum, totalTokens } from '../components/runMetrics';

const DECISION_BADGE: Record<string, string> = {
  accept: 'accept',
  minor_revision: 'revise',
  major_revision: 'revise',
  reject: 'reject',
};

function DecisionBadge({ decision }: { decision: string | null | undefined }) {
  const variant = decision ? DECISION_BADGE[decision] ?? 'none' : 'none';
  return <span className={`ri-badge ri-badge--${variant}`}>{decision?.replace('_', ' ') || '—'}</span>;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/** The insight panel of one expanded run: KPI cards + charts + drill-down. */
function RunDetail({ record, paper }: { record: GraphReviewRecord; paper: Paper | null }) {
  const navigate = useNavigate();
  const reviewers = finalReviewers(record);
  const ratings = reviewers.map((r) => payloadNum(r.response_payload, 'rating'));
  const meanRating = mean(ratings);
  const subMeans = {
    soundness: mean(reviewers.map((r) => payloadNum(r.response_payload, 'soundness'))),
    presentation: mean(reviewers.map((r) => payloadNum(r.response_payload, 'presentation'))),
    contribution: mean(reviewers.map((r) => payloadNum(r.response_payload, 'contribution'))),
  };
  const comparable = paper?.paper_type?.toLowerCase() === 'open_review';

  return (
    <div className="ri-run__body">
      {record.description && <p className="ri-run__desc">{record.description}</p>}

      <div className="ri-metrics">
        <MetricCard label="Decisione" value={<DecisionBadge decision={record.decision} />} />
        <MetricCard label="Meta score" value={formatNum(payloadNum(record.meta_review_response ?? undefined, 'overall_score'), 0)} hint="su 10" />
        <MetricCard label="Rating medio" value={formatNum(meanRating)} hint={`${reviewers.length} reviewer`} />
        <MetricCard label="Round" value={record.total_rounds} />
        <MetricCard label="Token totali" value={formatTokens(totalTokens(record))} />
      </div>

      {reviewers.length > 0 && (
        <div className="ri-block">
          <p className="ri-chart-title">Rating per reviewer <em>(ultimo round, 1–10 · S·P·C = soundness/presentation/contribution, 1–4)</em></p>
          {reviewers.map((r, i) => {
            const spc = (['soundness', 'presentation', 'contribution'] as const)
              .map((key) => payloadNum(r.response_payload, key) ?? '—').join('·');
            return (
              <BarRow
                key={i}
                label={`Reviewer ${r.agent_index ?? i + 1}`}
                sublabel={`conf. ${payloadNum(r.response_payload, 'confidence') ?? '—'} · S·P·C ${spc}`}
                value={ratings[i]}
                max={10}
              />
            );
          })}
        </div>
      )}

      {(subMeans.soundness !== null || subMeans.presentation !== null || subMeans.contribution !== null) && (
        <div className="ri-block">
          <p className="ri-chart-title">Sub-score medi dei reviewer <em>(1–4)</em></p>
          <BarRow label="soundness" value={subMeans.soundness === null ? null : Math.round(subMeans.soundness * 10) / 10} max={4} />
          <BarRow label="presentation" value={subMeans.presentation === null ? null : Math.round(subMeans.presentation * 10) / 10} max={4} />
          <BarRow label="contribution" value={subMeans.contribution === null ? null : Math.round(subMeans.contribution * 10) / 10} max={4} />
        </div>
      )}

      {comparable && (
        <button
          className="btn btn--ghost btn--sm"
          type="button"
          onClick={() => navigate(`/review-graph/confronto?paper=${encodeURIComponent(record.paper_id)}&run=${encodeURIComponent(record.run_id)}`)}
        >
          ⇄ Confronta con OpenReview
        </button>
      )}

      <details className="ri-details">
        <summary>Flusso completo round per round</summary>
        <RunFlowView record={record} compareEnabled={false} />
      </details>
    </div>
  );
}

export default function RunHistory() {
  const [runs, setRuns] = useState<GraphReviewSummary[] | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [error, setError] = useState('');
  const [paperFilter, setPaperFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [search, setSearch] = useState('');
  const [openRunId, setOpenRunId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, GraphReviewRecord>>({});
  const [detailError, setDetailError] = useState('');

  useEffect(() => {
    let alive = true;
    listGraphRuns()
      .then((rows) => { if (alive) setRuns(rows); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    listPapers()
      .then((rows) => { if (alive) setPapers(rows); })
      .catch(() => { /* names stay as ids */ });
    return () => { alive = false; };
  }, []);

  // Load the full record once per expanded run (cached across toggles).
  useEffect(() => {
    if (openRunId === null || details[openRunId]) return;
    let alive = true;
    setDetailError('');
    getGraphRun(openRunId)
      .then((record) => { if (alive) setDetails((prev) => ({ ...prev, [openRunId]: record })); })
      .catch((err) => { if (alive) setDetailError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, [openRunId, details]);

  const paperById = useMemo(() => new Map(papers.map((p) => [p.paper_id, p])), [papers]);
  const paperName = (paperId: string) => paperById.get(paperId)?.paper_name ?? paperId;

  const decisions = useMemo(
    () => [...new Set((runs ?? []).map((r) => r.decision).filter((d): d is string => !!d))].sort(),
    [runs],
  );
  const runPapers = useMemo(
    () => [...new Set((runs ?? []).map((r) => r.paper_id))],
    [runs],
  );

  const visible = runs === null ? null : runs.filter((run) =>
    (paperFilter === '' || run.paper_id === paperFilter)
    && (decisionFilter === '' || run.decision === decisionFilter)
    && (search.trim() === '' || (run.description ?? '').toLowerCase().includes(search.trim().toLowerCase())));

  return (
    <div className="section-wrap">
      <h2 className="section-title">Storico review</h2>
      <p className="section-description">
        Le run del grafo eseguite finora: espandi una run per il quadro
        completo — decisione, punteggi e flusso round per round.{' '}
        <Link to="/review-graph">← Review Graph</Link>
      </p>

      <div className="ri-toolbar">
        <select
          className="paper-form__select"
          aria-label="Filtra per paper"
          value={paperFilter}
          onChange={(e) => setPaperFilter(e.target.value)}
        >
          <option value="">tutti i paper</option>
          {runPapers.map((id) => <option key={id} value={id}>{paperName(id)}</option>)}
        </select>
        <select
          className="paper-form__select"
          aria-label="Filtra per decisione"
          value={decisionFilter}
          onChange={(e) => setDecisionFilter(e.target.value)}
        >
          <option value="">tutte le decisioni</option>
          {decisions.map((d) => <option key={d} value={d}>{d.replace('_', ' ')}</option>)}
        </select>
        <input
          className="paper-form__input"
          type="search"
          placeholder="cerca nella descrizione…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {error && <p className="paper-form__error">{error}</p>}
      {!error && visible === null && <p className="ri-empty">Caricamento…</p>}
      {visible !== null && visible.length === 0 && (
        <p className="ri-empty">Nessuna run corrisponde ai filtri.</p>
      )}

      {visible !== null && visible.map((run) => {
        const open = openRunId === run.run_id;
        return (
          <div key={run.run_id} className={`ri-run${open ? ' ri-run--open' : ''}`}>
            <button
              className="ri-run__head"
              type="button"
              aria-expanded={open}
              onClick={() => setOpenRunId(open ? null : run.run_id)}
            >
              <span className="ri-run__chevron">▸</span>
              <span className="ri-run__date">{formatTimestamp(run.timestamp)}</span>
              <span className="ri-run__paper" title={run.paper_id}>{paperName(run.paper_id)}</span>
              <DecisionBadge decision={run.decision} />
              <span className="ri-run__meta">
                meta {run.meta_overall_score ?? '—'} · {run.total_rounds}{run.max_rounds != null ? `/${run.max_rounds}` : ''} round
              </span>
            </button>
            {open && (
              details[run.run_id]
                ? <RunDetail record={details[run.run_id]} paper={paperById.get(run.paper_id) ?? null} />
                : <div className="ri-run__body">{detailError ? <p className="paper-form__error">{detailError}</p> : <p className="ri-empty">Caricamento…</p>}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
