export function formatTimecode(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  const mmss = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours > 0 ? `${String(hours).padStart(2, "0")}:${mmss}` : mmss;
}

// The API sends raw base64 without the data: prefix; detect the format from its magic bytes.
export function toImageSrc(base64: string): string {
  const value = String(base64 ?? "").trim();
  if (value.startsWith("data:")) return value;
  let mime = "image/jpeg";
  if (value.startsWith("iVBOR")) mime = "image/png";
  else if (value.startsWith("R0lGOD")) mime = "image/gif";
  else if (value.startsWith("UklGR")) mime = "image/webp";
  return `data:${mime};base64,${value}`;
}
