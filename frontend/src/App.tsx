import { useRef } from "react";
import { Results } from "./components/Results";
import { ErrorAlert, IdleState, ProcessingState } from "./components/StatusViews";
import { UploadForm } from "./components/UploadForm";
import { useVideoAnalysis } from "./useVideoAnalysis";

export default function App() {
  const { state, error, setError, start } = useVideoAnalysis();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  function seekTo(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, seconds);
    video.scrollIntoView({ behavior: "smooth", block: "center" });
    video.play().catch(() => {});
  }

  return (
    <>
      <header className="app-header py-4 mb-4">
        <div className="container">
          <h1 className="h3 mb-1">Видеоаналитика кассовой дисциплины</h1>
          <p className="mb-0 opacity-75">
            Загрузите запись с камеры — AI-сервис найдёт нарушения и покажет таймкоды с кадрами.
          </p>
        </div>
      </header>

      <main className="container pb-5">
        <div className="row g-4">
          <div className="col-lg-4">
            <UploadForm busy={state.phase === "processing"} onSubmit={start} onValidationError={setError} />
          </div>
          <div className="col-lg-8">
            {error && <ErrorAlert message={error} onClose={() => setError(null)} />}
            {state.phase === "idle" && <IdleState />}
            {state.phase === "processing" && (
              <ProcessingState fileName={state.fileName} jobId={state.jobId} elapsedSec={state.elapsedSec} />
            )}
            {state.phase === "result" && (
              <Results outcome={state.outcome} file={state.file} videoRef={videoRef} onSeek={seekTo} />
            )}
          </div>
        </div>
      </main>
    </>
  );
}
