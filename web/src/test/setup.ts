import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// jsdom has no matchMedia. This fake lets tests flip the OS colour scheme with setSystemDark().
type Listener = (event: MediaQueryListEvent) => void;
let systemDark = false;
const listeners = new Set<Listener>();

export function setSystemDark(dark: boolean): void {
  systemDark = dark;
  for (const listener of listeners) listener({ matches: dark } as MediaQueryListEvent);
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    get matches() {
      return query.includes("dark") ? systemDark : false;
    },
    media: query,
    addEventListener: (_: string, listener: Listener) => listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => listeners.delete(listener),
  }),
});

beforeEach(() => {
  systemDark = false;
  listeners.clear();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  // No real network in tests; each test stubs fetch when it needs the API.
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fetch not stubbed"))));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
