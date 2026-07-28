/** Paper section — action cards in the Admin style. "Carica un nuovo paper"
 * opens a modal with the upload form: .pdf/.txt file, type, optional
 * description. The file travels base64-encoded inside CreatePaperRequest
 * (POST /paper/create); the backend derives the paper_id
 * (<paper-type>_<name>_<extension>) and stores row + file under it.
 * List/detail cards are TODO placeholders for the upcoming endpoints. */
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { ApiError, createPaper, getIndexStatus, indexPaper, listPaperTypes, listRetrievalStrategies } from '../api/client';
import type { IndexInfo, Paper as PaperModel, RagStrategy } from '../api/types';
import { useOptions } from '../components/useOptions';

const INDEX_POLL_INTERVAL_MS = 2000;
const INDEX_POLL_MAX_ATTEMPTS = 150; // ~5 minutes

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const ALLOWED_EXTENSIONS = ['pdf', 'txt'];

/** Extension of a file name, lowercased ("" when absent). */
function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot + 1).toLowerCase();
}

/** Mirror of the backend build_paper_id: <paper-type>_<stem>_<extension>. */
function previewPaperId(paperType: string, fileName: string): string {
  const dot = fileName.lastIndexOf('.');
  const stem = dot === -1 ? fileName : fileName.slice(0, dot);
  const ext = extensionOf(fileName);
  const parts = [paperType.toLowerCase(), stem];
  if (ext) parts.push(ext);
  return parts.join('_');
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

interface ActionCardProps {
  title: string;
  description: ReactNode;
  actionLabel: string;
  onAction?: () => void;
}

function ActionCard({ title, description, actionLabel, onAction }: ActionCardProps) {
  return (
    <section className="admin-card">
      <div className="admin-card__info">
        <h3 className="admin-card__title">
          {title}
          {!onAction && <span className="badge badge--todo">TODO</span>}
        </h3>
        <p className="admin-card__desc">{description}</p>
      </div>
      <button
        className="btn btn--primary admin-card__btn"
        type="button"
        disabled={!onAction}
        onClick={onAction}
      >
        {actionLabel}
      </button>
    </section>
  );
}

function UploadPaperModal({ onClose }: { onClose: () => void }) {
  const { options: types, error: typesError } = useOptions(listPaperTypes);
  const [paperType, setPaperType] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<PaperModel | null>(null);
  const [submitError, setSubmitError] = useState('');

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

  function onFileChange(selected: File | null) {
    setResult(null);
    setSubmitError('');
    if (!selected) {
      setFile(null);
      setFileError('');
      return;
    }
    if (!ALLOWED_EXTENSIONS.includes(extensionOf(selected.name))) {
      setFile(null);
      setFileError('Formato non supportato: scegli un file .pdf o .txt.');
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    setFile(selected);
    setFileError('');
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || saving) return;

    setSaving(true);
    setResult(null);
    setSubmitError('');
    try {
      const saved = await createPaper({
        paper: {
          paper_id: previewPaperId(paperType, file.name),
          paper_name: file.name,
          paper_type: paperType as PaperModel['paper_type'],
          description: description.trim() || null,
        },
        file_bytes: await fileToBase64(file),
      });
      setResult(saved);
      // Form stays open, reset for the next upload.
      setFile(null);
      setDescription('');
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
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-paper-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 className="modal__title" id="upload-paper-title">Carica un nuovo paper</h3>
          <button className="modal__close" type="button" aria-label="Chiudi" onClick={onClose}>✕</button>
        </div>

        <form className="paper-form" noValidate onSubmit={onSubmit}>
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

          {file && (
            <p className="paper-form__preview">
              paper_id: <code>{previewPaperId(paperType, file.name)}</code>
            </p>
          )}

          <div className="paper-form__actions">
            <button className="btn btn--primary" type="submit" disabled={saving || !file}>
              {saving ? 'Salvataggio…' : 'Salva paper'}
            </button>
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
            Indicizzazione <code>full_context</code> avviata in background.
          </p>
        )}
      </div>
    </div>
  );
}

function IndexPaperModal({ onClose }: { onClose: () => void }) {
  const { options: strategies, error: strategiesError } = useOptions(listRetrievalStrategies);
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
          <label className="paper-form__label" htmlFor="index-paper-id">Paper id</label>
          <input
            className="paper-form__input"
            id="index-paper-id"
            type="text"
            placeholder="es. other_attention_pdf"
            autoComplete="off"
            value={paperId}
            disabled={indexing}
            onChange={(e) => setPaperId(e.target.value)}
          />

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

export default function Paper() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [indexOpen, setIndexOpen] = useState(false);

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
        description={<>Elenco dei paper nel catalogo — in preparazione.</>}
        actionLabel="Apri"
      />

      <ActionCard
        title="Dettaglio paper"
        description={<>Scheda di un paper per id — in preparazione.</>}
        actionLabel="Apri"
      />

      {uploadOpen && <UploadPaperModal onClose={() => setUploadOpen(false)} />}
      {indexOpen && <IndexPaperModal onClose={() => setIndexOpen(false)} />}
    </div>
  );
}
