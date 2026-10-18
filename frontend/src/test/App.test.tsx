import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "../App";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function submit(fileName = "clip.mov") {
  render(<App />);
  const file = new File(["video"], fileName, { type: "video/quicktime" });
  fireEvent.change(screen.getByLabelText("Видеофайл (.mov)"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Анализировать видео" }));
}

describe("App", () => {
  it("uploads, polls and renders violations", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ job_id: "3f2a9c1e" }))
      .mockResolvedValueOnce(jsonResponse({ job_id: "3f2a9c1e", status: "processing" }))
      .mockResolvedValueOnce(
        jsonResponse({
          job_id: "3f2a9c1e",
          status: "done",
          verdict: "violation",
          violations: [
            {
              type: "Оставление наличных без присмотра",
              timecode_sec: 44.2,
              description: "Сотрудник покинул рабочую зону...",
              evidence_frames: [{ timestamp_sec: 44.2, image_base64: "iVBORw0KGgo" }],
            },
          ],
        })
      );
    vi.stubGlobal("fetch", fetchMock);

    submit();
    expect(await screen.findByText("Анализ видео, пожалуйста подождите...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обработка..." })).toBeDisabled();

    expect(await screen.findByText("⚠️ Обнаружены нарушения кассовой дисциплины", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "00:44" })).toBeInTheDocument();
    expect(screen.getByAltText("Кадр 00:44")).toHaveAttribute("src", "data:image/png;base64,iVBORw0KGgo");

    const [uploadUrl, uploadInit] = fetchMock.mock.calls[0];
    expect(uploadUrl).toBe("/api/v1/analyze");
    expect(uploadInit.headers).toEqual({ "X-API-Key": "forte2026" });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/jobs/3f2a9c1e");

    fireEvent.click(screen.getByAltText("Кадр 00:44"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  }, 10000);

  it("shows the green banner when there are no violations", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ job_id: "a" }))
        .mockResolvedValueOnce(jsonResponse({ job_id: "a", status: "done", verdict: "no_violation", violations: [] }))
    );
    submit();
    expect(await screen.findByText("✅ Нарушений не обнаружено")).toBeInTheDocument();
  });

  it("shows an error and unlocks the form when the job fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ job_id: "a" }))
        .mockResolvedValueOnce(jsonResponse({ job_id: "a", status: "failed", error: "codec not supported" }))
    );
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("codec not supported");
    expect(screen.getByRole("button", { name: "Анализировать видео" })).toBeEnabled();
  });

  it("reports HTTP 401 as an invalid key", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse({ detail: "Invalid or missing API key" }, 401)));
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Неверный или отсутствующий API-ключ.");
  });

  it("explains a missing backend when the host has no /api route", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("Not Found", { status: 404 })));
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Бэкенд не найден");
    expect(screen.getByRole("button", { name: "Анализировать видео" })).toBeEnabled();
  });

  it("rejects non-.mov files without calling the API", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    submit("clip.mp4");
    expect(screen.getByRole("alert")).toHaveTextContent(".mov");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
