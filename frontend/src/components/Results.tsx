import { useEffect, useState, type RefObject } from "react";
import type { AnalysisOutcome, Violation } from "../api";
import { formatTimecode } from "../format";
import { FrameGallery } from "./FrameGallery";

interface ViolationCardProps {
  violation: Violation;
  index: number;
  onSeek: (seconds: number) => void;
}

function ViolationCard({ violation, index, onSeek }: ViolationCardProps) {
  return (
    <div className="card app-card violation-card">
      <div className="card-header bg-white d-flex align-items-center gap-3 py-3">
        <button
          type="button"
          className="btn btn-outline-danger btn-sm timecode-btn"
          title="Перейти к моменту в видео"
          onClick={() => onSeek(violation.timecodeSec)}
        >
          {formatTimecode(violation.timecodeSec)}
        </button>
        <h3 className="h6 mb-0 flex-grow-1">{violation.type}</h3>
        <span className="badge text-bg-light text-body-secondary">#{index + 1}</span>
      </div>
      <div className="card-body">
        <p className="mb-2">{violation.description || "Описание не передано."}</p>
        {violation.ruleRef && <p className="small text-body-secondary mb-3">Основание: {violation.ruleRef}</p>}
        <h4 className="h6 text-uppercase small text-body-secondary mb-2">Кадры</h4>
        <FrameGallery frames={violation.frames} violationType={violation.type} />
      </div>
    </div>
  );
}

interface VideoPreviewProps {
  file: File;
  videoRef: RefObject<HTMLVideoElement | null>;
}

// Some browsers cannot decode every .mov codec; the player is hidden rather than shown broken.
function VideoPreview({ file, videoRef }: VideoPreviewProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [playable, setPlayable] = useState(true);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    setPlayable(true);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  if (!url || !playable) return null;
  return (
    <div className="card app-card mb-4">
      <div className="card-body">
        <video
          ref={videoRef}
          className="preview-video"
          src={url}
          controls
          preload="metadata"
          onError={() => setPlayable(false)}
        />
        <p className="small text-body-secondary mt-2 mb-0">
          Нажмите на таймкод в карточке, чтобы перейти к моменту нарушения.
        </p>
      </div>
    </div>
  );
}

interface ResultsProps {
  outcome: AnalysisOutcome;
  file: File;
  videoRef: RefObject<HTMLVideoElement | null>;
  onSeek: (seconds: number) => void;
}

export function Results({ outcome, file, videoRef, onSeek }: ResultsProps) {
  if (outcome.verdict === "no_violation") {
    return (
      <>
        <div className="verdict-banner verdict-ok mb-4">✅ Нарушений не обнаружено</div>
        <VideoPreview file={file} videoRef={videoRef} />
      </>
    );
  }

  const violations = [...outcome.violations].sort((a, b) => a.timecodeSec - b.timecodeSec);
  return (
    <>
      <div className="verdict-banner verdict-bad mb-4">
        <div>⚠️ Обнаружены нарушения кассовой дисциплины</div>
        <div className="fs-6 fw-normal mt-1">
          {violations.length ? `Найдено нарушений: ${violations.length}` : "Детали нарушений не переданы сервером."}
        </div>
      </div>
      <VideoPreview file={file} videoRef={videoRef} />
      <div className="d-flex flex-column gap-3">
        {violations.map((v, i) => (
          <ViolationCard key={`${v.timecodeSec}-${i}`} violation={v} index={i} onSeek={onSeek} />
        ))}
      </div>
    </>
  );
}
