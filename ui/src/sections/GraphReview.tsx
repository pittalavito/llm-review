/** Review Graph section — run the multi-agent review pipeline on a paper.
 *
 * "Configura review" opens a fullscreen modal: graph-level settings on top
 * (paper, num reviewers, max rounds — the only shared knobs), the pipeline
 * graph below (click a node to open its editor), and the reusable
 * AgentConfigPanel on the side for the selected agent. Every reviewer has its
 * own AgentConfig; the config persists in localStorage. "Lancia review" maps
 * it onto the BE contract (per-reviewer configs, prompt resolved on the BE
 * from each agent's prompt_preset_id) and drives POST /graph/compile + /graph/invoke. */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, compileGraph, getGraphConfig, invokeGraph, listPapers } from '../api/client';
import type {
  AgentConfig, BackendAgentConfig, ContextMode, CreateGraphReviewRequest,
  GraphConfig, GraphReviewConfig, GraphReviewRecord, Paper,
} from '../api/types';
import ActionCard from '../components/ActionCard';
import AgentConfigPanel from '../components/AgentConfigPanel';

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

const ROLE_TO_BE: Record<'reviewer' | SingleRole, string> = {
  reviewer: 'reviewer',
  meta_reviewer: 'meta_reviewer',
  area_chair: 'area_chair',
  author: 'author_agent',
};

function defaultAgent(contextMode: ContextMode = 'none'): AgentConfig {
  return {
    model: 'mock',
    temperature: 0.4,
    prompt_preset_id: null,
    input_message: null,
    request_context: { context_mode: contextMode, retrieval_context_query: null },
  };
}

/** Drop the legacy prompt fields from stored configs (JSON system_prompt and
 * the pre-preset system_prompt_request), keeping the preset id when one was
 * selected — so older localStorage keeps loading. */
function sanitizeAgent(agent: AgentConfig & { system_prompt?: unknown; system_prompt_request?: { preset_id?: unknown } | null }): AgentConfig {
  const { system_prompt: _legacy, system_prompt_request: legacyRequest, ...rest } = agent;
  const legacyPresetId = typeof legacyRequest?.preset_id === 'number' ? legacyRequest.preset_id : null;
  const presetId = typeof rest.prompt_preset_id === 'number' ? rest.prompt_preset_id : legacyPresetId;
  return { ...defaultAgent(), ...rest, prompt_preset_id: presetId };
}

/** BE default (mock everywhere), with the reviewers reading the whole paper. */
function defaultConfig(): GraphConfig {
  return {
    paper_id: null,
    num_reviewers: 3,
    max_rounds: 1,
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
      base.reviewers = resizeReviewers(base.reviewers, base.num_reviewers).map(sanitizeAgent);
      base.meta_reviewer = sanitizeAgent(base.meta_reviewer);
      base.area_chair = sanitizeAgent(base.area_chair);
      base.author = sanitizeAgent(base.author);
      return base;
    }
  } catch { /* corrupted/unavailable storage — fall through */ }
  return defaultConfig();
}

function saveGraphConfig(config: GraphConfig): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(config)); } catch { /* ignore */ }
}

/** FE AgentConfig -> BE AgentConfig: the prompt travels as the preset id; the
 * BE resolves the preset and builds the actual string. The BE requires an id,
 * so an unselected preset blocks the launch with a clear message. */
function toBackendAgent(agent: AgentConfig): BackendAgentConfig {
  if (agent.prompt_preset_id === null) {
    throw new Error('Ogni agente deve avere un preset di system prompt selezionato in "Configura review".');
  }
  return {
    model: agent.model,
    temperature: agent.temperature,
    prompt_preset_id: agent.prompt_preset_id,
    request_context: agent.request_context,
  };
}

/** FE GraphConfig -> BE CreateGraphReviewRequest: reviewers map 1:1 (the BE
 * derives the committee size from the list). */
function toBackendRequest(config: GraphConfig, description: string): CreateGraphReviewRequest {
  if (!config.paper_id) throw new Error('Nessun paper selezionato nella configurazione.');
  return {
    paper_id: config.paper_id,
    graph_config: {
      reviewers: config.reviewers.map(toBackendAgent),
      meta_reviewer: toBackendAgent(config.meta_reviewer),
      area_chair: toBackendAgent(config.area_chair),
      author: toBackendAgent(config.author),
      max_rounds: config.max_rounds,
    },
    description,
  };
}

/** BE AgentConfig -> FE AgentConfig (input_message is FE-only, reset to null).
 * The BE's default config uses 0 as a placeholder preset id — map it to the
 * FE's "not chosen yet" null. */
function fromBackendAgent(agent: BackendAgentConfig): AgentConfig {
  return {
    model: agent.model,
    temperature: agent.temperature,
    prompt_preset_id: agent.prompt_preset_id > 0 ? agent.prompt_preset_id : null,
    input_message: null,
    request_context: agent.request_context,
  };
}

/** BE GraphReviewConfig -> FE GraphConfig. The BE has no paper notion in the
 * config: the paper selection stays whatever the FE already had. */
function fromBackendConfig(graphConfig: GraphReviewConfig, paperId: string | null): GraphConfig {
  const reviewers = graphConfig.reviewers.map(fromBackendAgent);
  return {
    paper_id: paperId,
    num_reviewers: reviewers.length,
    max_rounds: graphConfig.max_rounds,
    reviewers,
    meta_reviewer: fromBackendAgent(graphConfig.meta_reviewer),
    area_chair: fromBackendAgent(graphConfig.area_chair),
    author: fromBackendAgent(graphConfig.author),
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
  const [configSource, setConfigSource] = useState<'backend' | 'local'>('local');
  const [compiling, setCompiling] = useState(false);
  const [compileNote, setCompileNote] = useState('');
  const [compileError, setCompileError] = useState('');

  useEffect(() => {
    let alive = true;
    listPapers()
      .then((rows) => { if (alive) setPapers(rows); })
      .catch(() => { /* catalog unavailable — the select stays empty */ });
    return () => { alive = false; };
  }, []);

  // On open: the graph configuration currently loaded on the BE (its default
  // before any compile). The locally stored config stays as offline fallback.
  useEffect(() => {
    let alive = true;
    getGraphConfig()
      .then((response) => {
        if (!alive) return;
        setConfig((prev) => fromBackendConfig(response.graph_config, prev.paper_id));
        setConfigSource('backend');
      })
      .catch(() => { /* BE unreachable — keep the localStorage config */ });
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
    setCompileNote('');
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
    setCompileNote('');
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

  /** Push the config to the BE: POST /graph/compile builds the agents and
   * loads the graph. On success it is also saved locally for "Lancia review". */
  async function onCompile() {
    setCompileError('');
    setCompileNote('');
    setCompiling(true);
    try {
      const request = toBackendRequest(config, '');
      await compileGraph(request);
      saveGraphConfig(config);
      setCompileNote('Grafo compilato ✓ — configurazione caricata sul backend e salvata.');
    } catch (err) {
      setCompileError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setCompiling(false);
    }
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
            <button className="btn btn--primary" type="button" disabled={compiling || !config.paper_id} onClick={onCompile}>
              {compiling ? 'Compilo…' : 'Compila grafo'}
            </button>
          </div>
        </div>
        {configSource === 'backend' && !compileNote && !compileError && (
          <p className="rg-saved">Configurazione caricata dal backend{config.paper_id ? '' : ' — seleziona un paper per compilare'}.</p>
        )}
        {compileNote && <p className="rg-saved">{compileNote}</p>}
        {compileError && <p className="paper-form__error">{compileError}</p>}

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
              <AgentConfigPanel
                key={selectionKey}
                idPrefix={`rg-${selectionKey}`}
                title={selectionTitle}
                agentRole={ROLE_TO_BE[selected!.role]}
                agent={agent}
                onChange={updateAgent}
                showInputMessage={false}
              />
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

type LaunchPhase = 'idle' | 'running' | 'done' | 'error';

const PHASE_NOTES: Record<LaunchPhase, string> = {
  idle: '',
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

  const busy = phase === 'running';
  const models = [
    ...config.reviewers.map((r) => r.model),
    config.meta_reviewer.model,
    config.area_chair.model,
    config.author.model,
  ];

  /** "Reviewer 2: preset #4" — one row per agent with a selected preset. */
  const promptSummary = [
    ...config.reviewers.map((r, i) => [`Reviewer ${i + 1}`, r.prompt_preset_id] as const),
    ['Meta Reviewer', config.meta_reviewer.prompt_preset_id] as const,
    ['Area Chair', config.area_chair.prompt_preset_id] as const,
    ['Author', config.author.prompt_preset_id] as const,
  ]
    .filter(([, presetId]) => presetId !== null)
    .map(([label, presetId]) => `${label}: preset #${presetId}`);

  /** Invoke only: the graph must already be compiled from "Configura review". */
  async function onLaunch() {
    if (phase === 'running' || phase === 'done') return;
    setError('');
    setRecord(null);
    try {
      const request = toBackendRequest(config, description);
      setPhase('running');
      setRecord(await invokeGraph(request));
      setPhase('done');
    } catch (err) {
      setPhase('error');
      const message = err instanceof ApiError ? err.message : String(err);
      setError(`${message} — se il grafo non è stato compilato, apri "Configura review" e premi "Compila grafo".`);
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
              <dt>Prompt</dt>
              <dd>
                {promptSummary.length === 0
                  ? 'nessun prompt dal registry'
                  : promptSummary.map((row) => <div key={row}>{row}</div>)}
              </dd>
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
              {/* Once done the button stays disabled: no accidental double invoke —
                  close and reopen the modal to launch another run. */}
              <button className="btn btn--primary" type="button" disabled={busy || phase === 'done'} onClick={onLaunch}>
                {busy ? 'In esecuzione…' : phase === 'done' ? 'Review completata ✓' : 'Lancia'}
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


export default function GraphReview() {
  const navigate = useNavigate();
  const [configureOpen, setConfigureOpen] = useState(false);
  const [launchOpen, setLaunchOpen] = useState(false);

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
        description={
          <>
            Le run del grafo eseguite finora: decisione, punteggi per reviewer e
            flusso round per round, con filtri per paper e decisione.
          </>
        }
        actionLabel="Apri"
        onAction={() => navigate('/review-graph/storico')}
      />

      <ActionCard
        title="Confronto con OpenReview"
        description={
          <>
            La run del grafo a fianco delle review umane: verdetti, rating a
            confronto, sub-score e testi campo per campo.
          </>
        }
        actionLabel="Confronta"
        onAction={() => navigate('/review-graph/confronto')}
      />

      {configureOpen && <ConfigureReviewModal onClose={() => setConfigureOpen(false)} />}
      {launchOpen && <LaunchReviewModal onClose={() => setLaunchOpen(false)} />}
    </div>
  );
}
