/**
 * RunCompare — dedicated page (/review-graph/confronto): run-level dashboard
 * comparing one graph run against the paper's real OpenReview reviews.
 * Verdict cards on top (decision match, mean rating / confidence deltas),
 * then the rating dumbbell per reviewer, the paired sub-score bars, the
 * meta-score trend across the paper's runs, and the per-field text
 * comparison (CompareView) as drill-down per role.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError, getGraphRun, getOpenReviewData, listGraphRuns, listPapers } from '../api/client';
import type { GraphReviewRecord, GraphReviewSummary, OpenReviewItem, Paper } from '../api/types';
import CompareView from '../components/CompareView';
import { ChartLegend, DumbbellChart, PairedBars, TrendChart } from '../components/charts';
import {
  finalReviewers, formatNum, humanAreaChair, humanMeta, humanReviewers,
  isAccept, mean, payloadNum, round1,
} from '../components/runMetrics';

function delta(graph: number | null, human: number | null): string | null {
  if (graph === null || human === null) return null;
  const d = round1(graph - human);
  return `${d > 0 ? '+' : ''}${d}`;
}

function Verdicts({ record, humans }: { record: GraphReviewRecord; humans: OpenReviewItem[] }) {
  const graphAccept = isAccept(record.decision);
  const humanDecision = humanAreaChair(humans)?.decision ?? null;
  const humanAccept = isAccept(humanDecision);
  const match = graphAccept !== null && humanAccept !== null ? graphAccept === humanAccept : null;

  const graphRatings = finalReviewers(record).map((r) => payloadNum(r.response_payload, 'rating'));
  const humanRatings = humanReviewers(humans).map((h) => h.rating ?? null);
  const graphMeanRating = mean(graphRatings);
  const humanMeanRating = mean(humanRatings);

  const graphConf = mean(finalReviewers(record).map((r) => payloadNum(r.response_payload, 'confidence')));
  const humanConf = mean(humanReviewers(humans).map((h) => h.confidence ?? null));

  return (
    <div className="ri-verdicts">
      <div className={`ri-verdict${match === null ? '' : match ? ' ri-verdict--ok' : ' ri-verdict--ko'}`}>
        <span className="ri-verdict__label">Decisione (accept vs non-accept)</span>
        <span className="ri-verdict__value">{match === null ? '—' : match ? '✓ Coincide' : '✗ Diverge'}</span>
        <span className="ri-verdict__hint">grafo: {(record.decision ?? '—').replace('_', ' ')} · umani: {humanDecision ?? '—'}</span>
      </div>
      <div className="ri-verdict">
        <span className="ri-verdict__label">Rating medio (grafo vs umani)</span>
        <span className="ri-verdict__value">
          {formatNum(graphMeanRating)} vs {formatNum(humanMeanRating)}{' '}
          <span className="ri-verdict__delta">{delta(graphMeanRating, humanMeanRating) ?? ''}</span>
        </span>
        <span className="ri-verdict__hint">scala 1–10</span>
      </div>
      <div className="ri-verdict">
        <span className="ri-verdict__label">Confidence media (grafo vs umani)</span>
        <span className="ri-verdict__value">
          {formatNum(graphConf)} vs {formatNum(humanConf)}{' '}
          <span className="ri-verdict__delta">{delta(graphConf, humanConf) ?? ''}</span>
        </span>
        <span className="ri-verdict__hint">scala 1–5</span>
      </div>
    </div>
  );
}

function Dashboard({ record, humans, paperRuns }: {
  record: GraphReviewRecord;
  humans: OpenReviewItem[];
  paperRuns: GraphReviewSummary[];
}) {
  const graphReviewers = finalReviewers(record);
  const humanRevs = humanReviewers(humans);

  const ratingRows = Array.from({ length: Math.max(graphReviewers.length, humanRevs.length) }, (_, i) => ({
    label: `R${i + 1}`,
    graph: graphReviewers[i] ? payloadNum(graphReviewers[i].response_payload, 'rating') : null,
    human: humanRevs[i]?.rating ?? null,
  })).filter((row) => row.graph !== null || row.human !== null);
  const meanRow = {
    label: 'Media',
    graph: mean(ratingRows.map((r) => r.graph)),
    human: mean(ratingRows.map((r) => r.human)),
  };
  const roundedMean = {
    label: meanRow.label,
    graph: meanRow.graph === null ? null : round1(meanRow.graph),
    human: meanRow.human === null ? null : round1(meanRow.human),
  };

  const sub = (key: 'soundness' | 'presentation' | 'contribution') => ({
    label: key,
    graph: mean(graphReviewers.map((r) => payloadNum(r.response_payload, key))),
    human: mean(humanRevs.map((h) => h[key] ?? null)),
  });
  const subGroups = (['soundness', 'presentation', 'contribution'] as const).map((key) => {
    const g = sub(key);
    return {
      label: g.label,
      graph: g.graph === null ? null : round1(g.graph),
      human: g.human === null ? null : round1(g.human),
    };
  });
  const humanHasSubscores = subGroups.some((g) => g.human !== null);

  const metaGroups = [{
    label: 'overall score',
    graph: payloadNum(record.meta_review_response ?? undefined, 'overall_score'),
    human: humanMeta(humans)?.overall_score ?? null,
  }];
  const humanMetaScore = metaGroups[0].human;

  const trendPoints = paperRuns
    .filter((r) => r.meta_overall_score != null)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .map((r) => ({ label: `${r.timestamp}${r.description ? ` — ${r.description}` : ''}`, value: r.meta_overall_score! }));

  return (
    <>
      <Verdicts record={record} humans={humans} />
      <ChartLegend />

      <div className="ri-block">
        <p className="ri-chart-title">Rating per reviewer <em>(ultimo round, 1–10; il segmento è il disaccordo)</em></p>
        <DumbbellChart rows={[...ratingRows, roundedMean]} min={1} max={10} />
      </div>

      <div className="ri-block">
        <p className="ri-chart-title">Sub-score medi a confronto <em>(1–4)</em></p>
        <PairedBars groups={subGroups} max={4} />
        {!humanHasSubscores && (
          <p className="ri-note">Le review umane di questo paper non hanno sub-score (form senza soundness/presentation/contribution).</p>
        )}
      </div>

      <div className="ri-block">
        <p className="ri-chart-title">Meta review <em>(overall score, 1–10)</em></p>
        <PairedBars groups={metaGroups} max={10} />
      </div>

      {trendPoints.length > 0 && (
        <div className="ri-block">
          <p className="ri-chart-title">Trend del meta score nelle run di questo paper <em>(riga tratteggiata = umani)</em></p>
          <TrendChart points={trendPoints} refValue={humanMetaScore} refLabel="umani" max={10} />
        </div>
      )}

      <p className="ri-chart-title">Confronto campo per campo</p>
      {graphReviewers.map((rev, i) => (
        <details key={`rev-${i}`} className="ri-details">
          <summary>🔬 Reviewer {rev.agent_index ?? i + 1} — testo e punteggi vs tutti gli umani</summary>
          <CompareView agent={rev} humans={humanRevs} />
        </details>
      ))}
      {record.agent_records?.filter((r) => r.agent_role === 'meta_reviewer').slice(-1).map((meta) => (
        <details key="meta" className="ri-details">
          <summary>📋 Meta reviewer</summary>
          <CompareView agent={meta} humans={humans.filter((h) => h.reviewer_type === 'meta_reviewer')} />
        </details>
      ))}
      {record.agent_records?.filter((r) => r.agent_role === 'area_chair').slice(-1).map((chair) => (
        <details key="chair" className="ri-details">
          <summary>🪑 Area chair</summary>
          <CompareView agent={chair} humans={humans.filter((h) => h.reviewer_type === 'area_chair')} />
        </details>
      ))}
    </>
  );
}

export default function RunCompare() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [runs, setRuns] = useState<GraphReviewSummary[]>([]);
  const [record, setRecord] = useState<GraphReviewRecord | null>(null);
  const [humans, setHumans] = useState<OpenReviewItem[] | null>(null);
  const [error, setError] = useState('');

  const paperId = searchParams.get('paper') ?? '';
  const runId = searchParams.get('run') ?? '';

  useEffect(() => {
    let alive = true;
    Promise.all([listPapers(), listGraphRuns()])
      .then(([paperRows, runRows]) => {
        if (!alive) return;
        setPapers(paperRows.filter((p) => p.paper_type?.toLowerCase() === 'open_review'));
        setRuns(runRows);
      })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, []);

  const paperRuns = useMemo(
    () => runs.filter((r) => r.paper_id === paperId),
    [runs, paperId],
  );

  useEffect(() => {
    if (!paperId || !runId) {
      setRecord(null);
      setHumans(null);
      return;
    }
    let alive = true;
    setRecord(null);
    setHumans(null);
    setError('');
    Promise.all([getGraphRun(runId), getOpenReviewData(paperId)])
      .then(([rec, items]) => {
        if (!alive) return;
        setRecord(rec);
        setHumans(items);
      })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, [paperId, runId]);

  function selectPaper(id: string) {
    const next = new URLSearchParams();
    if (id) next.set('paper', id);
    setSearchParams(next);
  }

  function selectRun(id: string) {
    const next = new URLSearchParams(searchParams);
    if (id) next.set('run', id); else next.delete('run');
    setSearchParams(next);
  }

  return (
    <div className="section-wrap">
      <h2 className="section-title">Confronto con OpenReview</h2>
      <p className="section-description">
        Una run del grafo a fianco delle review umane dello stesso paper:
        verdetti, punteggi e testi.{' '}
        <Link to="/review-graph/storico">← Storico review</Link>
      </p>

      <div className="ri-toolbar">
        <select
          className="paper-form__select"
          aria-label="Paper"
          value={paperId}
          onChange={(e) => selectPaper(e.target.value)}
        >
          <option value="">— scegli un paper OpenReview —</option>
          {papers.map((p) => <option key={p.paper_id} value={p.paper_id}>{p.paper_name}</option>)}
        </select>
        <select
          className="paper-form__select"
          aria-label="Run"
          value={runId}
          disabled={!paperId}
          onChange={(e) => selectRun(e.target.value)}
        >
          <option value="">{paperId ? (paperRuns.length ? '— scegli una run —' : 'nessuna run per questo paper') : '— prima il paper —'}</option>
          {paperRuns.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.timestamp}{r.description ? ` — ${r.description}` : ''}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="paper-form__error">{error}</p>}
      {!error && paperId && runId && (record === null || humans === null) && <p className="ri-empty">Caricamento…</p>}
      {!error && (!paperId || !runId) && (
        <p className="ri-empty">Scegli paper e run per vedere il confronto.</p>
      )}
      {record !== null && humans !== null && (
        humans.length === 0
          ? <p className="ri-empty">Nessuna review OpenReview salvata per questo paper.</p>
          : <Dashboard record={record} humans={humans} paperRuns={paperRuns} />
      )}
    </div>
  );
}
