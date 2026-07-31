/** Review Graph section — run the multi-agent review pipeline on a paper.
 *
 * "Configura review" opens a fullscreen modal: graph-level settings on top
 * (paper, num reviewers, max rounds — the only shared knobs), the pipeline
 * graph below (click a node to open its editor), and the reusable
 * AgentConfigPanel on the side for the selected agent. Every reviewer has its
 * own AgentConfig; the config persists in localStorage. "Lancia review" maps
 * it onto the BE contract (one shared reviewer config, system_prompt as
 * string) and drives POST /graph/compile + /graph/invoke. */
import { useEffect, useState } from 'react';
import { ApiError, compileGraph, invokeGraph, listGraphRuns, listPapers } from '../api/client';
import type {
  AgentConfig, BackendAgentConfig, ContextMode, CreateGraphReviewRequest,
  GraphConfig, GraphReviewRecord, GraphReviewSummary, Paper,
} from '../api/types';
import ActionCard from '../components/ActionCard';
import AgentConfigPanel from '../components/AgentConfigPanel';
import InputMessagesPanel from '../components/InputMessagesPanel';

const STORAGE_KEY = 'llm-review-2.graph-config';

type SingleRole = 'meta_reviewer' | 'area_chair' | 'author';

/** A node selection: one of the reviewers (by index) or a single-instance role. */
type Selection = { role: 'reviewer'; index: number } | { role: SingleRole };

const ROLE_LABELS: Record<'reviewer' | SingleRole, string> = {
  reviewer: 'Reviewer',
  meta_reviewer: 'Meta Reviewer',
  area_chair: 'Area Chair',
  author: 'Author',
};

const ROLE_ICONS: Record<'reviewer' | SingleRole, string> = {
  reviewer: '🔬',
  meta_reviewer: '📋',
  area_chair: '🪑',
  author: '✍️',
};

function defaultAgent(contextMode: ContextMode = 'none'): AgentConfig {
  return {
    model: 'mock',
    temperature: 0.4,
    system_prompt: null,
    input_message: null,
    request_context: { context_mode: contextMode, retrieval_context_query: null },
  };
}

/** BE default (mock everywhere), with the reviewers reading the whole paper. */
function defaultConfig(): GraphConfig {
  return {
    paper_id: null,
    num_reviewers: 3,
    max_rounds: 1,
    input_messages: {},
    reviewers: Array.from({ length: 3 }, () => defaultAgent('full_context')),
    meta_reviewer: defaultAgent(),
    area_chair: defaultAgent(),
    author: defaultAgent(),
  };
}

/** Keep reviewers.length in sync with count: clone the last one to grow. */
function resizeReviewers(reviewers: AgentConfig[], count: number): AgentConfig[] {
  if (reviewers.length >= count) return reviewers.slice(0, count);
  const template = reviewers[reviewers.length - 1] ?? defaultAgent('full_context');
  return [
    ...reviewers,
    ...Array.from({ length: count - reviewers.length }, () => structuredClone(template)),
  ];
}


export function loadGraphConfig(): GraphConfig {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<GraphConfig> & { reviewer?: AgentConfig };
      const base = { ...defaultConfig(), ...parsed };
      // Migrate the legacy shape (single shared `reviewer`) to per-reviewer configs.
      if (!Array.isArray(parsed.reviewers)) {
        base.reviewers = Array.from(
          { length: base.num_reviewers },
          () => structuredClone(parsed.reviewer ?? defaultAgent('full_context')),
        );
      }
      base.reviewers = resizeReviewers(base.reviewers, base.num_reviewers);
      // Legacy shapes stored no input_messages (or the dropped round_messages array).
      if (typeof parsed.input_messages !== 'object' || Array.isArray(parsed.input_messages)) {
        base.input_messages = {};
      }
      return base;
    }
  } catch { /* corrupted/unavailable storage — fall through */ }
  return defaultConfig();
}

function saveGraphConfig(config: GraphConfig): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(config)); } catch { /* ignore */ }
}

/** FE AgentConfig -> BE AgentConfig: the JSON system prompt travels serialized. */
function toBackendAgent(agent: AgentConfig): BackendAgentConfig {
  return {
    model: agent.model,
    temperature: agent.temperature,
    system_prompt: agent.system_prompt ? JSON.stringify(agent.system_prompt) : '',
    request_context: agent.request_context,
  };
}

/** FE GraphConfig -> BE CreateGraphReviewRequest. The BE still shares ONE
 * reviewer config: the first reviewer acts as the committee template
 * (per-reviewer configs and input_messages ship when the BE aligns). */
function toBackendRequest(config: GraphConfig, description: string): CreateGraphReviewRequest {
  if (!config.paper_id) throw new Error('Nessun paper selezionato nella configurazione.');
  return {
    paper_id: config.paper_id,
    graph_config: {
      reviewer: toBackendAgent(config.reviewers[0] ?? defaultAgent('full_context')),
      meta_reviewer: toBackendAgent(config.meta_reviewer),
      area_chair: toBackendAgent(config.area_chair),
      author: toBackendAgent(config.author),
      num_reviewers: config.num_reviewers,
      max_rounds: config.max_rounds,
    },
    run_description: description,
  };
}

function GraphNode({ label, icon, selected, muted, onSelect }: {
  label: string;
  icon?: string;
  selected?: boolean;
  muted?: boolean;
  onSelect?: () => void;
}) {
  return (
    <button
      type="button"
      className={
        'rg-node' +
        (selected ? ' rg-node--selected' : '') +
        (muted ? ' rg-node--muted' : '')
      }
      disabled={!onSelect}
      onClick={onSelect}
    >
      {icon && <span className="rg-node__icon">{icon}</span>}
      <span className="rg-node__label">{label}</span>
    </button>
  );
}

function ConfigureReviewModal({ onClose }: { onClose: () => void }) {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [config, setConfig] = useState<GraphConfig>(loadGraphConfig);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [savedNote, setSavedNote] = useState(false);

  useEffect(() => {
    let alive = true;
    listPapers()
      .then((rows) => { if (alive) setPapers(rows); })
      .catch(() => { /* catalog unavailable — the select stays empty */ });
    return () => { alive = false; };
  }, []);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const agent: AgentConfig | null = selected === null
    ? null
    : selected.role === 'reviewer'
      ? config.reviewers[selected.index] ?? null
      : config[selected.role];

  /** Stable identity of the edited agent — remounts the panel on switch. */
  const keyOf = (sel: Selection) =>
    sel.role === 'reviewer' ? `reviewer-${sel.index}` : sel.role;
  const selectionKey = selected === null ? 'none' : keyOf(selected);

  const selectionTitle = selected === null
    ? ''
    : selected.role === 'reviewer'
      ? `${ROLE_ICONS.reviewer} Reviewer ${selected.index + 1}`
      : `${ROLE_ICONS[selected.role]} ${ROLE_LABELS[selected.role]}`;

  function updateAgent(patch: Partial<AgentConfig>) {
    if (selected === null) return;
    setSavedNote(false);
    setConfig((prev) => {
      if (selected.role === 'reviewer') {
        const reviewers = prev.reviewers.map(
          (r, i) => (i === selected.index ? { ...r, ...patch } : r),
        );
        return { ...prev, reviewers };
      }
      return { ...prev, [selected.role]: { ...prev[selected.role], ...patch } };
    });
  }

  function updateGlobal(patch: Partial<Pick<GraphConfig, 'paper_id' | 'num_reviewers' | 'max_rounds'>>) {
    setSavedNote(false);
    setConfig((prev) => {
      const next = { ...prev, ...patch };
      next.reviewers = resizeReviewers(next.reviewers, next.num_reviewers);
      return next;
    });
    // Drop the selection if it points to a removed reviewer.
    if (patch.num_reviewers !== undefined) {
      setSelected((sel) =>
        sel?.role === 'reviewer' && sel.index >= patch.num_reviewers! ? null : sel);
    }
  }

  function updateInputMessages(messages: Record<string, string[]>) {
    setSavedNote(false);
    setConfig((prev) => ({ ...prev, input_messages: messages }));
  }

  function onSave() {
    saveGraphConfig(config);
    setSavedNote(true);
  }

  function onReset() {
    setConfig(defaultConfig());
    setSelected(null);
    setSavedNote(false);
  }

  const isSelected = (sel: Selection) => selectionKey === keyOf(sel);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--full"
        role="dialog"
        aria-modal="true"
        aria-labelledby="configure-review-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="configure-review-title">Configura review</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        {/* ── Graph-level settings: the only shared knobs ── */}
        <div className="rg-globals">
          <div className="rg-globals__field rg-globals__field--grow">
            <label className="paper-form__label" htmlFor="rg-paper">Paper</label>
            <select
              className="paper-form__select"
              id="rg-paper"
              value={config.paper_id ?? ''}
              onChange={(e) => updateGlobal({ paper_id: e.target.value || null })}
            >
              <option value="">— seleziona un paper —</option>
              {papers.map((p) => (
                <option key={p.paper_id} value={p.paper_id}>{p.paper_name} ({p.paper_id})</option>
              ))}
            </select>
          </div>
          <div className="rg-globals__field">
            <label className="paper-form__label" htmlFor="rg-reviewers">N. reviewer</label>
            <input
              className="paper-form__input rg-globals__number"
              id="rg-reviewers"
              type="number"
              min={1}
              max={9}
              value={config.num_reviewers}
              onChange={(e) => updateGlobal({ num_reviewers: Math.max(1, Math.min(9, Number(e.target.value) || 1)) })}
            />
          </div>
          <div className="rg-globals__field">
            <label className="paper-form__label" htmlFor="rg-rounds">Max round</label>
            <input
              className="paper-form__input rg-globals__number"
              id="rg-rounds"
              type="number"
              min={1}
              max={5}
              value={config.max_rounds}
              onChange={(e) => updateGlobal({ max_rounds: Math.max(1, Math.min(5, Number(e.target.value) || 1)) })}
            />
          </div>
          <div className="rg-globals__actions">
            <button className="btn btn--primary" type="button" onClick={onSave}>Salva configurazione</button>
            <button className="btn btn--ghost btn--sm" type="button" onClick={onReset}>Ripristina default</button>
          </div>
        </div>
        {savedNote && <p className="rg-saved">Configurazione salvata — verrà usata da "Lancia review".</p>}

        <div className="rg-layout">
          {/* ── Pipeline graph ── */}
          <div className="rg-graph">
            <div className="rg-col">
              <GraphNode label="Paper" icon="▤" muted />
            </div>
            <div className="rg-arrow">→</div>
            <div className="rg-col rg-col--stack">
              {Array.from({ length: config.num_reviewers }, (_, i) => (
                <GraphNode
                  key={i}
                  label={`Reviewer ${i + 1}`}
                  icon={ROLE_ICONS.reviewer}
                  selected={isSelected({ role: 'reviewer', index: i })}
                  onSelect={() => setSelected({ role: 'reviewer', index: i })}
                />
              ))}
            </div>
            <div className="rg-arrow">→</div>
            <div className="rg-col">
              <GraphNode
                label={ROLE_LABELS.meta_reviewer}
                icon={ROLE_ICONS.meta_reviewer}
                selected={isSelected({ role: 'meta_reviewer' })}
                onSelect={() => setSelected({ role: 'meta_reviewer' })}
              />
            </div>
            <div className="rg-arrow">→</div>
            <div className="rg-col">
              <GraphNode
                label={ROLE_LABELS.area_chair}
                icon={ROLE_ICONS.area_chair}
                selected={isSelected({ role: 'area_chair' })}
                onSelect={() => setSelected({ role: 'area_chair' })}
              />
            </div>

            <div className="rg-loop">
              <span className="rg-loop__arrow">↺</span>
              <GraphNode
                label={ROLE_LABELS.author}
                icon={ROLE_ICONS.author}
                selected={isSelected({ role: 'author' })}
                onSelect={() => setSelected({ role: 'author' })}
              />
              <span className="rg-loop__note">
                L'Author riceve le review e revisiona il paper: il ciclo si ripete
                fino a max {config.max_rounds} round, poi l'Area Chair emette la
                decisione finale (accept/reject).
              </span>
            </div>
          </div>

          {/* ── Editor for the selected node (reusable panels) ── */}
          <aside className="rg-editor">
            {agent === null ? (
              <p className="rg-editor__placeholder">
                Clicca un agente nel grafo per configurarlo.
              </p>
            ) : (
              <>
                <AgentConfigPanel
                  key={selectionKey}
                  idPrefix={`rg-${selectionKey}`}
                  title={selectionTitle}
                  agent={agent}
                  onChange={updateAgent}
                  showInputMessage={false}
                />
                <InputMessagesPanel
                  idPrefix={`rg-messages-${selectionKey}`}
                  agentKey={selectionKey}
                  rounds={config.max_rounds}
                  messages={config.input_messages}
                  onChange={updateInputMessages}
                />
              </>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

type LaunchPhase = 'idle' | 'compiling' | 'running' | 'done' | 'error';

const PHASE_NOTES: Record<LaunchPhase, string> = {
  idle: '',
  compiling: 'Compilo il grafo e costruisco gli agenti…',
  running: 'Review in corso — reviewer, meta reviewer, area chair…',
  done: 'Review completata e salvata nello storico.',
  error: '',
};

function LaunchReviewModal({ onClose }: { onClose: () => void }) {
  const [config] = useState<GraphConfig>(loadGraphConfig);
  const [description, setDescription] = useState('');
  const [phase, setPhase] = useState<LaunchPhase>('idle');
  const [error, setError] = useState('');
  const [record, setRecord] = useState<GraphReviewRecord | null>(null);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const busy = phase === 'compiling' || phase === 'running';
  const models = [
    ...config.reviewers.map((r) => r.model),
    config.meta_reviewer.model,
    config.area_chair.model,
    config.author.model,
  ];

  async function onLaunch() {
    setError('');
    setRecord(null);
    try {
      const request = toBackendRequest(config, description);
      setPhase('compiling');
      await compileGraph(request);
      setPhase('running');
      setRecord(await invokeGraph(request));
      setPhase('done');
    } catch (err) {
      setPhase('error');
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="launch-review-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="launch-review-title">Lancia review</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        {!config.paper_id ? (
          <p className="paper-form__error">
            Nessun paper selezionato: aprilo da "Configura review" e scegli un paper del catalogo.
          </p>
        ) : (
          <>
            <dl className="rg-launch__summary">
              <dt>Paper</dt><dd className="paper-list__id">{config.paper_id}</dd>
              <dt>Comitato</dt><dd>{config.num_reviewers} reviewer · max {config.max_rounds} round</dd>
              <dt>Modelli</dt><dd>{[...new Set(models)].join(', ')}</dd>
            </dl>

            <label className="paper-form__label" htmlFor="rg-launch-description">Descrizione run (opzionale)</label>
            <input
              className="paper-form__input"
              id="rg-launch-description"
              type="text"
              placeholder="es. baseline mock, 3 reviewer"
              value={description}
              disabled={busy}
              onChange={(e) => setDescription(e.target.value)}
            />

            <div className="rg-launch__actions">
              <button className="btn btn--primary" type="button" disabled={busy} onClick={onLaunch}>
                {busy ? 'In esecuzione…' : 'Lancia'}
              </button>
              {PHASE_NOTES[phase] && <span className="rg-launch__note">{PHASE_NOTES[phase]}</span>}
            </div>

            {error && <p className="paper-form__error">{error}</p>}

            {record && (
              <div className="rg-launch__result">
                <p><strong>Decisione:</strong> {record.decision || '—'} · <strong>round:</strong> {record.total_rounds}</p>
                <p><strong>run_id:</strong> <span className="paper-list__id">{record.run_id}</span></p>
                <p className="rg-launch__hint">I dettagli completi sono in "Storico review".</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}


function RunHistoryModal({ onClose }: { onClose: () => void }) {
  const [runs, setRuns] = useState<GraphReviewSummary[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    listGraphRuns()
      .then((rows) => { if (alive) setRuns(rows); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, []);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-history-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="run-history-title">Storico review</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        {error && <p className="paper-form__error">{error}</p>}
        {!error && runs === null && <p className="paper-list__empty">Caricamento…</p>}
        {runs !== null && runs.length === 0 && (
          <p className="paper-list__empty">Nessuna run nel database.</p>
        )}
        {runs !== null && runs.length > 0 && (
          <div className="paper-list__scroll">
            <table className="paper-list">
              <thead>
                <tr>
                  <th>run_id</th>
                  <th>timestamp</th>
                  <th>paper</th>
                  <th>decision</th>
                  <th>round</th>
                  <th>descrizione</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id}>
                    <td className="paper-list__id">{run.run_id}</td>
                    <td>{run.timestamp}</td>
                    <td className="paper-list__id">{run.paper_id}</td>
                    <td>{run.decision || '—'}</td>
                    <td>{run.total_rounds}</td>
                    <td className="paper-list__desc">{run.run_description || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ReviewGraph() {
  const [configureOpen, setConfigureOpen] = useState(false);
  const [launchOpen, setLaunchOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  return (
    <div className="section-wrap">
      <h2 className="section-title">Review Graph</h2>
      <p className="section-description">
        Configura il comitato di review e lancia il grafo multi-agente su un paper del catalogo.
      </p>

      <ActionCard
        title="Configura review"
        description={
          <>
            Paper, numero di reviewer e round massimi a livello di grafo; modello,
            temperature, context mode e system prompt per ogni singolo agente.
          </>
        }
        actionLabel="Configura"
        onAction={() => setConfigureOpen(true)}
      />

      <ActionCard
        title="Lancia review"
        description={
          <>
            Esegui il grafo di review sul paper scelto con la configurazione
            salvata: compila il grafo e lancia i round del comitato.
          </>
        }
        actionLabel="Lancia"
        onAction={() => setLaunchOpen(true)}
      />

      <ActionCard
        title="Storico review"
        description={<>Le run del grafo eseguite finora: esito, round e paper (dati dal DB).</>}
        actionLabel="Apri"
        onAction={() => setHistoryOpen(true)}
      />

      <ActionCard
        title="Open Review Comparator"
        description={
          <>
            Confronta le review del grafo con quelle umane di OpenReview per lo stesso
            paper — in preparazione.
          </>
        }
        actionLabel="Confronta"
      />

      {configureOpen && <ConfigureReviewModal onClose={() => setConfigureOpen(false)} />}
      {launchOpen && <LaunchReviewModal onClose={() => setLaunchOpen(false)} />}
      {historyOpen && <RunHistoryModal onClose={() => setHistoryOpen(false)} />}
    </div>
  );
}
