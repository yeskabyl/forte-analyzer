import { useState, type FormEvent } from "react";
import { apiBaseLabel } from "../api";

interface Props {
  busy: boolean;
  onSubmit: (file: File, apiKey: string) => void;
  onValidationError: (message: string) => void;
}

export function UploadForm({ busy, onSubmit, onValidationError }: Props) {
  const [apiKey, setApiKey] = useState("forte2026");
  const [file, setFile] = useState<File | null>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const key = apiKey.trim();
    if (!key) return onValidationError("Укажите X-API-Key.");
    if (!file) return onValidationError("Выберите видеофайл.");
    if (!file.name.toLowerCase().endsWith(".mov")) {
      return onValidationError("Поддерживаются только файлы формата .mov.");
    }
    onSubmit(file, key);
  }

  return (
    <div className="card app-card">
      <div className="card-body p-4">
        <h2 className="h5 mb-3">Загрузка видео</h2>
        <form onSubmit={handleSubmit} noValidate>
          <fieldset disabled={busy}>
            <div className="mb-3">
              <label htmlFor="api-key" className="form-label">
                X-API-Key
              </label>
              <input
                id="api-key"
                type="text"
                className="form-control"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <div className="mb-3">
              <label htmlFor="video-file" className="form-label">
                Видеофайл (.mov)
              </label>
              <input
                id="video-file"
                type="file"
                className="form-control"
                accept=".mov,video/quicktime"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            <button type="submit" className="btn btn-danger btn-lg w-100">
              {busy && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
              {busy ? "Обработка..." : "Анализировать видео"}
            </button>
          </fieldset>
        </form>
        <p className="small text-body-secondary mt-3 mb-0">
          Сервер: <code>{apiBaseLabel()}</code>
        </p>
      </div>
    </div>
  );
}
