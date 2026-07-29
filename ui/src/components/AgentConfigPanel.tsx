/**
 * AgentConfigPanel — standalone editor for a single AgentConfig.
 *
 * Section-agnostic on purpose: the Review Graph mounts it next to the pipeline
 * graph today, other sections can reuse it as-is. It owns the model catalog
 * fetch and the JSON draft of system_prompt; the parent owns the AgentConfig
 * value and receives patches via onChange. Remount it (React key) when the
 * edited agent switches, so the JSON draft resets with it.
 */
import { useState } from 'react';
import { listModels } from '../api/client';
import type { AgentConfig, ContextMode, SystemPrompt } from '../api/types';
import TemperatureSlider from './TemperatureSlider';
import { useOptions } from './useOptions';

const CONTEXT_MODES: ContextMode[] = ['none', 'full_context', 'bm25', 'embedding'];

interface AgentConfigPanelProps {
  /** Panel heading, e.g. "🔬 Reviewer 2". */
  title: string;
  /** Optional muted note next to the title. */
  hint?: string;
  agent: AgentConfig;
  onChange: (patch: Partial<AgentConfig>) => void;
  /** Prefix for input ids, to keep labels unique per mounted panel. */
  idPrefix?: string;
  /** Hide the input message field where it is not relevant yet (default shown). */
  showInputMessage?: boolean;
}

function formatPrompt(prompt: SystemPrompt | null | undefined): string {
  return prompt == null ? '' : JSON.stringify(prompt, null, 2);
}

export default function AgentConfigPanel({
  title, hint, agent, onChange, idPrefix = 'acp', showInputMessage = true,
}: AgentConfigPanelProps) {
  const { options: models, error: modelsError } = useOptions(listModels);
  const [promptDraft, setPromptDraft] = useState(() => formatPrompt(agent.system_prompt));
  const [promptError, setPromptError] = useState('');

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

  /** Commit only valid JSON objects; keep typing free in the meantime. */
  function updatePromptDraft(text: string) {
    setPromptDraft(text);
    if (text.trim() === '') {
      setPromptError('');
      onChange({ system_prompt: null });
      return;
    }
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setPromptError('Deve essere un oggetto JSON, es. {"role": "..."}');
        return;
      }
      setPromptError('');
      onChange({ system_prompt: parsed as SystemPrompt });
    } catch {
      setPromptError('JSON non valido — la modifica non è applicata.');
    }
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

      <label className="paper-form__label" htmlFor={`${idPrefix}-prompt`}>
        System prompt <span className="acp__hint">(JSON)</span>
      </label>
      <textarea
        className={'paper-form__input acp__prompt' + (promptError ? ' acp__prompt--invalid' : '')}
        id={`${idPrefix}-prompt`}
        rows={7}
        spellCheck={false}
        placeholder={'{\n  "role": "sei un reviewer esperto",\n  "focus": ["novelty", "soundness"]\n}'}
        value={promptDraft}
        onChange={(e) => updatePromptDraft(e.target.value)}
      />
      {promptError && <p className="acp__prompt-error">{promptError}</p>}

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
