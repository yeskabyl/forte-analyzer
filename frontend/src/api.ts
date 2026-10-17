// REST client for the video analysis backend.

export type Verdict = "violation" | "no_violation";

export interface EvidenceFrame {
  timestamp_sec: number;
  image_base64: string;
}

export interface Violation {
  type: string;
  timecodeSec: number;
  description: string;
  ruleRef: string;
  frames: EvidenceFrame[];
}

export interface AnalysisOutcome {
  verdict: Verdict;
  violations: Violation[];
}

// Schema from the frontend spec.
interface SpecViolation {
  type?: string;
  timecode_sec?: number;
  description?: string;
  rule_ref?: string;
  evidence_frames?: EvidenceFrame[];
}

// Schema returned by the forte-video-analyzer backend.
interface BackendEvent {
  event_sec?: number;
  type_key?: string;
  name_ru?: string;
  desc_ru?: string;
  rule_ref?: string;
  evidence_frames?: EvidenceFrame[];
}

export interface JobResponse {
  job_id: string;
  status: "processing" | "done" | "failed";
  error?: string | null;
  verdict?: string;
  violations?: SpecViolation[];
  result?: { violation?: boolean; events?: BackendEvent[] } | null;
}

// Empty base = same origin; the Vite dev server and nginx proxy /api to the backend.
// Override at runtime with ?api=http://host:port or at build time with VITE_API_BASE_URL.
export const API_BASE_URL = (
  new URLSearchParams(window.location.search).get("api") ??
  import.meta.env.VITE_API_BASE_URL ??
  ""
).replace(/\/+$/, "");

export const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;
const MAX_NETWORK_RETRIES = 3;

const KNOWN_HTTP_ERRORS: Record<number, string> = {
  401: "Неверный или отсутствующий API-ключ.",
  404: "Задача не найдена на сервере.",
  413: "Файл слишком большой.",
  415: "Неподдерживаемый формат файла.",
  503: "Сервер временно недоступен.",
};

export function apiBaseLabel(): string {
  return API_BASE_URL || `${window.location.origin} (прокси)`;
}

async function errorFromResponse(res: Response): Promise<Error> {
  const known = KNOWN_HTTP_ERRORS[res.status];
  if (known) return new Error(known);
  let detail = "";
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).join("; ");
    else if (body.error) detail = String(body.error);
  } catch {
    // Non-JSON error body; the status code alone is reported.
  }
  return new Error(`Ошибка сервера (HTTP ${res.status}).${detail ? ` ${detail}` : ""}`);
}

function networkError(): Error {
  return new Error(
    `Не удалось подключиться к серверу ${apiBaseLabel()}. Проверьте, что бэкенд запущен и для этой страницы разрешён CORS.`
  );
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true }
    );
  });
}

export async function uploadVideo(file: File, apiKey: string, signal: AbortSignal): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
      method: "POST",
      headers: { "X-API-Key": apiKey },
      body: formData,
      signal,
    });
  } catch (err) {
    if (isAbort(err)) throw err;
    throw networkError();
  }
  if (!res.ok) throw await errorFromResponse(res);
  const data = await res.json();
  if (!data.job_id) throw new Error("Сервер не вернул job_id.");
  return data.job_id;
}

/** Polls the job every POLL_INTERVAL_MS until it is done; throws on failure. */
export async function pollJob(
  jobId: string,
  apiKey: string,
  signal: AbortSignal,
  onTick: (elapsedSec: number) => void
): Promise<JobResponse> {
  const startedAt = Date.now();
  let networkFailures = 0;
  for (;;) {
    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}`, {
        headers: { "X-API-Key": apiKey },
        signal,
      });
    } catch (err) {
      if (isAbort(err)) throw err;
      networkFailures += 1;
      if (networkFailures > MAX_NETWORK_RETRIES) throw networkError();
      await sleep(POLL_INTERVAL_MS, signal);
      continue;
    }
    networkFailures = 0;
    if (!res.ok) throw await errorFromResponse(res);

    const data: JobResponse = await res.json();
    if (data.status === "done") return data;
    if (data.status === "failed") {
      throw new Error(data.error ? `Обработка не удалась: ${data.error}` : "Обработка видео завершилась с ошибкой.");
    }
    if (data.status !== "processing") throw new Error(`Неизвестный статус задачи: ${String(data.status)}`);

    const elapsedMs = Date.now() - startedAt;
    if (elapsedMs > POLL_TIMEOUT_MS) throw new Error("Превышено время ожидания результата.");
    onTick(Math.round(elapsedMs / 1000));
    await sleep(POLL_INTERVAL_MS, signal);
  }
}

/** Maps either response schema to one shape; null if the verdict is unrecognised. */
export function normalizeJob(data: JobResponse): AnalysisOutcome | null {
  if (data.verdict !== undefined || Array.isArray(data.violations)) {
    if (data.verdict !== "violation" && data.verdict !== "no_violation") return null;
    return {
      verdict: data.verdict,
      violations: (data.violations ?? []).map((v) => ({
        type: v.type || "Нарушение",
        timecodeSec: Number(v.timecode_sec) || 0,
        description: v.description ?? "",
        ruleRef: v.rule_ref ?? "",
        frames: Array.isArray(v.evidence_frames) ? v.evidence_frames : [],
      })),
    };
  }
  if (data.result && typeof data.result === "object") {
    return {
      verdict: data.result.violation ? "violation" : "no_violation",
      violations: (data.result.events ?? []).map((e) => ({
        type: e.name_ru || e.type_key || "Нарушение",
        timecodeSec: Number(e.event_sec) || 0,
        description: e.desc_ru ?? "",
        ruleRef: e.rule_ref ?? "",
        frames: Array.isArray(e.evidence_frames) ? e.evidence_frames : [],
      })),
    };
  }
  return null;
}

export { isAbort };
