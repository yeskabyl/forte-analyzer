interface ErrorAlertProps {
  message: string;
  onClose: () => void;
}

export function ErrorAlert({ message, onClose }: ErrorAlertProps) {
  return (
    <div className="alert alert-danger alert-dismissible shadow-sm" role="alert">
      <strong>Ошибка: </strong>
      {message}
      <button type="button" className="btn-close" aria-label="Закрыть" onClick={onClose} />
    </div>
  );
}

export function IdleState() {
  return (
    <div className="card app-card">
      <div className="card-body p-5 text-center text-body-secondary">
        <div className="display-6 mb-2">🎥</div>
        <p className="mb-0">Выберите .mov файл и нажмите «Анализировать видео».</p>
      </div>
    </div>
  );
}

interface ProcessingStateProps {
  fileName: string;
  jobId?: string;
  elapsedSec: number;
}

export function ProcessingState({ fileName, jobId, elapsedSec }: ProcessingStateProps) {
  const details = jobId ? `Задача ${jobId} · прошло ${elapsedSec} с` : `Загрузка файла «${fileName}»...`;
  return (
    <div className="card app-card">
      <div className="card-body processing-box text-center">
        <div className="spinner-border text-danger mb-4" role="status">
          <span className="visually-hidden">Загрузка…</span>
        </div>
        <p className="h5 mb-2">Анализ видео, пожалуйста подождите...</p>
        <p className="text-body-secondary small mb-0">{details}</p>
      </div>
    </div>
  );
}
