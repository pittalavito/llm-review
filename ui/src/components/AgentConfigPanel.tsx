/**
 * AgentConfigPanel — standalone editor for a single AgentConfig.
 *
 * Section-agnostic on purpose: the Review Graph mounts it next to the pipeline
 * graph today, other sections can reuse it as-is. It owns the model catalog and
 * prompt-registry fetches; the parent owns the AgentConfig value and receives
 * patches via onChange. Remount it (React key) when the edited agent switches,
 * so the local preview state resets with it.
 *
 * The system prompt is composed on the BE (base version + instruction labels):
 * here the user picks a registered base prompt for the role, checks the persona
 * instructions, and can preview the exact composed string via /prompts/preview.
 */
import { useEffect, useState } from 'react';
import { ApiError, listInstructions, listModels, listPromptsByRole, previewPrompt } from '../api/client';
import type { AgentConfig, AgentSystemPromptRequest, ContextMode, PromptInstruction, PromptVersion } from '../api/types';
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

/** Group instructions by axis type, untyped ones under "other". */
function groupByType(instructions: PromptInstruction[]): [string, PromptInstruction[]][] {
  const groups = new Map<string, PromptInstruction[]>();
  for (const instr of instructions) {
    const key = instr.type ?? 'other';
    groups.set(key, [...(groups.get(key) ?? []), instr]);
  }
  return [...groups.entries()];
}

export default function AgentConfigPanel({
  title, hint, agentRole, agent, onChange, idPrefix = 'acp', showInputMessage = true,
}: AgentConfigPanelProps) {
  const { options: models, error: modelsError } = useOptions(listModels);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [instructions, setInstructions] = useState<PromptInstruction[]>([]);
  const [registryError, setRegistryError] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewBusy, setPreviewBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([listPromptsByRole(agentRole), listInstructions()])
      .then(([promptRows, instructionRows]) => {
        if (!alive) return;
        setVersions(promptRows.filter((p) => p.is_active));
        setInstructions(relevantInstructions(instructionRows, agentRole));
      })
      .catch(() => { if (alive) setRegistryError(true); });
    return () => { alive = false; };
  }, [agentRole]);

  const promptRequest: AgentSystemPromptRequest | null = agent.system_prompt_request ?? null;
  const baseVersion = promptRequest?.base_prompt_version ?? '';
  const selectedLabels = promptRequest?.instruction_labels ?? [];

  function updatePromptRequest(patch: Partial<AgentSystemPromptRequest>) {
    setPreview(null);
    setPreviewError('');
    const next: AgentSystemPromptRequest = {
      base_prompt_version: promptRequest?.base_prompt_version ?? null,
      instruction_labels: promptRequest?.instruction_labels ?? [],
      ...patch,
    };
    onChange({ system_prompt_request: next.base_prompt_version === null ? null : next });
  }

  function toggleInstruction(label: string) {
    const labels = selectedLabels.includes(label)
      ? selectedLabels.filter((l) => l !== label)
      : [...selectedLabels, label];
    updatePromptRequest({ instruction_labels: labels });
  }

  async function onPreview() {
    if (!baseVersion) return;
    setPreviewBusy(true);
    setPreviewError('');
    try {
      setPreview(await previewPrompt({
        agent_role: agentRole,
        base_prompt_version: baseVersion,
        instruction_labels: selectedLabels,
      }));
    } catch (err) {
      setPreview(null);
      setPreviewError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPreviewBusy(false);
    }
  }

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

      {/* ── System prompt composer: base version + persona instructions ── */}
      <label className="paper-form__label" htmlFor={`${idPrefix}-prompt-version`}>
        Prompt base <span className="acp__hint">(registry del ruolo)</span>
      </label>
      <select
        className="paper-form__select"
        id={`${idPrefix}-prompt-version`}
        value={baseVersion}
        onChange={(e) => updatePromptRequest({ base_prompt_version: e.target.value || null })}
      >
        <option value="">— nessun prompt —</option>
        {versions.map((v) => (
          <option key={v.id} value={v.version_label}>
            {v.version_label}{v.description ? ` — ${v.description}` : ''}
          </option>
        ))}
      </select>
      {registryError && (
        <p className="acp__prompt-error">Registry dei prompt non raggiungibile.</p>
      )}

      {baseVersion && instructions.length > 0 && (
        <fieldset className="acp__instructions">
          <legend className="paper-form__label">Instructions (persona)</legend>
          {groupByType(instructions).map(([type, group]) => (
            <div key={type} className="acp__instructions-group">
              <span className="acp__instructions-type">{type}</span>
              {group.map((instr) => (
                <label key={instr.label} className="acp__instructions-item">
                  <input
                    type="checkbox"
                    checked={selectedLabels.includes(instr.label)}
                    onChange={() => toggleInstruction(instr.label)}
                  />
                  <span title={instr.instruction}>{instr.label}</span>
                </label>
              ))}
            </div>
          ))}
        </fieldset>
      )}

      {baseVersion && (
        <div className="acp__preview">
          <button
            className="btn btn--ghost btn--sm"
            type="button"
            disabled={previewBusy}
            onClick={onPreview}
          >
            {previewBusy ? 'Compongo…' : 'Anteprima prompt'}
          </button>
          {previewError && <p className="acp__prompt-error">{previewError}</p>}
          {preview !== null && <pre className="acp__preview-text">{preview}</pre>}
        </div>
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
