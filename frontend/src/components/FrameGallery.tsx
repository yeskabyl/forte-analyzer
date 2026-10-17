import { useEffect, useState } from "react";
import type { EvidenceFrame } from "../api";
import { formatTimecode, toImageSrc } from "../format";

interface Props {
  frames: EvidenceFrame[];
  violationType: string;
}

export function FrameGallery({ frames, violationType }: Props) {
  const [selected, setSelected] = useState<EvidenceFrame | null>(null);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null);
    document.addEventListener("keydown", onKey);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("modal-open");
    };
  }, [selected]);

  if (frames.length === 0) {
    return <p className="small text-body-secondary fst-italic mb-0">Кадры-доказательства не переданы.</p>;
  }

  return (
    <>
      <div className="row g-2">
        {frames.map((frame, i) => {
          const ts = formatTimecode(frame.timestamp_sec);
          return (
            <div className="col-6 col-md-4" key={i}>
              <figure className="mb-0">
                <img
                  className="evidence-thumb rounded border"
                  src={toImageSrc(frame.image_base64)}
                  alt={`Кадр ${ts}`}
                  loading="lazy"
                  onClick={() => setSelected(frame)}
                />
                <figcaption className="small text-body-secondary text-center mt-1">{ts}</figcaption>
              </figure>
            </div>
          );
        })}
      </div>

      {selected && (
        <>
          <div
            className="modal fade show d-block"
            role="dialog"
            aria-modal="true"
            aria-label="Кадр-доказательство"
            onClick={() => setSelected(null)}
          >
            <div className="modal-dialog modal-xl modal-dialog-centered" onClick={(e) => e.stopPropagation()}>
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">
                    {violationType} — {formatTimecode(selected.timestamp_sec)}
                  </h5>
                  <button type="button" className="btn-close" aria-label="Закрыть" onClick={() => setSelected(null)} />
                </div>
                <div className="modal-body text-center bg-dark">
                  <img className="img-fluid" src={toImageSrc(selected.image_base64)} alt="Кадр-доказательство" />
                </div>
              </div>
            </div>
          </div>
          <div className="modal-backdrop fade show" />
        </>
      )}
    </>
  );
}
