/** Review Graph section — run the multi-agent review pipeline on a paper.
 *
 * "Configura review" opens a fullscreen modal: the pipeline graph on the left
 * (click a node to select it), the editor for the selected role on the right.
 * The GraphConfig mirrors domain/models/graph.py — one AgentConfig per role
 * (the N reviewers share the single reviewer config) plus num_reviewers and
 * max_rounds. No compile endpoint exists yet, so the config persists in
 * localStorage and will be shipped with "Lancia review". */
import { useEffect, useState } from 'react';
import { listModels } from '../api/client';
import type { AgentConfig, ContextMode, GraphConfig } from '../api/types';
import ActionCard from '../components/ActionCard';
import TemperatureSlider from '../components/TemperatureSlider';
import { useOptions } from '../components/useOptions';

const STORAGE_KEY = 'llm-review-2.graph-config';

const ROLES = ['reviewer', 'meta_reviewer', 'area_chair', 'author'] as const;
type RoleKey = (typeof ROLES)[number];

const ROLE_LABELS: Record<RoleKey, string> = {
  reviewer: 'Reviewer',
  meta_reviewer: 'Meta Reviewer',
  area_chair: 'Area Chair',
  author: 'Author',
};

const ROLE_ICONS: Record<RoleKey, string> = {
  reviewer: '🔬',
  meta_reviewer: '📋',
  area_chair: '🪑',
  author: '✍️',
};

const CONTEXT_MODES: ContextMode[] = ['none', 'full_context', 'bm25', 'embedding'];

function defaultAgent(contextMode: ContextMode = 'none'): AgentConfig {
  return {
    model: 'mock',
    temperature: 0.4,
    request_context: { context_mode: contextMode, retrieval_context_query: null },
  };
}

/** BE default (mock everywhere), with the reviewer reading the whole paper. */
function defaultConfig(): GraphConfig {
  return {
    reviewer: defaultAgent('full_context'),
    meta_reviewer: defaultAgent(),
    area_chair: defaultAgent(),
    author: defaultAgent(),
    num_reviewers: 3,
    max_rounds: 1,
  };
}

export function loadGraphConfig(): GraphConfig {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return { ...defaultConfig(), ...JSON.parse(stored) };
  } catch { /* corrupted/unavailable storage — fall through */ }
  return defaultConfig();
}

function saveGraphConfig(config: GraphConfig): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(config)); } catch { /* ignore */ }
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
  const { options: models, error: modelsError } = useOptions(listModels);
  const [config, setConfig] = useState<GraphConfig>(loadGraphConfig);
  const [selected, setSelected] = useState<RoleKey>('reviewer');
  const [savedNote, setSavedNote] = useState(false);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const agent = config[selected];

  function updateAgent(patch: Partial<AgentConfig>) {
    setSavedNote(false);
    setConfig((prev) => ({ ...prev, [selected]: { ...prev[selected], ...patch } }));
  }

  function updateContextMode(mode: ContextMode) {
    updateAgent({
      request_context: {
        context_mode: mode,
        retrieval_context_query: mode === 'bm25' || mode === 'embedding'
          ? agent.request_context.retrieval_context_query ?? ''
          : null,
      },
    });
  }

  function updateGlobal(patch: Partial<Pick<GraphConfig, 'num_reviewers' | 'max_rounds'>>) {
    setSavedNote(false);
    setConfig((prev) => ({ ...prev, ...patch }));
  }

  function onSave() {
    saveGraphConfig(config);
    setSavedNote(true);
  }

  function onReset() {
    setConfig(defaultConfig());
    setSavedNote(false);
  }

  const needsQuery = agent.request_context.context_mode === 'bm25'
    || agent.request_context.context_mode === 'embedding';

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
                  selected={selected === 'reviewer'}
                  onSelect={() => setSelected('reviewer')}
                />
              ))}
            </div>
            <div className="rg-arrow">→</div>
            <div className="rg-col">
              <GraphNode
                label={ROLE_LABELS.meta_reviewer}
                icon={ROLE_ICONS.meta_reviewer}
                selected={selected === 'meta_reviewer'}
                onSelect={() => setSelected('meta_reviewer')}
              />
            </div>
            <div className="rg-arrow">→</div>
            <div className="rg-col">
              <GraphNode
                label={ROLE_LABELS.area_chair}
                icon={ROLE_ICONS.area_chair}
                selected={selected === 'area_chair'}
                onSelect={() => setSelected('area_chair')}
              />
            </div>
            <div className="rg-arrow">→</div>
            <div className="rg-col">
              <GraphNode label="Decisione" icon="⚖" muted />
            </div>

            <div className="rg-loop">
              <span className="rg-loop__arrow">↺</span>
              <GraphNode
                label={ROLE_LABELS.author}
                icon={ROLE_ICONS.author}
                selected={selected === 'author'}
                onSelect={() => setSelected('author')}
              />
              <span className="rg-loop__note">revision loop · max {config.max_rounds} round</span>
            </div>
          </div>

          {/* ── Editor for the selected node ── */}
          <aside className="rg-editor">
            <h4 className="rg-editor__title">
              {ROLE_ICONS[selected]} {ROLE_LABELS[selected]}
              {selected === 'reviewer' && <span className="rg-editor__hint"> — config condivisa dai {config.num_reviewers} reviewer</span>}
            </h4>

            <label className="paper-form__label" htmlFor="rg-model">Modello</label>
            <select
              className="paper-form__select"
              id="rg-model"
              value={agent.model}
              onChange={(e) => updateAgent({ model: e.target.value })}
            >
              {modelsError && <option value="">Error loading</option>}
              {!modelsError && models.length === 0 && <option value="">Loading…</option>}
              {models.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>

            <label className="paper-form__label" htmlFor="rg-temperature">Temperature</label>
            <div className="rg-editor__slider">
              <TemperatureSlider
                id="rg-temperature"
                min={0}
                max={2}
                value={agent.temperature}
                onChange={(value) => updateAgent({ temperature: value })}
                inputClassName="ping-chat-model-bar__temperature"
                valueClassName="ping-chat-model-bar__temperature-value"
              />
            </div>

            <label className="paper-form__label" htmlFor="rg-context">Context mode</label>
            <select
              className="paper-form__select"
              id="rg-context"
              value={agent.request_context.context_mode}
              onChange={(e) => updateContextMode(e.target.value as ContextMode)}
            >
              {CONTEXT_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
            </select>

            {needsQuery && (
              <>
                <label className="paper-form__label" htmlFor="rg-query">Retrieval query</label>
                <input
                  className="paper-form__input"
                  id="rg-query"
                  type="text"
                  placeholder="query per il retrieval del contesto"
                  value={agent.request_context.retrieval_context_query ?? ''}
                  onChange={(e) => updateAgent({
                    request_context: { ...agent.request_context, retrieval_context_query: e.target.value },
                  })}
                />
              </>
            )}

            <div className="rg-editor__globals">
              <div>
                <label className="paper-form__label" htmlFor="rg-reviewers">N. reviewer</label>
                <input
                  className="paper-form__input rg-editor__number"
                  id="rg-reviewers"
                  type="number"
                  min={1}
                  max={9}
                  value={config.num_reviewers}
                  onChange={(e) => updateGlobal({ num_reviewers: Math.max(1, Math.min(9, Number(e.target.value) || 1)) })}
                />
              </div>
              <div>
                <label className="paper-form__label" htmlFor="rg-rounds">Max round</label>
                <input
                  className="paper-form__input rg-editor__number"
                  id="rg-rounds"
                  type="number"
                  min={1}
                  max={5}
                  value={config.max_rounds}
                  onChange={(e) => updateGlobal({ max_rounds: Math.max(1, Math.min(5, Number(e.target.value) || 1)) })}
                />
              </div>
            </div>

            <div className="rg-editor__actions">
              <button className="btn btn--primary" type="button" onClick={onSave}>Salva configurazione</button>
              <button className="btn btn--ghost btn--sm" type="button" onClick={onReset}>Ripristina default</button>
            </div>
            {savedNote && <p className="rg-editor__saved">Configurazione salvata — verrà usata da "Lancia review".</p>}
          </aside>
        </div>
      </div>
    </div>
  );
}

export default function ReviewGraph() {
  const [configureOpen, setConfigureOpen] = useState(false);

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
            Composizione del comitato: modelli, temperature e context mode per ruolo,
            numero di reviewer e round massimi.
          </>
        }
        actionLabel="Configura"
        onAction={() => setConfigureOpen(true)}
      />

      <ActionCard
        title="Lancia review"
        description={
          <>
            Esegui il grafo di review su un paper del catalogo con la configurazione
            scelta — in preparazione.
          </>
        }
        actionLabel="Lancia"
      />

      {configureOpen && <ConfigureReviewModal onClose={() => setConfigureOpen(false)} />}
    </div>
  );
}
