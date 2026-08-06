/**
 * PromptPreviewModal — fullscreen-overlay preview of the composed system
 * prompt for one agent, opened from AgentConfigPanel.
 *
 * The visual blocks (base template + one card per persona instruction, with
 * the axis label) are rendered from the registry data the panel already has;
 * the flat composed string is fetched from POST /prompts/presets/preview —
 * the exact resolution path the run uses — so the "Copia" button copies
 * EXACTLY what the agent will receive. Max ~80vh, the text scrolls inside
 * its own box — the page never scrolls.
 */
import { useEffect, useState } from 'react';
import { ApiError, previewPrompt } from '../api/client';
import type { PromptInstruction, PromptVersion } from '../api/types';

interface PromptPreviewModalProps {
  /** Panel heading of the agent, e.g. "🔬 Reviewer 2". */
  agentTitle: string;
  agentRole: string;
  version: PromptVersion;
  /** The selected instructions, in registry order (the BE composes in this order). */
  instructions: PromptInstruction[];
  /** The saved preset to preview — drives the composed-string fetch. */
  presetId: number;
  onClose: () => void;
}

export default function PromptPreviewModal({
  agentTitle, agentRole, version, instructions, presetId, onClose,
}: PromptPreviewModalProps) {
  const [composed, setComposed] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  // Esc closes ONLY this modal: capture-phase listener so the underlying
  // "Configura review" window listener (bubble phase) never sees the event.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  // The exact composed string, for the copy button.
  useEffect(() => {
    let alive = true;
    previewPrompt({ agent_role: agentRole, preset_id: presetId })
      .then((text) => { if (alive) setComposed(text); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, [agentRole, presetId]);

  async function onCopy() {
    if (composed === null) return;
    try {
      await navigator.clipboard.writeText(composed);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Copia non riuscita — seleziona e copia il testo a mano.');
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal prompt-preview"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prompt-preview-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="prompt-preview-title">
            Anteprima prompt — {agentTitle}
          </h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <p className="prompt-preview__meta">
          ruolo <code>{agentRole}</code> · versione <code>{version.version_label}</code>
          {' '}· {instructions.length} instruction{instructions.length === 1 ? '' : 's'}
        </p>

        <div className="prompt-preview__body">
          <section className="prompt-preview__block prompt-preview__block--base">
            <span className="prompt-preview__block-label">
              Template base — {version.version_label}
              {version.description ? ` · ${version.description}` : ''}
            </span>
            <p className="prompt-preview__text">{version.template}</p>
          </section>

          {instructions.map((instr) => (
            <section key={instr.label} className="prompt-preview__block prompt-preview__block--instruction">
              <span className="prompt-preview__block-label">
                {instr.type ?? 'other'} — {instr.label}
              </span>
              <p className="prompt-preview__text">{instr.instruction}</p>
            </section>
          ))}
        </div>

        <div className="prompt-preview__footer">
          <button
            className="btn btn--primary btn--sm"
            type="button"
            disabled={composed === null}
            onClick={onCopy}
          >
            {copied ? 'Copiato ✓' : 'Copia negli appunti'}
          </button>
          <span className="prompt-preview__footer-hint">
            La copia usa la stringa esatta composta dal backend.
          </span>
        </div>
        {error && <p className="paper-form__error">{error}</p>}
      </div>
    </div>
  );
}
