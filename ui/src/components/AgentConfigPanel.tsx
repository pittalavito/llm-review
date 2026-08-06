/**
 * AgentConfigPanel — standalone editor for a single AgentConfig.
 *
 * Section-agnostic on purpose: the Review Graph mounts it next to the pipeline
 * graph today, other sections can reuse it as-is. It owns the model catalog and
 * prompt-registry fetches; the parent owns the AgentConfig value and receives
 * patches via onChange. Remount it (React key) when the edited agent switches,
 * so the local preview state resets with it.
 *
 * The system prompt is preset-only: the agent carries a prompt_preset_id and
 * the user picks a saved preset of the role (base version + instructions
 * bundled, managed in the Prompt section), previewing the exact composed
 * string via /prompts/presets/preview — the bundle's content never shows up
 * as editable controls in this panel.
 */
import { useEffect, useState } from 'react';
import { listInstructions, listModels, listPresets, listPromptsByRole } from '../api/client';
import type { AgentConfig, ContextMode, PromptInstruction, PromptVersion, SystemPromptPreset } from '../api/types';
import PromptPreviewModal from './PromptPreviewModal';
import TemperatureSlider from './TemperatureSlider';
import { useOptions } from './useOptions';

const CONTEXT_MODES: ContextMode[] = ['none', 'full_context', 'bm25', 'embedding'];

interface AgentConfigPanelProps {
  /** Panel heading, e.g. "🔬 Reviewer 2". */
  title: string;
  /** Optional muted note next to the title. */
  hint?: string;
  /** BE role of the edited agent ('reviewer', 'meta_reviewer', …) — selects
   * which prompt versions and instructions the composer offers. */
  agentRole: string;
  agent: AgentConfig;
  onChange: (patch: Partial<AgentConfig>) => void;
  /** Prefix for input ids, to keep labels unique per mounted panel. */
  idPrefix?: string;
  /** Hide the input message field where it is not relevant yet (default shown). */
  showInputMessage?: boolean;
}

/** Instructions the composer offers: active, and either global or bound to this role. */
function relevantInstructions(all: PromptInstruction[], agentRole: string): PromptInstruction[] {
  return all.filter((i) => i.is_active && (!i.agent_role || i.agent_role === agentRole));
}

export default function AgentConfigPanel({
  title, hint, agentRole, agent, onChange, idPrefix = 'acp', showInputMessage = true,
}: AgentConfigPanelProps) {
  const { options: models, error: modelsError } = useOptions(listModels);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [instructions, setInstructions] = useState<PromptInstruction[]>([]);
  const [presets, setPresets] = useState<SystemPromptPreset[]>([]);
  const [registryError, setRegistryError] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([listPromptsByRole(agentRole), listInstructions(), listPresets(agentRole)])
      .then(([promptRows, instructionRows, presetRows]) => {
        if (!alive) return;
        setVersions(promptRows.filter((p) => p.is_active));
        setInstructions(relevantInstructions(instructionRows, agentRole));
        setPresets(presetRows.filter((p) => p.is_active));
      })
      .catch(() => { if (alive) setRegistryError(true); });
    return () => { alive = false; };
  }, [agentRole]);

  const presetId = agent.prompt_preset_id ?? null;
  const selectedPreset = presets.find((p) => p.id === presetId) ?? null;

  /** Preset-only selection: base version and instructions are bundled inside
   * the preset (managed in the Prompt section). The BE requires a preset per
   * agent — null is a FE-only "not chosen yet" state, validated at launch. */
  function selectPreset(value: string) {
    onChange({ prompt_preset_id: value === '' ? null : Number(value) });
  }

  // Registry data feeds the preview modal only — no manual controls here.
  const selectedVersion = selectedPreset
    ? versions.find((v) => v.version_label === selectedPreset.base_prompt_version) ?? null
    : null;
  /** Registry order — the BE composes the instructions in this order. */
  const selectedInstructions = selectedPreset
    ? instructions.filter((i) => selectedPreset.instruction_ids.includes(i.id))
    : [];

  function updateContextMode(mode: ContextMode) {
    onChange({
      request_context: {
        context_mode: mode,
        retrieval_context_query: mode === 'bm25' || mode === 'embedding'
          ? agent.request_context.retrieval_context_query ?? ''
          : null,
      },
    });
  }

  const needsQuery = agent.request_context.context_mode === 'bm25'
    || agent.request_context.context_mode === 'embedding';

  return (
    <div className="acp">
      <h4 className="acp__title">
        {title}
        {hint && <span className="acp__hint"> — {hint}</span>}
      </h4>

      <label className="paper-form__label" htmlFor={`${idPrefix}-model`}>Modello</label>
      <select
        className="paper-form__select"
        id={`${idPrefix}-model`}
        value={agent.model}
        onChange={(e) => onChange({ model: e.target.value })}
      >
        {modelsError && <option value="">Error loading</option>}
        {!modelsError && models.length === 0 && <option value="">Loading…</option>}
        {models.map((name) => <option key={name} value={name}>{name}</option>)}
      </select>

      <label className="paper-form__label" htmlFor={`${idPrefix}-temperature`}>Temperature</label>
      <div className="acp__slider">
        <TemperatureSlider
          id={`${idPrefix}-temperature`}
          min={0}
          max={2}
          value={agent.temperature}
          onChange={(value) => onChange({ temperature: value })}
          inputClassName="ping-chat-model-bar__temperature"
          valueClassName="ping-chat-model-bar__temperature-value"
        />
      </div>

      <label className="paper-form__label" htmlFor={`${idPrefix}-context`}>Context mode</label>
      <select
        className="paper-form__select"
        id={`${idPrefix}-context`}
        value={agent.request_context.context_mode}
        onChange={(e) => updateContextMode(e.target.value as ContextMode)}
      >
        {CONTEXT_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
      </select>

      {needsQuery && (
        <>
          <label className="paper-form__label" htmlFor={`${idPrefix}-query`}>Retrieval query</label>
          <input
            className="paper-form__input"
            id={`${idPrefix}-query`}
            type="text"
            placeholder="query per il retrieval del contesto"
            value={agent.request_context.retrieval_context_query ?? ''}
            onChange={(e) => onChange({
              request_context: { ...agent.request_context, retrieval_context_query: e.target.value },
            })}
          />
        </>
      )}

      {/* ── System prompt: pick a saved preset; the bundle's content is
           visible only through the preview. ── */}
      <label className="paper-form__label" htmlFor={`${idPrefix}-preset`}>
        Preset <span className="acp__hint">(bundle salvati del ruolo)</span>
      </label>
      <select
        className="paper-form__select"
        id={`${idPrefix}-preset`}
        value={presetId ?? ''}
        onChange={(e) => selectPreset(e.target.value)}
      >
        <option value="">— seleziona un preset —</option>
        {presetId !== null && !selectedPreset && (
          <option value={presetId}>preset id {presetId} (non trovato)</option>
        )}
        {presets.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}{p.description ? ` — ${p.description}` : ''}
          </option>
        ))}
      </select>
      {registryError && (
        <p className="acp__prompt-error">Registry dei prompt non raggiungibile.</p>
      )}

      <div className="acp__preview">
        <button
          className="btn btn--ghost btn--sm"
          type="button"
          disabled={!selectedVersion}
          title={selectedVersion ? undefined : 'Seleziona un preset per vedere l\'anteprima.'}
          onClick={() => setPreviewOpen(true)}
        >
          👁 Anteprima prompt
        </button>
        {!selectedVersion && (
          <span className="acp__hint">seleziona un preset</span>
        )}
      </div>

      {previewOpen && selectedVersion && selectedPreset && (
        <PromptPreviewModal
          agentTitle={title}
          agentRole={agentRole}
          version={selectedVersion}
          instructions={selectedInstructions}
          presetId={selectedPreset.id}
          onClose={() => setPreviewOpen(false)}
        />
      )}

      {showInputMessage && (
        <>
          <label className="paper-form__label" htmlFor={`${idPrefix}-input-message`}>
            Input message
          </label>
          <textarea
            className="paper-form__input acp__input-message"
            id={`${idPrefix}-input-message`}
            rows={4}
            placeholder="messaggio di input per l'agente"
            value={agent.input_message ?? ''}
            onChange={(e) => onChange({ input_message: e.target.value || null })}
          />
        </>
      )}
    </div>
  );
}
