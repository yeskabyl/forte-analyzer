import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// jsdom implements neither object URLs nor media playback.
URL.createObjectURL = () => "blob:mock";
URL.revokeObjectURL = () => {};
