import { useCallback, useEffect, useRef, useState } from "react";
import { isAbort, normalizeJob, pollJob, uploadVideo, type AnalysisOutcome } from "./api";

export type AnalysisState =
  | { phase: "idle" }
  | { phase: "processing"; fileName: string; jobId?: string; elapsedSec: number }
  | { phase: "result"; outcome: AnalysisOutcome; file: File };

export function useVideoAnalysis() {
  const [state, setState] = useState<AnalysisState>({ phase: "idle" });
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Stop polling if the component unmounts mid-analysis.
  useEffect(() => () => abortRef.current?.abort(), []);

  const start = useCallback(async (file: File, apiKey: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setError(null);
    setState({ phase: "processing", fileName: file.name, elapsedSec: 0 });
    try {
      const jobId = await uploadVideo(file, apiKey, controller.signal);
      setState({ phase: "processing", fileName: file.name, jobId, elapsedSec: 0 });
      const data = await pollJob(jobId, apiKey, controller.signal, (elapsedSec) =>
        setState({ phase: "processing", fileName: file.name, jobId, elapsedSec })
      );
      const outcome = normalizeJob(data);
      if (!outcome) throw new Error("Сервер вернул результат в неизвестном формате.");
      setState({ phase: "result", outcome, file });
    } catch (err) {
      if (isAbort(err)) return;
      setState({ phase: "idle" });
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  return { state, error, setError, start };
}
