/** Single-turn LLM chat tester — the old "test-llm" / ping-chat section. */
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { listModels, pingChat } from '../api/client';
import TemperatureSlider from '../components/TemperatureSlider';
import { useOptions } from '../components/useOptions';

interface Bubble {
  role: 'user' | 'bot';
  text: string;
  model?: string;
  isError?: boolean;
}

const EXAMPLES = [
  "Respond with a simple 'ping'.",
  'Say hello in one short sentence.',
  'What is 2 + 2?',
];

/** Pretty-print a JSON payload; return null when the text isn't JSON. */
function tryPrettyJson(text: string): string | null {
  const t = text.trim();
  if (!t || (t[0] !== '{' && t[0] !== '[')) return null;
  try {
    return JSON.stringify(JSON.parse(t), null, 2);
  } catch {
    return null;
  }
}

function renderBotBody(text: string): ReactNode {
  const pretty = tryPrettyJson(text);
  if (pretty !== null) return <pre className="ping-chat-json">{pretty}</pre>;
  return text;
}

export default function PingChat() {
  const { options: models, error: modelsError } = useOptions(listModels);
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [message, setMessage] = useState('');
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [locked, setLocked] = useState(false);

  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Default to the first model once loaded.
  useEffect(() => {
    if (!model && models.length > 0) setModel(models[0]);
  }, [models, model]);

  // Auto-scroll on new bubbles / loading indicator.
  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [bubbles, locked]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  function useExample(text: string) {
    setMessage(text);
    inputRef.current?.focus();
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = message.trim();
    if (!text || locked) return;

    const usedModel = model || 'mock';
    setMessage('');
    setLocked(true);
    setBubbles((prev) => [...prev, { role: 'user', text }]);

    try {
      const data = await pingChat(text, usedModel, temperature);
      // The ping reply is treated as JSON: render the whole payload.
      setBubbles((prev) => [...prev, { role: 'bot', text: JSON.stringify(data, null, 2), model: usedModel }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setBubbles((prev) => [...prev, { role: 'bot', text: `Error: ${msg}`, isError: true }]);
    } finally {
      setLocked(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div className="ping-chat-section">
      <div className="ping-chat-model-bar">
        <label className="ping-chat-model-bar__label" htmlFor="model-select">Model:</label>
        <select
          className="ping-chat-model-bar__select"
          id="model-select"
          value={model}
          disabled={locked}
          onChange={(e) => setModel(e.target.value)}
        >
          {modelsError && <option value="">Error loading</option>}
          {!modelsError && models.length === 0 && <option value="">Loading…</option>}
          {models.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>

        <label className="ping-chat-model-bar__label" htmlFor="temperature-input">Temperature:</label>
        <TemperatureSlider
          id="temperature-input"
          min={0}
          max={2}
          value={temperature}
          onChange={setTemperature}
          disabled={locked}
          inputClassName="ping-chat-model-bar__temperature"
          valueClassName="ping-chat-model-bar__temperature-value"
        />

        <span className="ping-chat-model-bar__spacer" />
        {bubbles.length > 0 && (
          <button
            type="button"
            className="btn btn--ghost btn--sm ping-chat-clear-btn"
            onClick={() => setBubbles([])}
            disabled={locked}
          >
            Clear
          </button>
        )}
      </div>

      <div className="ping-chat-messages" ref={messagesRef}>
        {bubbles.length === 0 && !locked && (
          <div className="ping-chat-welcome">
            <span className="ping-chat-welcome__icon">📝</span>
            <h3 className="ping-chat-welcome__heading">Ping the model</h3>
            <p className="ping-chat-welcome__text">
              Send a message to test the selected model. Try one of these:
            </p>
            <div className="ping-chat-examples">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  className="ping-chat-example"
                  onClick={() => useExample(ex)}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {bubbles.map((bubble, i) => (
          <div
            key={i}
            className={
              `ping-chat-bubble ping-chat-bubble--${bubble.role}` +
              (bubble.isError ? ' ping-chat-bubble--error' : '')
            }
          >
            {bubble.role === 'bot' && bubble.model && !bubble.isError && (
              <span className="ping-chat-bubble__caption">{bubble.model}</span>
            )}
            {bubble.role === 'bot' ? renderBotBody(bubble.text) : bubble.text}
          </div>
        ))}
        {locked && (
          <div className="ping-chat-bubble ping-chat-bubble--bot">
            <span className="loading-dots"><span></span><span></span><span></span></span>
          </div>
        )}
      </div>

      <form className="ping-chat-input-bar" noValidate onSubmit={onSubmit}>
        <input
          ref={inputRef}
          className="ping-chat-input"
          type="text"
          placeholder="Enter a message to ping…"
          autoComplete="off"
          maxLength={2000}
          value={message}
          disabled={locked}
          onChange={(e) => setMessage(e.target.value)}
        />
        <button className="btn btn--primary ping-chat-send-btn" type="submit" disabled={locked}>
          Ping
        </button>
      </form>
    </div>
  );
}
