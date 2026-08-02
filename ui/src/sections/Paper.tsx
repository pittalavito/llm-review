/** Paper section — action cards in the Admin style. "Carica un nuovo paper"
 * opens a modal with the upload form: .pdf/.txt file, type, optional
 * description. The file travels base64-encoded inside CreatePaperRequest
 * (POST /paper/create); the backend derives the paper_id
 * (<paper-type>_<name>_<extension>) and stores row + file under it.
 * List/detail cards are TODO placeholders for the upcoming endpoints. */
import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, createOpenreviewPaper, createPaper, getIndexStatus, indexPaper, listPapers, listPaperTypes, listRetrievalStrategies } from '../api/client';
import type { Author, IndexInfo, Paper as PaperModel, RagStrategy } from '../api/types';
import ActionCard from '../components/ActionCard';
import { useOptions } from '../components/useOptions';

const INDEX_POLL_INTERVAL_MS = 2000;
const INDEX_POLL_MAX_ATTEMPTS = 150; // ~5 minutes

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Catalog paper ids for the index-paper select (module-level: stable identity
 * for useOptions). */
const listPaperIds = () => listPapers().then((papers) => papers.map((paper) => paper.paper_id));

const ALLOWED_EXTENSIONS = ['pdf', 'txt'];

/** Extension of a file name, lowercased ("" when absent). */
function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot + 1).toLowerCase();
}

/** File name without its extension — prefill for the user-typed paper name. */
function stemOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? name : name.slice(0, dot);
}

/** File content -> base64 string (chunked to keep the call stack small). */
async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

const OPENREVIEW_CONFERENCES = ['ICLR', 'NeurIPS'];

/** What the FE extracts from a pasted OpenReview forum response. */
interface ParsedForum {
  forumId: string;
  title: string;
  abstract: string | null;
  pdf: string | null;
  decision: string | null;
  apiVersion: 'v1' | 'v2';
  noteCount: number;
  authors: { name: string; profileId: string }[];
  /** The verbatim notes array — shipped to the BE for the cache and the PDF uri. */
  notes: Record<string, unknown>[];
}

/** OpenReview API v2 wraps content fields as {"value": ...}; flatten to the value. */
function unwrapValue(value: unknown): unknown {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && 'value' in (value as Record<string, unknown>)
    ? (value as Record<string, unknown>).value
    : value;
}

/** Parse the pasted response of GET /notes?forum=<id>: finds the forum note
 * (the submission itself) and extracts title, abstract, pdf uri and authors.
 * Throws with a readable message when the JSON is not a notes response. */
function parseForumJson(text: string, forumId: string): ParsedForum {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error('JSON non valido: incolla la risposta completa della call.');
  }
  const notes = (data as { notes?: unknown }).notes;
  if (!Array.isArray(notes) || notes.length === 0) {
    throw new Error('Il JSON non contiene "notes": incolla la risposta di /notes?forum=<forum_id>.');
  }
  const forumNote = (notes.find((n) => n.id && (n.id === forumId || n.id === n.forum))
    ?? notes.find((n) => !n.replyto)
    ?? notes[0]) as { id?: unknown; forum?: unknown; content?: Record<string, unknown>; invitations?: unknown };
  const content = forumNote.content ?? {};
  const names = unwrapValue(content.authors);
  const ids = unwrapValue(content.authorids);
  const authors = Array.isArray(names)
    ? names.map((name, i) => ({
      name: String(name),
      profileId: Array.isArray(ids) && ids[i] != null ? String(ids[i]) : '',
    }))
    : [];
  const abstract = unwrapValue(content.abstract);
  const pdf = unwrapValue(content.pdf);
  return {
    forumId: String(forumNote.forum ?? forumNote.id ?? ''),
    title: String(unwrapValue(content.title) ?? ''),
    abstract: abstract ? String(abstract) : null,
    pdf: pdf ? String(pdf) : null,
    decision: extractDecision(notes),
    apiVersion: Array.isArray(forumNote.invitations) ? 'v2' : 'v1',
    noteCount: notes.length,
    authors,
    notes: notes as Record<string, unknown>[],
  };
}

/** The human decision from the forum's Decision note, when present. */
function extractDecision(notes: { invitation?: unknown; invitations?: unknown; content?: Record<string, unknown> }[]): string | null {
  for (const note of notes) {
    const invitation = (Array.isArray(note.invitations) ? note.invitations.join(' ') : String(note.invitation ?? '')).toLowerCase();
    if (!invitation.includes('decision')) continue;
    const content = note.content ?? {};
    const decision = unwrapValue(content.decision) ?? unwrapValue(content.recommendation);
    if (decision) return String(decision);
  }
  return null;
}

/** One editable author row in the upload form (position = row order). */
interface AuthorDraft {
  full_name: string;
  email: string;
  affiliation: string;
  openreview_profile_id: string;
}

const emptyAuthor = (): AuthorDraft => ({ full_name: '', email: '', affiliation: '', openreview_profile_id: '' });

/** Drafts -> request authors: rows without a name are dropped, order is kept. */
function toRequestAuthors(drafts: AuthorDraft[]): Author[] {
  return drafts
    .filter((a) => a.full_name.trim() !== '')
    .map((a, index) => ({
      full_name: a.full_name.trim(),
      email: a.email.trim() || null,
      affiliation: a.affiliation.trim() || null,
      openreview_profile_id: a.openreview_profile_id.trim() || null,
      position: index + 1,
    }));
}

function UploadPaperModal({ onClose }: { onClose: () => void }) {
  const { options: types, error: typesError } = useOptions(listPaperTypes);
  const [paperType, setPaperType] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [paperName, setPaperName] = useState('');
  const [description, setDescription] = useState('');
  const [authors, setAuthors] = useState<AuthorDraft[]>([]);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<PaperModel | null>(null);
  const [submitError, setSubmitError] = useState('');

  // OPEN_REVIEW mode: no file upload — conference + forum id + pasted notes JSON.
  const [conference, setConference] = useState(OPENREVIEW_CONFERENCES[0]);
  const [forumId, setForumId] = useState('');
  const [notesJson, setNotesJson] = useState('');
  const [notesError, setNotesError] = useState('');
  const [parsed, setParsed] = useState<ParsedForum | null>(null);

  const isOpenReview = paperType === 'OPEN_REVIEW';

  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!paperType && types.length > 0) setPaperType(types[0]);
  }, [types, paperType]);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function onFileChange(selected: File | null) {
    setResult(null);
    setSubmitError('');
    if (!selected) {
      setFile(null);
      setFileError('');
      return;
    }
    const allowed = isOpenReview ? ['pdf'] : ALLOWED_EXTENSIONS;
    if (!allowed.includes(extensionOf(selected.name))) {
      setFile(null);
      setFileError(isOpenReview ? 'Serve il PDF del paper (.pdf).' : 'Formato non supportato: scegli un file .pdf o .txt.');
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    // Real PDFs start with "%PDF": a saved OpenReview challenge page does not.
    if (extensionOf(selected.name) === 'pdf') {
      const head = new TextDecoder().decode(await selected.slice(0, 5).arrayBuffer());
      if (!head.startsWith('%PDF')) {
        setFile(null);
        setFileError('Il file non è un PDF valido — probabilmente è la pagina di verifica di OpenReview salvata come .pdf. Riapri il link e riscarica il paper.');
        if (fileRef.current) fileRef.current.value = '';
        return;
      }
    }
    setFile(selected);
    setFileError('');
    // Prefill the user-typed name from the file when still empty (OTHER flow).
    if (!isOpenReview) {
      setPaperName((prev) => prev.trim() === '' ? stemOf(selected.name) : prev);
    }
  }

  /** Parse the pasted JSON as the user types: preview + author prefill. */
  function onNotesJsonChange(text: string) {
    setNotesJson(text);
    setResult(null);
    setSubmitError('');
    if (!text.trim()) {
      setParsed(null);
      setNotesError('');
      return;
    }
    try {
      const forum = parseForumJson(text, forumId.trim());
      setParsed(forum);
      setNotesError('');
      if (forum.forumId) setForumId(forum.forumId);
    } catch (err) {
      setParsed(null);
      setNotesError(err instanceof Error ? err.message : String(err));
    }
  }

  function updateAuthor(index: number, patch: Partial<AuthorDraft>) {
    setAuthors((prev) => prev.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  }

  function removeAuthor(index: number) {
    setAuthors((prev) => prev.filter((_, i) => i !== index));
  }

  const canSubmitOpenReview = parsed !== null && forumId.trim() !== '' && parsed.title !== '' && file !== null;
  const canSubmitOther = file !== null && paperName.trim() !== '';

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    if (isOpenReview ? !canSubmitOpenReview : !canSubmitOther) return;

    setSaving(true);
    setResult(null);
    setSubmitError('');
    try {
      const saved = isOpenReview
        ? await createOpenreviewPaper({
          conference,
          forum_id: forumId.trim(),
          paper_name: parsed!.title,
          file_bytes: await fileToBase64(file!),
          authors: parsed!.authors.map((a, index) => ({
            full_name: a.name,
            openreview_profile_id: a.profileId || null,
            position: index + 1,
          })),
          human_decision: parsed!.decision,
          description: description.trim() || null,
          notes: parsed!.notes,
        })
        : await createPaper({
          paper: {
            paper_id: '',  // generated (uid) by the BE
            paper_name: paperName.trim(),
            paper_type: paperType as PaperModel['paper_type'],
            description: description.trim() || null,
          },
          file_name: file!.name,
          file_bytes: await fileToBase64(file!),
          authors: toRequestAuthors(authors),
        });
      setResult(saved);
      // Form stays open, reset for the next upload.
      setFile(null);
      setPaperName('');
      setDescription('');
      setAuthors([]);
      setForumId('');
      setNotesJson('');
      setParsed(null);
      if (fileRef.current) fileRef.current.value = '';
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--paper-upload"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-paper-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="upload-paper-title">Carica un nuovo paper</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <form className="paper-form paper-form--two-col" noValidate onSubmit={onSubmit}>
          {/* ── Left column: metadata ── */}
          <div className="paper-form__col">
            <label className="paper-form__label" htmlFor="paper-type">Tipo</label>
            <select
              className="paper-form__select"
              id="paper-type"
              value={paperType}
              disabled={saving}
              onChange={(e) => setPaperType(e.target.value)}
            >
              {typesError && <option value="">Error loading</option>}
              {!typesError && types.length === 0 && <option value="">Loading…</option>}
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>

            {!isOpenReview && (
              <>
                <label className="paper-form__label" htmlFor="paper-file">File (.pdf o .txt)</label>
                <input
                  ref={fileRef}
                  className="paper-form__file"
                  id="paper-file"
                  type="file"
                  accept=".pdf,.txt"
                  disabled={saving}
                  onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
                />
                {fileError && <p className="paper-form__error">{fileError}</p>}

                <label className="paper-form__label" htmlFor="paper-name">Nome paper</label>
                <input
                  className="paper-form__input"
                  id="paper-name"
                  type="text"
                  placeholder="nome leggibile del paper"
                  value={paperName}
                  disabled={saving}
                  onChange={(e) => setPaperName(e.target.value)}
                />
              </>
            )}

            {isOpenReview && (
              <>
                <label className="paper-form__label" htmlFor="paper-conference">Conference</label>
                <select
                  className="paper-form__select"
                  id="paper-conference"
                  value={conference}
                  disabled={saving}
                  onChange={(e) => setConference(e.target.value)}
                >
                  {OPENREVIEW_CONFERENCES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>

                <label className="paper-form__label" htmlFor="paper-forum-id">Forum id</label>
                <input
                  className="paper-form__input"
                  id="paper-forum-id"
                  type="text"
                  placeholder="es. H1lGHsA9KX"
                  value={forumId}
                  disabled={saving}
                  onChange={(e) => setForumId(e.target.value)}
                />

                <label className="paper-form__label" htmlFor="paper-or-pdf">PDF del paper</label>
                <input
                  ref={fileRef}
                  className="paper-form__file"
                  id="paper-or-pdf"
                  type="file"
                  accept=".pdf"
                  disabled={saving}
                  onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
                />
                {fileError && <p className="paper-form__error">{fileError}</p>}
                {parsed?.pdf && (
                  <p className="paper-form__preview">
                    <a
                      href={parsed.pdf.startsWith('http') ? parsed.pdf : `https://openreview.net${parsed.pdf}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Apri il PDF su OpenReview ↗
                    </a>
                    {' '}— scaricalo e caricalo qui (il server non può: bot protection).
                  </p>
                )}
              </>
            )}

            <label className="paper-form__label" htmlFor="paper-description">Descrizione (opzionale)</label>
            <textarea
              className="paper-form__textarea"
              id="paper-description"
              rows={3}
              maxLength={1000}
              placeholder="Breve descrizione del paper…"
              value={description}
              disabled={saving}
              onChange={(e) => setDescription(e.target.value)}
            />

          </div>

          {/* ── Right column: JSON (OPEN_REVIEW) or authors (OTHER) ── */}
          <div className="paper-form__col">
            {isOpenReview ? (
              <>
                <label className="paper-form__label" htmlFor="paper-notes-file">
                  Response JSON di <code>/notes?forum=&lt;forum_id&gt;&amp;limit=1000</code>
                </label>
                <input
                  className="paper-form__file"
                  id="paper-notes-file"
                  type="file"
                  accept=".json,application/json"
                  disabled={saving}
                  onChange={async (e) => {
                    const selected = e.target.files?.[0];
                    if (selected) onNotesJsonChange(await selected.text());
                  }}
                />
                <span className="acp__hint">oppure incolla qui sotto:</span>
                <textarea
                  className="paper-form__textarea paper-form__json"
                  id="paper-notes-json"
                  rows={8}
                  spellCheck={false}
                  placeholder={'{\n  "notes": [ ... ]\n}'}
                  value={notesJson}
                  disabled={saving}
                  onChange={(e) => onNotesJsonChange(e.target.value)}
                />
                {notesError && <p className="paper-form__error">{notesError}</p>}

                {parsed && (
                  <div className="paper-form__preview">
                    <p><strong>{parsed.title || '(titolo non trovato)'}</strong></p>
                    <p>
                      {parsed.noteCount} note · API {parsed.apiVersion}
                      {parsed.decision && <> · decision: <code>{parsed.decision}</code></>}
                      {parsed.pdf && <> · pdf: <code>{parsed.pdf}</code></>}
                    </p>
                    {parsed.authors.length > 0 && (
                      <p>
                        Autori (dalla response):{' '}
                        {parsed.authors.map((a) => a.name).join(', ')}
                      </p>
                    )}
                  </div>
                )}
              </>
            ) : (
              <>
                <span className="paper-form__label">Autori (opzionale, in ordine)</span>
                {authors.map((author, index) => (
                  <div className="paper-authors__row" key={index}>
                    <span className="paper-authors__position">{index + 1}.</span>
                    <input
                      className="paper-form__input"
                      type="text"
                      placeholder="nome e cognome *"
                      aria-label={`Autore ${index + 1}: nome`}
                      value={author.full_name}
                      disabled={saving}
                      onChange={(e) => updateAuthor(index, { full_name: e.target.value })}
                    />
                    <input
                      className="paper-form__input"
                      type="email"
                      placeholder="email"
                      aria-label={`Autore ${index + 1}: email`}
                      value={author.email}
                      disabled={saving}
                      onChange={(e) => updateAuthor(index, { email: e.target.value })}
                    />
                    <input
                      className="paper-form__input"
                      type="text"
                      placeholder="affiliazione"
                      aria-label={`Autore ${index + 1}: affiliazione`}
                      value={author.affiliation}
                      disabled={saving}
                      onChange={(e) => updateAuthor(index, { affiliation: e.target.value })}
                    />
                    <input
                      className="paper-form__input"
                      type="text"
                      placeholder="~OpenReview_Id1"
                      aria-label={`Autore ${index + 1}: profilo OpenReview`}
                      value={author.openreview_profile_id}
                      disabled={saving}
                      onChange={(e) => updateAuthor(index, { openreview_profile_id: e.target.value })}
                    />
                    <button
                      className="btn btn--ghost btn--sm paper-authors__remove"
                      type="button"
                      aria-label={`Rimuovi autore ${index + 1}`}
                      disabled={saving}
                      onClick={() => removeAuthor(index)}
                    >
                      ✕
                    </button>
                  </div>
                ))}
                <button
                  className="btn btn--ghost btn--sm paper-authors__add"
                  type="button"
                  disabled={saving}
                  onClick={() => setAuthors((prev) => [...prev, emptyAuthor()])}
                >
                  + Aggiungi autore
                </button>
              </>
            )}
          </div>

          <div className="paper-form__actions">
            <button
              className="btn btn--primary"
              type="submit"
              disabled={saving || (isOpenReview ? !canSubmitOpenReview : !canSubmitOther)}
            >
              {saving ? 'Salvataggio…' : 'Salva paper'}
            </button>
            {isOpenReview && !canSubmitOpenReview && !saving && (
              <span className="paper-form__preview">
                Servono JSON valido, forum id e il PDF per salvare.
              </span>
            )}
            {isOpenReview && saving && (
              <span className="paper-form__preview">
                Salvo paper, autori e cache delle review…
              </span>
            )}
          </div>
        </form>

        {submitError && <p className="paper-form__error">{submitError}</p>}

        {result && (
          <div className="card paper-result">
            <div className="card__header"><span className="card__title">Paper salvato</span></div>
            <div className="card__body"><pre>{JSON.stringify(result, null, 2)}</pre></div>
          </div>
        )}
        {result && (
          <p className="paper-form__preview">
            Indicizzazione (<code>full_context</code>, <code>bm25</code>, <code>embedding</code>) avviata in background.
          </p>
        )}
      </div>
    </div>
  );
}

function IndexPaperModal({ onClose }: { onClose: () => void }) {
  const { options: strategies, error: strategiesError } = useOptions(listRetrievalStrategies);
  const { options: paperIds, error: paperIdsError } = useOptions(listPaperIds);
  const [paperId, setPaperId] = useState('');
  const [strategy, setStrategy] = useState('');
  const [strategyVersion, setStrategyVersion] = useState('v1');
  const [force, setForce] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [result, setResult] = useState<IndexInfo | null>(null);
  const [submitError, setSubmitError] = useState('');

  // Stops the status polling when the modal unmounts.
  const aliveRef = useRef(true);
  useEffect(() => () => { aliveRef.current = false; }, []);

  useEffect(() => {
    if (!strategy && strategies.length > 0) setStrategy(strategies[0]);
  }, [strategies, strategy]);

  // Default to the first catalog paper once loaded.
  useEffect(() => {
    if (!paperId && paperIds.length > 0) setPaperId(paperIds[0]);
  }, [paperIds, paperId]);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const id = paperId.trim();
    const version = strategyVersion.trim() || 'v1';
    if (!id || indexing) return;

    setIndexing(true);
    setResult(null);
    setSubmitError('');
    try {
      // 202: the job runs in background — poll the status until the index shows up.
      await indexPaper({ paper_id: id, strategy: strategy as RagStrategy, strategy_version: version, force });

      let info: IndexInfo | null = null;
      for (let attempt = 0; attempt < INDEX_POLL_MAX_ATTEMPTS && aliveRef.current; attempt++) {
        await sleep(INDEX_POLL_INTERVAL_MS);
        info = await getIndexStatus(id, strategy as RagStrategy, version);
        if (info) break;
      }
      if (!aliveRef.current) return;
      if (info) setResult(info);
      else setSubmitError("L'indicizzazione è ancora in corso: ricontrolla più tardi (i PDF grossi richiedono minuti).");
    } catch (err) {
      if (aliveRef.current) setSubmitError(err instanceof ApiError ? err.message : String(err));
    } finally {
      if (aliveRef.current) setIndexing(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="index-paper-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="index-paper-title">Index paper</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <form className="paper-form" noValidate onSubmit={onSubmit}>
          <label className="paper-form__label" htmlFor="index-paper-id">Paper</label>
          <select
            className="paper-form__select"
            id="index-paper-id"
            value={paperId}
            disabled={indexing}
            onChange={(e) => setPaperId(e.target.value)}
          >
            {paperIdsError && <option value="">Error loading</option>}
            {!paperIdsError && paperIds.length === 0 && <option value="">Nessun paper nel catalogo</option>}
            {paperIds.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>

          <label className="paper-form__label" htmlFor="index-strategy">Strategia</label>
          <select
            className="paper-form__select"
            id="index-strategy"
            value={strategy}
            disabled={indexing}
            onChange={(e) => setStrategy(e.target.value)}
          >
            {strategiesError && <option value="">Error loading</option>}
            {!strategiesError && strategies.length === 0 && <option value="">Loading…</option>}
            {strategies.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          <label className="paper-form__label" htmlFor="index-version">Versione strategia</label>
          <input
            className="paper-form__input"
            id="index-version"
            type="text"
            value={strategyVersion}
            disabled={indexing}
            onChange={(e) => setStrategyVersion(e.target.value)}
          />

          <label className="paper-form__check">
            <input
              type="checkbox"
              checked={force}
              disabled={indexing}
              onChange={(e) => setForce(e.target.checked)}
            />
            Force reindex (ricostruisce anche se l'indice è aggiornato)
          </label>

          <div className="paper-form__actions">
            <button className="btn btn--primary" type="submit" disabled={indexing || !paperId.trim()}>
              {indexing ? 'Indicizzazione…' : 'Indicizza'}
            </button>
          </div>
        </form>

        {submitError && <p className="paper-form__error">{submitError}</p>}

        {result && (
          <div className="card paper-result">
            <div className="card__header"><span className="card__title">Indice creato</span></div>
            <div className="card__body"><pre>{JSON.stringify(result, null, 2)}</pre></div>
          </div>
        )}
      </div>
    </div>
  );
}

/** One labeled field inside the expanded paper panel (accordion style). */
function PaperField({ label, value }: { label: string; value: string }) {
  return (
    <div className="prompts__field">
      <span className="prompts__field-label">{label}</span>
      <span className="prompts__field-value">{value}</span>
    </div>
  );
}

function PaperListModal({ onClose }: { onClose: () => void }) {
  const [papers, setPapers] = useState<PaperModel[] | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listPapers()
      .then((rows) => { if (alive) setPapers(rows); })
      .catch((err) => { if (alive) setError(err instanceof ApiError ? err.message : String(err)); });
    return () => { alive = false; };
  }, []);

  // Close on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const visible = papers === null
    ? null
    : papers.filter((p) => {
      const query = search.trim().toLowerCase();
      return query === ''
        || p.paper_name.toLowerCase().includes(query)
        || (p.description ?? '').toLowerCase().includes(query)
        || (p.conference ?? '').toLowerCase().includes(query);
    });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal--full"
        role="dialog"
        aria-modal="true"
        aria-labelledby="paper-list-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="paper-list-title">Lista paper</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <div className="prompts__filters">
          <input
            className="paper-form__input prompts__filters-search"
            type="search"
            placeholder="cerca in nome, descrizione, conference…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {error && <p className="paper-form__error">{error}</p>}
        {!error && visible === null && <p className="paper-list__empty">Caricamento…</p>}
        {visible !== null && visible.length === 0 && (
          <p className="paper-list__empty">
            {search.trim() ? 'Nessun paper corrisponde alla ricerca.' : 'Nessun paper nel catalogo.'}
          </p>
        )}
        {visible !== null && visible.length > 0 && (
          <div className="paper-list__scroll">
            <table className="paper-list">
              <thead>
                <tr>
                  <th></th>
                  <th>nome</th>
                  <th>tipo</th>
                  <th>conference</th>
                  <th>decision</th>
                  <th>review</th>
                  <th>descrizione</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((paper) => (
                  <Fragment key={paper.paper_id}>
                    <tr
                      className={'prompts__row' + (expandedId === paper.paper_id ? ' prompts__row--open' : '')}
                      onClick={() => setExpandedId(expandedId === paper.paper_id ? null : paper.paper_id)}
                    >
                      <td className="rg-history__toggle">{expandedId === paper.paper_id ? '▾' : '▸'}</td>
                      <td className="paper-list__name">{paper.paper_name}</td>
                      <td>{paper.paper_type}</td>
                      <td>{paper.conference || '—'}</td>
                      <td>{paper.human_decision || '—'}</td>
                      <td>{paper.num_graph_review ?? 0}</td>
                      <td className="paper-list__desc">{paper.description || '—'}</td>
                    </tr>
                    {expandedId === paper.paper_id && (
                      <tr className="prompts__expand">
                        <td colSpan={7}>
                          <div className="prompts__fields">
                            <PaperField label="nome" value={paper.paper_name} />
                            <PaperField label="paper_id" value={paper.paper_id} />
                            <PaperField label="tipo" value={paper.paper_type} />
                            <PaperField label="conference" value={paper.conference || '—'} />
                            <PaperField label="forum OpenReview" value={paper.open_review_id || '—'} />
                            <PaperField label="api version" value={paper.openreview_api_version || '—'} />
                            <PaperField label="decision" value={paper.human_decision || '—'} />
                            <PaperField label="review eseguite" value={String(paper.num_graph_review ?? 0)} />
                          </div>
                          {paper.description && (
                            <>
                              <span className="prompts__field-label">descrizione</span>
                              <p className="prompts__field-value">{paper.description}</p>
                            </>
                          )}
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

export default function Paper() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [indexOpen, setIndexOpen] = useState(false);
  const [listOpen, setListOpen] = useState(false);

  return (
    <div className="section-wrap paper-section">
      <h2 className="section-title">Paper</h2>
      <p className="section-description">Gestione del catalogo paper.</p>

      <ActionCard
        title="Carica un nuovo paper"
        description={<>Aggiungi un file <code>.pdf</code> o <code>.txt</code> al catalogo, con tipo e descrizione.</>}
        actionLabel="Carica"
        onAction={() => setUploadOpen(true)}
      />

      <ActionCard
        title="Index paper"
        description={<>Indicizza un paper per il retrieval: strategia RAG e versione, con rebuild forzabile.</>}
        actionLabel="Indicizza"
        onAction={() => setIndexOpen(true)}
      />

      <ActionCard
        title="Lista paper"
        description={<>Elenco dei paper nel catalogo (dati dal DB).</>}
        actionLabel="Apri"
        onAction={() => setListOpen(true)}
      />

      {uploadOpen && <UploadPaperModal onClose={() => setUploadOpen(false)} />}
      {indexOpen && <IndexPaperModal onClose={() => setIndexOpen(false)} />}
      {listOpen && <PaperListModal onClose={() => setListOpen(false)} />}
    </div>
  );
}
