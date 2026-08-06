/** Prompt section — browse the prompt-version registry and the persona
 * instructions used by the review-graph agents. Both tables follow the same
 * pattern: truncated rows, click a row to open an accordion panel right below
 * it with every field expanded (one row open at a time). CRUD lands later. */
import { Fragment, useEffect, useMemo, useState } from 'react';
import { ApiError, createInstruction, createPreset, createPrompt, deletePreset, listInstructions, listPresets, listPrompts, listPromptsByRole, listRoles, updateInstruction, updatePreset, updatePrompt } from '../api/client';
import type { InstructionType, PromptInstruction, PromptVersion, SystemPromptPreset } from '../api/types';
import ActionCard from '../components/ActionCard';
import { useOptions } from '../components/useOptions';

const INSTRUCTION_TYPES: InstructionType[] = ['commitment', 'focus', 'intention', 'knowledgeability', 'venue', 'calibration'];

/** Case-insensitive contains, safe on null/undefined. */
function matches(text: string | null | undefined, query: string): boolean {
  return (text ?? '').toLowerCase().includes(query);
}

/** Close the modal on Esc — shared by both modals. */
function useEscToClose(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
}

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** One labeled field inside the expanded panel. */
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="prompts__field">
      <span className="prompts__field-label">{label}</span>
      <span className="prompts__field-value">{value}</span>
    </div>
  );
}

/** "Modifica" button + inline editor for the mutable metadata (description,
 * is_active) of a prompt version or instruction — the text itself is
 * immutable by design. Shown inside the expanded accordion panel. */
function MetaEditor({ description, isActive, onSave }: {
  description: string | null | undefined;
  isActive: boolean;
  onSave: (request: { description: string | null; is_active: boolean }) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draftDescription, setDraftDescription] = useState('');
  const [draftActive, setDraftActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function startEdit() {
    setDraftDescription(description ?? '');
    setDraftActive(isActive);
    setError('');
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    setError('');
    try {
      await onSave({ description: draftDescription.trim() || null, is_active: draftActive });
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <div className="prompts__edit-actions">
        <button className="btn btn--ghost btn--sm" type="button" onClick={startEdit}>
          ✎ Modifica
        </button>
        <span className="prompts__edit-hint">solo descrizione e stato attivo — il testo è immutabile</span>
      </div>
    );
  }

  return (
    <div className="prompts__edit">
      <label className="paper-form__label" htmlFor="meta-description">Descrizione</label>
      <input
        className="paper-form__input"
        id="meta-description"
        type="text"
        value={draftDescription}
        disabled={busy}
        onChange={(e) => setDraftDescription(e.target.value)}
      />
      <label className="prompts__filter">
        <input
          type="checkbox"
          checked={draftActive}
          disabled={busy}
          onChange={(e) => setDraftActive(e.target.checked)}
        />
        attiva
      </label>
      <div className="prompts__edit-actions">
        <button className="btn btn--primary btn--sm" type="button" disabled={busy} onClick={save}>
          {busy ? 'Salvataggio…' : 'Salva'}
        </button>
        <button className="btn btn--ghost btn--sm" type="button" disabled={busy} onClick={() => setEditing(false)}>
          Annulla
        </button>
      </div>
      {error && <p className="paper-form__error">{error}</p>}
    </div>
  );
}

function AllPromptsModal({ onClose }: { onClose: () => void }) {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [prompts, setPrompts] = useState<PromptVersion[] | null>(null);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [roleFilter, setRoleFilter] = useState('');
  const [search, setSearch] = useState('');

  useEscToClose(onClose);

  useEffect(() => {
    let alive = true;
    setPrompts(null);
    setError('');
    setExpandedId(null);
    listPrompts(includeInactive)
      .then((rows) => { if (alive) setPrompts(rows); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, [includeInactive]);

  const roles = useMemo(
    () => [...new Set((prompts ?? []).map((p) => p.agent_role))].sort(),
    [prompts],
  );

  const visible = useMemo(() => {
    if (prompts === null) return null;
    const query = search.trim().toLowerCase();
    return prompts.filter((p) =>
      (roleFilter === '' || p.agent_role === roleFilter)
      && (query === ''
        || matches(p.version_label, query)
        || matches(p.description, query)
        || matches(p.template, query)),
    );
  }, [prompts, roleFilter, search]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--full"
        role="dialog"
        aria-modal="true"
        aria-labelledby="all-prompts-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="all-prompts-title">Tutti i prompt</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__filters">
          <select
            className="paper-form__select prompts__filters-select"
            aria-label="Filtra per ruolo"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">tutti i ruoli</option>
            {roles.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
          <input
            className="paper-form__input prompts__filters-search"
            type="search"
            placeholder="cerca in versione, descrizione, template…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <label className="prompts__filter">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
            />
            includi disattivate
          </label>
        </div>

        {error && <p className="paper-form__error">{error}</p>}
        {!error && visible === null && <p className="paper-list__empty">Caricamento…</p>}
        {visible !== null && visible.length === 0 && (
          <p className="paper-list__empty">Nessun prompt corrisponde ai filtri.</p>
        )}
        {visible !== null && visible.length > 0 && (
          <div className="paper-list__scroll">
            <table className="paper-list">
              <thead>
                <tr>
                  <th>ruolo</th>
                  <th>versione</th>
                  <th>descrizione</th>
                  <th>template</th>
                  <th>attivo</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((p) => (
                  <Fragment key={p.id}>
                    <tr
                      className={'prompts__row' + (expandedId === p.id ? ' prompts__row--open' : '')}
                      onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                    >
                      <td className="paper-list__id">{p.agent_role}</td>
                      <td className="paper-list__id">{p.version_label}</td>
                      <td>{truncate(p.description || '—', 60)}</td>
                      <td>{truncate(p.template)}</td>
                      <td>{p.is_active ? '✓' : '—'}</td>
                    </tr>
                    {expandedId === p.id && (
                      <tr className="prompts__expand">
                        <td colSpan={5}>
                          <div className="prompts__fields">
                            <Field label="ruolo" value={p.agent_role} />
                            <Field label="versione" value={p.version_label} />
                            <Field label="attivo" value={p.is_active ? 'sì' : 'no'} />
                            <Field label="creato" value={p.created_at} />
                            <Field label="descrizione" value={p.description || '—'} />
                          </div>
                          <span className="prompts__field-label">template</span>
                          <pre className="prompts__text">{p.template}</pre>
                          <MetaEditor
                            description={p.description}
                            isActive={p.is_active}
                            onSave={async (request) => {
                              const updated = await updatePrompt(p.id, request);
                              setPrompts((prev) => prev?.map((row) => (row.id === p.id ? updated : row)) ?? prev);
                            }}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AllInstructionsModal({ onClose }: { onClose: () => void }) {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [instructions, setInstructions] = useState<PromptInstruction[] | null>(null);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [search, setSearch] = useState('');

  useEscToClose(onClose);

  useEffect(() => {
    let alive = true;
    setInstructions(null);
    setError('');
    setExpandedId(null);
    listInstructions(includeInactive)
      .then((rows) => { if (alive) setInstructions(rows); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, [includeInactive]);

  const roles = useMemo(
    () => [...new Set((instructions ?? []).map((i) => i.agent_role).filter((r): r is string => !!r))].sort(),
    [instructions],
  );

  const visible = useMemo(() => {
    if (instructions === null) return null;
    const query = search.trim().toLowerCase();
    return instructions.filter((i) =>
      (typeFilter === '' || i.type === typeFilter)
      && (roleFilter === '' || i.agent_role === roleFilter)
      && (query === ''
        || matches(i.label, query)
        || matches(i.instruction, query)
        || matches(i.description, query)),
    );
  }, [instructions, typeFilter, roleFilter, search]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--full"
        role="dialog"
        aria-modal="true"
        aria-labelledby="all-instructions-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="all-instructions-title">Tutte le instructions</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__filters">
          <select
            className="paper-form__select prompts__filters-select"
            aria-label="Filtra per tipo"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">tutti i tipi</option>
            {INSTRUCTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select
            className="paper-form__select prompts__filters-select"
            aria-label="Filtra per ruolo"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">tutti i ruoli</option>
            {roles.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
          <input
            className="paper-form__input prompts__filters-search"
            type="search"
            placeholder="cerca in label, instruction, descrizione…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <label className="prompts__filter">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
            />
            includi disattivate
          </label>
        </div>

        {error && <p className="paper-form__error">{error}</p>}
        {!error && visible === null && <p className="paper-list__empty">Caricamento…</p>}
        {visible !== null && visible.length === 0 && (
          <p className="paper-list__empty">Nessuna instruction corrisponde ai filtri.</p>
        )}
        {visible !== null && visible.length > 0 && (
          <div className="paper-list__scroll">
            <table className="paper-list">
              <thead>
                <tr>
                  <th>tipo</th>
                  <th>label</th>
                  <th>instruction</th>
                  <th>descrizione</th>
                  <th>attiva</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((i) => (
                  <Fragment key={i.id}>
                    <tr
                      className={'prompts__row' + (expandedId === i.id ? ' prompts__row--open' : '')}
                      onClick={() => setExpandedId(expandedId === i.id ? null : i.id)}
                    >
                      <td className="paper-list__id">{i.type ?? '—'}</td>
                      <td className="paper-list__id">{i.label}</td>
                      <td>{truncate(i.instruction)}</td>
                      <td>{truncate(i.description || '—', 60)}</td>
                      <td>{i.is_active ? '✓' : '—'}</td>
                    </tr>
                    {expandedId === i.id && (
                      <tr className="prompts__expand">
                        <td colSpan={5}>
                          <div className="prompts__fields">
                            <Field label="tipo" value={i.type ?? '—'} />
                            <Field label="label" value={i.label} />
                            <Field label="ruolo" value={i.agent_role || '—'} />
                            <Field label="attiva" value={i.is_active ? 'sì' : 'no'} />
                            <Field label="creata" value={i.created_at} />
                            <Field label="descrizione" value={i.description || '—'} />
                          </div>
                          <span className="prompts__field-label">instruction</span>
                          <pre className="prompts__text">{i.instruction}</pre>
                          <MetaEditor
                            description={i.description}
                            isActive={i.is_active}
                            onSave={async (request) => {
                              const updated = await updateInstruction(i.id, request);
                              setInstructions((prev) => prev?.map((row) => (row.id === i.id ? updated : row)) ?? prev);
                            }}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function CreatePromptModal({ onClose }: { onClose: () => void }) {
  const { options: roles, error: rolesError } = useOptions(listRoles);
  const [agentRole, setAgentRole] = useState('');
  const [versionLabel, setVersionLabel] = useState('');
  const [description, setDescription] = useState('');
  const [template, setTemplate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState('');
  const [existing, setExisting] = useState<PromptVersion[]>([]);
  const [copyFrom, setCopyFrom] = useState('');

  useEscToClose(onClose);

  useEffect(() => {
    let alive = true;
    listPrompts(true)
      .then((rows) => { if (alive) setExisting(rows); })
      .catch(() => { /* copy-from unavailable — the form still works */ });
    return () => { alive = false; };
  }, []);

  /** Prefill role, description and template from a saved version; the new
   * version label stays empty because (role, version) must be unique. */
  function applyCopyFrom(id: string) {
    setCopyFrom(id);
    const source = existing.find((p) => String(p.id) === id);
    if (!source) return;
    setAgentRole(source.agent_role);
    setDescription(source.description ?? '');
    setTemplate(source.template);
    setVersionLabel('');
    setCreated('');
    setError('');
  }

  const canSubmit = agentRole !== '' && versionLabel.trim() !== '' && template.trim() !== '' && !busy;

  async function onCreate() {
    setError('');
    setCreated('');
    setBusy(true);
    try {
      const prompt = await createPrompt({
        agent_role: agentRole,
        version_label: versionLabel.trim(),
        template: template.trim(),
        description: description.trim() || null,
      });
      setCreated(`Prompt creato: ${prompt.agent_role} / ${prompt.version_label}`);
      setVersionLabel('');
      setDescription('');
      setTemplate('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-prompt-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="create-prompt-title">Crea prompt</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__create-form">
        <label className="paper-form__label" htmlFor="cp-copy">Copia da (opzionale)</label>
        <select
          className="paper-form__select"
          id="cp-copy"
          value={copyFrom}
          onChange={(e) => applyCopyFrom(e.target.value)}
        >
          <option value="">— parti da zero —</option>
          {existing.map((p) => (
            <option key={p.id} value={p.id}>
              {p.agent_role} / {p.version_label}{p.description ? ` — ${p.description}` : ''}
            </option>
          ))}
        </select>

        <label className="paper-form__label" htmlFor="cp-role">Ruolo</label>
        <select
          className="paper-form__select"
          id="cp-role"
          value={agentRole}
          onChange={(e) => setAgentRole(e.target.value)}
        >
          <option value="">— seleziona un ruolo —</option>
          {rolesError && <option value="">errore caricamento ruoli</option>}
          {roles.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>

        <label className="paper-form__label" htmlFor="cp-version">Versione</label>
        <input
          className="paper-form__input"
          id="cp-version"
          type="text"
          placeholder="es. v3, skeptical-v1"
          value={versionLabel}
          onChange={(e) => setVersionLabel(e.target.value)}
        />

        <label className="paper-form__label" htmlFor="cp-description">Descrizione (opzionale)</label>
        <input
          className="paper-form__input"
          id="cp-description"
          type="text"
          placeholder="a cosa serve questa versione"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <label className="paper-form__label" htmlFor="cp-template">Template</label>
        <textarea
          className="paper-form__input prompts__create-text"
          id="cp-template"
          rows={10}
          spellCheck={false}
          placeholder="il testo del system prompt…"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        />
        </div>

        <div className="prompts__create-actions">
          <button className="btn btn--primary" type="button" disabled={!canSubmit} onClick={onCreate}>
            {busy ? 'Creazione…' : 'Crea'}
          </button>
          {created && <span className="prompts__ok">{created}</span>}
        </div>
        {error && <p className="paper-form__error">{error}</p>}
      </div>
    </div>
  );
}

function CreateInstructionModal({ onClose }: { onClose: () => void }) {
  const { options: roles, error: rolesError } = useOptions(listRoles);
  const [type, setType] = useState('');
  const [label, setLabel] = useState('');
  const [agentRole, setAgentRole] = useState('');
  const [description, setDescription] = useState('');
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState('');
  const [existing, setExisting] = useState<PromptInstruction[]>([]);
  const [copyFrom, setCopyFrom] = useState('');

  useEscToClose(onClose);

  useEffect(() => {
    let alive = true;
    listInstructions(true)
      .then((rows) => { if (alive) setExisting(rows); })
      .catch(() => { /* copy-from unavailable — the form still works */ });
    return () => { alive = false; };
  }, []);

  /** Prefill type, role, description and text from a saved instruction; the
   * new label stays empty because (type, label) must be unique. */
  function applyCopyFrom(id: string) {
    setCopyFrom(id);
    const source = existing.find((i) => String(i.id) === id);
    if (!source) return;
    setType(source.type ?? '');
    setAgentRole(source.agent_role ?? '');
    setDescription(source.description ?? '');
    setInstruction(source.instruction);
    setLabel('');
    setCreated('');
    setError('');
  }

  const canSubmit = type !== '' && label.trim() !== '' && instruction.trim() !== '' && !busy;

  async function onCreate() {
    setError('');
    setCreated('');
    setBusy(true);
    try {
      const saved = await createInstruction({
        type: type as InstructionType,
        label: label.trim(),
        instruction: instruction.trim(),
        description: description.trim() || null,
        agent_role: agentRole || null,
      });
      setCreated(`Instruction creata: ${saved.type} / ${saved.label}`);
      setLabel('');
      setDescription('');
      setInstruction('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-instruction-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="create-instruction-title">Crea instruction</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__create-form">
        <label className="paper-form__label" htmlFor="ci-copy">Copia da (opzionale)</label>
        <select
          className="paper-form__select"
          id="ci-copy"
          value={copyFrom}
          onChange={(e) => applyCopyFrom(e.target.value)}
        >
          <option value="">— parti da zero —</option>
          {existing.map((i) => (
            <option key={i.id} value={i.id}>
              {i.type ?? '—'} / {i.label}{i.description ? ` — ${i.description}` : ''}
            </option>
          ))}
        </select>

        <label className="paper-form__label" htmlFor="ci-type">Tipo (asse persona)</label>
        <select
          className="paper-form__select"
          id="ci-type"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">— seleziona un tipo —</option>
          {INSTRUCTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        <label className="paper-form__label" htmlFor="ci-label">Label</label>
        <input
          className="paper-form__input"
          id="ci-label"
          type="text"
          placeholder="es. responsible, empirical"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />

        <label className="paper-form__label" htmlFor="ci-role">Ruolo (opzionale)</label>
        <select
          className="paper-form__select"
          id="ci-role"
          value={agentRole}
          onChange={(e) => setAgentRole(e.target.value)}
        >
          <option value="">— nessun ruolo —</option>
          {rolesError && <option value="">errore caricamento ruoli</option>}
          {roles.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>

        <label className="paper-form__label" htmlFor="ci-description">Descrizione (opzionale)</label>
        <input
          className="paper-form__input"
          id="ci-description"
          type="text"
          placeholder="sintesi della persona"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <label className="paper-form__label" htmlFor="ci-instruction">Instruction</label>
        <textarea
          className="paper-form__input prompts__create-text"
          id="ci-instruction"
          rows={7}
          spellCheck={false}
          placeholder="il testo dell'istruzione persona…"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
        </div>

        <div className="prompts__create-actions">
          <button className="btn btn--primary" type="button" disabled={!canSubmit} onClick={onCreate}>
            {busy ? 'Creazione…' : 'Crea'}
          </button>
          {created && <span className="prompts__ok">{created}</span>}
        </div>
        {error && <p className="paper-form__error">{error}</p>}
      </div>
    </div>
  );
}

/** Checkbox groups of instructions by axis type, selected by id — shared by
 * the preset editor and creator. Untyped instructions land under "other". */
function InstructionIdPicker({ instructions, selectedIds, onToggle }: {
  instructions: PromptInstruction[];
  selectedIds: number[];
  onToggle: (id: number) => void;
}) {
  const groups = useMemo(() => {
    const map = new Map<string, PromptInstruction[]>();
    for (const instr of instructions) {
      const key = instr.type ?? 'other';
      map.set(key, [...(map.get(key) ?? []), instr]);
    }
    return [...map.entries()];
  }, [instructions]);

  if (instructions.length === 0) return null;
  return (
    <fieldset className="acp__instructions">
      <legend className="paper-form__label">Instructions (persona)</legend>
      {groups.map(([type, group]) => (
        <div key={type} className="acp__instructions-group">
          <span className="acp__instructions-type">{type}</span>
          {group.map((instr) => (
            <label key={instr.id} className="acp__instructions-item">
              <input
                type="checkbox"
                checked={selectedIds.includes(instr.id)}
                onChange={() => onToggle(instr.id)}
              />
              <span title={instr.instruction}>
                {instr.label}{instr.is_active ? '' : ' (disattivata)'}
              </span>
            </label>
          ))}
        </div>
      ))}
    </fieldset>
  );
}

/** Full inline editor for a preset — unlike versions/instructions a preset is a
 * mutable selection, so every field (name, description, base version,
 * instruction ids, active) can change; "Elimina" removes it for good. */
function PresetEditor({ preset, versions, instructions, onSaved, onDeleted }: {
  preset: SystemPromptPreset;
  /** Prompt versions of the preset's role (inactive included, so a stale
   * reference stays visible and fixable). */
  versions: PromptVersion[];
  /** Instructions offered for this role, plus any already referenced by id. */
  instructions: PromptInstruction[];
  onSaved: (updated: SystemPromptPreset) => void;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftDescription, setDraftDescription] = useState('');
  const [draftBaseVersion, setDraftBaseVersion] = useState('');
  const [draftIds, setDraftIds] = useState<number[]>([]);
  const [draftActive, setDraftActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function startEdit() {
    setDraftName(preset.name);
    setDraftDescription(preset.description ?? '');
    setDraftBaseVersion(preset.base_prompt_version);
    setDraftIds([...preset.instruction_ids]);
    setDraftActive(preset.is_active);
    setError('');
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    setError('');
    try {
      const updated = await updatePreset(preset.id, {
        name: draftName.trim(),
        description: draftDescription.trim() || null,
        base_prompt_version: draftBaseVersion,
        instruction_ids: draftIds,
        is_active: draftActive,
      });
      onSaved(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Eliminare il preset "${preset.name}"?`)) return;
    setBusy(true);
    setError('');
    try {
      await deletePreset(preset.id);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <div className="prompts__edit-actions">
        <button className="btn btn--ghost btn--sm" type="button" disabled={busy} onClick={startEdit}>
          ✎ Modifica
        </button>
        <button className="btn btn--ghost btn--sm" type="button" disabled={busy} onClick={remove}>
          🗑 Elimina
        </button>
        <span className="prompts__edit-hint">i preset sono modificabili: nome, prompt base e instructions</span>
        {error && <p className="paper-form__error">{error}</p>}
      </div>
    );
  }

  const canSave = draftName.trim() !== '' && draftBaseVersion !== '' && !busy;

  return (
    <div className="prompts__edit">
      <label className="paper-form__label" htmlFor="preset-name">Nome</label>
      <input
        className="paper-form__input"
        id="preset-name"
        type="text"
        value={draftName}
        disabled={busy}
        onChange={(e) => setDraftName(e.target.value)}
      />
      <label className="paper-form__label" htmlFor="preset-description">Descrizione</label>
      <input
        className="paper-form__input"
        id="preset-description"
        type="text"
        value={draftDescription}
        disabled={busy}
        onChange={(e) => setDraftDescription(e.target.value)}
      />
      <label className="paper-form__label" htmlFor="preset-base">Prompt base</label>
      <select
        className="paper-form__select"
        id="preset-base"
        value={draftBaseVersion}
        disabled={busy}
        onChange={(e) => setDraftBaseVersion(e.target.value)}
      >
        {!versions.some((v) => v.version_label === draftBaseVersion) && draftBaseVersion !== '' && (
          <option value={draftBaseVersion}>{draftBaseVersion} (non nel registry)</option>
        )}
        {versions.map((v) => (
          <option key={v.id} value={v.version_label}>
            {v.version_label}{v.is_active ? '' : ' (disattivata)'}{v.description ? ` — ${v.description}` : ''}
          </option>
        ))}
      </select>
      <InstructionIdPicker
        instructions={instructions}
        selectedIds={draftIds}
        onToggle={(id) => setDraftIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))}
      />
      <label className="prompts__filter">
        <input
          type="checkbox"
          checked={draftActive}
          disabled={busy}
          onChange={(e) => setDraftActive(e.target.checked)}
        />
        attivo
      </label>
      <div className="prompts__edit-actions">
        <button className="btn btn--primary btn--sm" type="button" disabled={!canSave} onClick={save}>
          {busy ? 'Salvataggio…' : 'Salva'}
        </button>
        <button className="btn btn--ghost btn--sm" type="button" disabled={busy} onClick={() => setEditing(false)}>
          Annulla
        </button>
      </div>
      {error && <p className="paper-form__error">{error}</p>}
    </div>
  );
}

function AllPresetsModal({ onClose }: { onClose: () => void }) {
  const [includeInactive, setIncludeInactive] = useState(false);
  const [presets, setPresets] = useState<SystemPromptPreset[] | null>(null);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [roleFilter, setRoleFilter] = useState('');
  const [search, setSearch] = useState('');
  // Registries for resolving instruction ids and offering the edit selects;
  // loaded once, inactive rows included so stale references stay readable.
  const [allPrompts, setAllPrompts] = useState<PromptVersion[]>([]);
  const [allInstructions, setAllInstructions] = useState<PromptInstruction[]>([]);

  useEscToClose(onClose);

  useEffect(() => {
    let alive = true;
    setPresets(null);
    setError('');
    setExpandedId(null);
    listPresets(undefined, includeInactive)
      .then((rows) => { if (alive) setPresets(rows); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, [includeInactive]);

  useEffect(() => {
    let alive = true;
    Promise.all([listPrompts(true), listInstructions(true)])
      .then(([promptRows, instructionRows]) => {
        if (!alive) return;
        setAllPrompts(promptRows);
        setAllInstructions(instructionRows);
      })
      .catch(() => { /* editors degrade — the table still renders */ });
    return () => { alive = false; };
  }, []);

  const roles = useMemo(
    () => [...new Set((presets ?? []).map((p) => p.agent_role))].sort(),
    [presets],
  );

  const visible = useMemo(() => {
    if (presets === null) return null;
    const query = search.trim().toLowerCase();
    return presets.filter((p) =>
      (roleFilter === '' || p.agent_role === roleFilter)
      && (query === ''
        || matches(p.name, query)
        || matches(p.description, query)
        || matches(p.base_prompt_version, query)),
    );
  }, [presets, roleFilter, search]);

  function instructionLabel(id: number): string {
    const instr = allInstructions.find((i) => i.id === id);
    return instr ? `[${instr.type ?? '—'}] ${instr.label}` : `id ${id} (sconosciuta)`;
  }

  /** Instructions the editor offers for a preset: active + global-or-role
   * bound, plus whatever the preset already references by id. */
  function editorInstructions(preset: SystemPromptPreset): PromptInstruction[] {
    return allInstructions.filter((i) =>
      preset.instruction_ids.includes(i.id)
      || (i.is_active && (!i.agent_role || i.agent_role === preset.agent_role)));
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--full"
        role="dialog"
        aria-modal="true"
        aria-labelledby="all-presets-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="all-presets-title">Tutti i preset</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__filters">
          <select
            className="paper-form__select prompts__filters-select"
            aria-label="Filtra per ruolo"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">tutti i ruoli</option>
            {roles.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
          <input
            className="paper-form__input prompts__filters-search"
            type="search"
            placeholder="cerca in nome, descrizione, prompt base…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <label className="prompts__filter">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
            />
            includi disattivati
          </label>
        </div>

        {error && <p className="paper-form__error">{error}</p>}
        {!error && visible === null && <p className="paper-list__empty">Caricamento…</p>}
        {visible !== null && visible.length === 0 && (
          <p className="paper-list__empty">Nessun preset corrisponde ai filtri.</p>
        )}
        {visible !== null && visible.length > 0 && (
          <div className="paper-list__scroll">
            <table className="paper-list">
              <thead>
                <tr>
                  <th>ruolo</th>
                  <th>nome</th>
                  <th>prompt base</th>
                  <th>instructions</th>
                  <th>attivo</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((p) => (
                  <Fragment key={p.id}>
                    <tr
                      className={'prompts__row' + (expandedId === p.id ? ' prompts__row--open' : '')}
                      onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                    >
                      <td className="paper-list__id">{p.agent_role}</td>
                      <td className="paper-list__id">{p.name}</td>
                      <td>{p.base_prompt_version}</td>
                      <td>{p.instruction_ids.length}</td>
                      <td>{p.is_active ? '✓' : '—'}</td>
                    </tr>
                    {expandedId === p.id && (
                      <tr className="prompts__expand">
                        <td colSpan={5}>
                          <div className="prompts__fields">
                            <Field label="ruolo" value={p.agent_role} />
                            <Field label="nome" value={p.name} />
                            <Field label="prompt base" value={p.base_prompt_version} />
                            <Field label="attivo" value={p.is_active ? 'sì' : 'no'} />
                            <Field label="creato" value={p.created_at} />
                            <Field label="aggiornato" value={p.updated_at || '—'} />
                            <Field label="descrizione" value={p.description || '—'} />
                          </div>
                          <span className="prompts__field-label">instructions</span>
                          <pre className="prompts__text">
                            {p.instruction_ids.length === 0
                              ? '— nessuna —'
                              : p.instruction_ids.map(instructionLabel).join('\n')}
                          </pre>
                          <PresetEditor
                            preset={p}
                            versions={allPrompts.filter((v) => v.agent_role === p.agent_role)}
                            instructions={editorInstructions(p)}
                            onSaved={(updated) => {
                              setPresets((prev) => prev?.map((row) => (row.id === p.id ? updated : row)) ?? prev);
                            }}
                            onDeleted={() => {
                              setPresets((prev) => prev?.filter((row) => row.id !== p.id) ?? prev);
                              setExpandedId(null);
                            }}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function CreatePresetModal({ onClose }: { onClose: () => void }) {
  const { options: roles, error: rolesError } = useOptions(listRoles);
  const [agentRole, setAgentRole] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [baseVersion, setBaseVersion] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [instructions, setInstructions] = useState<PromptInstruction[]>([]);
  const [registryError, setRegistryError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState('');

  useEscToClose(onClose);

  // The offered base versions and instructions follow the chosen role, exactly
  // like the per-node composer in AgentConfigPanel (active, global or role-bound).
  useEffect(() => {
    if (agentRole === '') {
      setVersions([]);
      setInstructions([]);
      return;
    }
    let alive = true;
    setRegistryError(false);
    Promise.all([listPromptsByRole(agentRole), listInstructions()])
      .then(([promptRows, instructionRows]) => {
        if (!alive) return;
        setVersions(promptRows.filter((v) => v.is_active));
        setInstructions(instructionRows.filter((i) => i.is_active && (!i.agent_role || i.agent_role === agentRole)));
      })
      .catch(() => { if (alive) setRegistryError(true); });
    return () => { alive = false; };
  }, [agentRole]);

  function changeRole(role: string) {
    setAgentRole(role);
    setBaseVersion('');
    setSelectedIds([]);
    setCreated('');
    setError('');
  }

  const canSubmit = agentRole !== '' && name.trim() !== '' && baseVersion !== '' && !busy;

  async function onCreate() {
    setError('');
    setCreated('');
    setBusy(true);
    try {
      const preset = await createPreset({
        agent_role: agentRole,
        name: name.trim(),
        base_prompt_version: baseVersion,
        instruction_ids: selectedIds,
        description: description.trim() || null,
      });
      setCreated(`Preset creato: ${preset.agent_role} / ${preset.name}`);
      setName('');
      setDescription('');
      setSelectedIds([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-preset-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="create-preset-title">Crea preset</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__create-form">
        <label className="paper-form__label" htmlFor="cps-role">Ruolo</label>
        <select
          className="paper-form__select"
          id="cps-role"
          value={agentRole}
          onChange={(e) => changeRole(e.target.value)}
        >
          <option value="">— seleziona un ruolo —</option>
          {rolesError && <option value="">errore caricamento ruoli</option>}
          {roles.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>

        <label className="paper-form__label" htmlFor="cps-name">Nome</label>
        <input
          className="paper-form__input"
          id="cps-name"
          type="text"
          placeholder="es. reviewer-severo, empirico-neurips"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <label className="paper-form__label" htmlFor="cps-description">Descrizione (opzionale)</label>
        <input
          className="paper-form__input"
          id="cps-description"
          type="text"
          placeholder="a cosa serve questo preset"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <label className="paper-form__label" htmlFor="cps-base">Prompt base</label>
        <select
          className="paper-form__select"
          id="cps-base"
          value={baseVersion}
          disabled={agentRole === ''}
          onChange={(e) => setBaseVersion(e.target.value)}
        >
          <option value="">{agentRole === '' ? '— seleziona prima un ruolo —' : '— seleziona una versione —'}</option>
          {versions.map((v) => (
            <option key={v.id} value={v.version_label}>
              {v.version_label}{v.description ? ` — ${v.description}` : ''}
            </option>
          ))}
        </select>
        {registryError && <p className="paper-form__error">Registry dei prompt non raggiungibile.</p>}

        <InstructionIdPicker
          instructions={instructions}
          selectedIds={selectedIds}
          onToggle={(id) => setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))}
        />
        </div>

        <div className="prompts__create-actions">
          <button className="btn btn--primary" type="button" disabled={!canSubmit} onClick={onCreate}>
            {busy ? 'Creazione…' : 'Crea'}
          </button>
          {created && <span className="prompts__ok">{created}</span>}
        </div>
        {error && <p className="paper-form__error">{error}</p>}
      </div>
    </div>
  );
}

export default function Prompts() {
  const [promptsOpen, setPromptsOpen] = useState(false);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [createPromptOpen, setCreatePromptOpen] = useState(false);
  const [createInstructionOpen, setCreateInstructionOpen] = useState(false);
  const [createPresetOpen, setCreatePresetOpen] = useState(false);

  return (
    <div className="section-wrap">
      <h2 className="section-title">Prompt</h2>
      <p className="section-description">
        Registry dei prompt di sistema e delle persona instructions usati dagli
        agenti del grafo di review.
      </p>

      <ActionCard
        title="Tutti i prompt"
        description={
          <>
            Il registry completo delle prompt version: ruolo, versione, template
            e stato di attivazione.
          </>
        }
        actionLabel="Apri"
        onAction={() => setPromptsOpen(true)}
      />

      <ActionCard
        title="Tutte le instructions"
        description={
          <>
            Le persona instructions per asse (focus, commitment, intention,
            knowledgeability) usate per comporre i prompt dei reviewer.
          </>
        }
        actionLabel="Apri"
        onAction={() => setInstructionsOpen(true)}
      />

      <ActionCard
        title="Crea prompt"
        description={
          <>
            Registra una nuova versione immutabile di prompt per un ruolo:
            versione, descrizione e template.
          </>
        }
        actionLabel="Crea"
        onAction={() => setCreatePromptOpen(true)}
      />

      <ActionCard
        title="Crea instruction"
        description={
          <>
            Registra una nuova persona instruction: asse, label, ruolo
            opzionale e testo dell'istruzione.
          </>
        }
        actionLabel="Crea"
        onAction={() => setCreateInstructionOpen(true)}
      />

      <ActionCard
        title="Tutti i preset"
        description={
          <>
            I preset di system prompt: bundle nominati per ruolo di prompt base
            + instructions, selezionabili per gli agenti del grafo.
          </>
        }
        actionLabel="Apri"
        onAction={() => setPresetsOpen(true)}
      />

      <ActionCard
        title="Crea preset"
        description={
          <>
            Salva una combinazione di prompt base e instructions con un nome,
            da riusare nella configurazione del grafo di review.
          </>
        }
        actionLabel="Crea"
        onAction={() => setCreatePresetOpen(true)}
      />

      {promptsOpen && <AllPromptsModal onClose={() => setPromptsOpen(false)} />}
      {instructionsOpen && <AllInstructionsModal onClose={() => setInstructionsOpen(false)} />}
      {presetsOpen && <AllPresetsModal onClose={() => setPresetsOpen(false)} />}
      {createPromptOpen && <CreatePromptModal onClose={() => setCreatePromptOpen(false)} />}
      {createInstructionOpen && <CreateInstructionModal onClose={() => setCreateInstructionOpen(false)} />}
      {createPresetOpen && <CreatePresetModal onClose={() => setCreatePresetOpen(false)} />}
    </div>
  );
}
