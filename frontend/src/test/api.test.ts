import { describe, expect, it } from "vitest";
import { normalizeJob } from "../api";
import { formatTimecode, toImageSrc } from "../format";

describe("formatTimecode", () => {
  it("formats mm:ss and hh:mm:ss", () => {
    expect(formatTimecode(44.2)).toBe("00:44");
    expect(formatTimecode(0)).toBe("00:00");
    expect(formatTimecode(3725)).toBe("01:02:05");
  });
});

describe("toImageSrc", () => {
  it("detects the image type from base64 magic bytes", () => {
    expect(toImageSrc("iVBORw0KGgo")).toBe("data:image/png;base64,iVBORw0KGgo");
    expect(toImageSrc("/9j/4AAQ")).toBe("data:image/jpeg;base64,/9j/4AAQ");
    expect(toImageSrc("data:image/gif;base64,R0lG")).toBe("data:image/gif;base64,R0lG");
  });
});

describe("normalizeJob", () => {
  it("maps the spec schema", () => {
    const out = normalizeJob({
      job_id: "1",
      status: "done",
      verdict: "violation",
      violations: [
        {
          type: "Оставление наличных без присмотра",
          timecode_sec: 44.2,
          description: "d",
          evidence_frames: [{ timestamp_sec: 44.2, image_base64: "x" }],
        },
      ],
    });
    expect(out?.verdict).toBe("violation");
    expect(out?.violations[0]).toMatchObject({ type: "Оставление наличных без присмотра", timecodeSec: 44.2 });
    expect(out?.violations[0].frames).toHaveLength(1);
  });

  it("maps the forte-video-analyzer backend schema", () => {
    const out = normalizeJob({
      job_id: "1",
      status: "done",
      result: {
        violation: true,
        events: [{ event_sec: 20, name_ru: "Уход с рабочего места", desc_ru: "d", rule_ref: "НБРК № 48" }],
      },
    });
    expect(out).toEqual({
      verdict: "violation",
      violations: [{ type: "Уход с рабочего места", timecodeSec: 20, description: "d", ruleRef: "НБРК № 48", frames: [] }],
    });
  });

  it("rejects unknown shapes", () => {
    expect(normalizeJob({ job_id: "1", status: "done" })).toBeNull();
    expect(normalizeJob({ job_id: "1", status: "done", verdict: "maybe" })).toBeNull();
  });
});
