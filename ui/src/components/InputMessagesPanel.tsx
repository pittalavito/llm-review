/**
 * InputMessagesPanel — editor for the graph-level input messages.
 *
 * Graph configuration, not per-agent config: input_messages[agentKey][i] is
 * the message that agent receives at round i+1, and every agent has its own
 * messages. Standalone on purpose (same contract as AgentConfigPanel): the
 * parent owns the record and receives it whole via onChange; the number of
 * rounds is decided elsewhere. Two modes: pass `agentKey` to edit one agent's
 * messages (no selector — e.g. embedded in the agent editor), or pass
 * `agents` to let the user pick the agent from a select.
 */
import { useState } from 'react';

export interface AgentOption {
  key: string;
  label: string;
}

interface InputMessagesPanelProps {
  rounds: number;
  messages: Record<string, string[]>;
  onChange: (messages: Record<string, string[]>) => void;
  /** Fixed agent to edit — hides the agent selector. */
  agentKey?: string;
  /** Selectable agents — used only when agentKey is not given. */
  agents?: AgentOption[];
  /** Prefix for input ids, to keep labels unique per mounted panel. */
  idPrefix?: string;
}

/** The stored array for an agent, padded/truncated to the current rounds. */
function messagesFor(messages: Record<string, string[]>, key: string, rounds: number): string[] {
  const stored = messages[key] ?? [];
  return Array.from({ length: rounds }, (_, i) => stored[i] ?? '');
}

export default function InputMessagesPanel({
  rounds, messages, onChange, agentKey, agents = [], idPrefix = 'imp',
}: InputMessagesPanelProps) {
  const [selectedKey, setSelectedKey] = useState(agents[0]?.key ?? '');
  const key = agentKey ?? selectedKey;
  const current = messagesFor(messages, key, rounds);

  function updateRound(index: number, text: string) {
    onChange({
      ...messages,
      [key]: current.map((m, i) => (i === index ? text : m)),
    });
  }

  return (
    <div className="imp">
      <h4 className="imp__title">
        💬 Input message
        <span className="imp__hint"> — {agentKey ? 'un messaggio per round' : 'per agente, per round'}</span>
      </h4>
      <p className="imp__note">
        {agentKey
          ? 'I messaggi che questo agente riceve ad ogni round; il numero di round si imposta con "Max round".'
          : 'Ogni agente riceve i propri messaggi, uno per round; il numero di round si imposta con "Max round".'}
      </p>

      {!agentKey && (
        <>
          <label className="paper-form__label" htmlFor={`${idPrefix}-agent`}>Agente</label>
          <select
            className="paper-form__select"
            id={`${idPrefix}-agent`}
            value={selectedKey}
            onChange={(e) => setSelectedKey(e.target.value)}
          >
            {agents.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
          </select>
        </>
      )}

      {current.map((message, i) => (
        <div key={i}>
          <label className="paper-form__label" htmlFor={`${idPrefix}-round-${i}`}>
            Round {i + 1}
          </label>
          <textarea
            className="paper-form__input imp__message"
            id={`${idPrefix}-round-${i}`}
            rows={3}
            placeholder={`messaggio per il round ${i + 1}`}
            value={message}
            onChange={(e) => updateRound(i, e.target.value)}
          />
        </div>
      ))}
    </div>
  );
}
