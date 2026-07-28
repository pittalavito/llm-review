/** Paper section — create a new paper: pick a .pdf/.txt file, choose the type,
 * optional description. The file travels base64-encoded inside
 * CreatePaperRequest (POST /paper/create); the backend derives the paper_id
 * (<paper-type>_<name>_<extension>) and stores row + file under it. */
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, createPaper, listPaperTypes } from '../api/client';
import type { Paper as PaperModel } from '../api/types';
import { useOptions } from '../components/useOptions';

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

export default function Paper() {
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
    <div className="section-wrap paper-section">
      <h2 className="section-title">Paper</h2>
      <p className="section-description">
        Carica un nuovo paper (<code>.pdf</code> o <code>.txt</code>) nel catalogo.
      </p>

      <form className="paper-form" noValidate onSubmit={onSubmit}>
        <label className="paper-form__label" htmlFor="paper-file">File</label>
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
    </div>
  );
}
