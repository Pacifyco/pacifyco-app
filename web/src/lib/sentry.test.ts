import * as Sentry from "@sentry/react";
import { afterEach, describe, expect, test, vi } from "vitest";

vi.mock("@sentry/react", () => ({ init: vi.fn(), captureException: vi.fn() }));

// config reads import.meta.env when it's first imported, so load a fresh copy per test.
async function loadSentry(env: Record<string, string>) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
  vi.resetModules();
  return import("./sentry");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.mocked(Sentry.init).mockClear();
  vi.mocked(Sentry.captureException).mockClear();
});

describe("initSentry", () => {
  test("stays off without a DSN", async () => {
    const { initSentry } = await loadSentry({ VITE_SENTRY_DSN: "" });
    expect(initSentry()).toBe(false);
    expect(Sentry.init).not.toHaveBeenCalled();
  });

  test("with a DSN: errors only, tagged with the environment, no personal data", async () => {
    const { initSentry } = await loadSentry({
      VITE_SENTRY_DSN: "https://key@o1.ingest.de.sentry.io/1",
      VITE_ENVIRONMENT: "staging",
    });
    expect(initSentry()).toBe(true);
    const options = vi.mocked(Sentry.init).mock.calls[0]![0]!;
    expect(options).toMatchObject({
      dsn: "https://key@o1.ingest.de.sentry.io/1",
      environment: "staging",
      dataCollection: {
        userInfo: false,
        cookies: false,
        httpHeaders: false,
        httpBodies: [],
        urlQueryParams: false,
        stackFrameVariables: false,
      },
      tracesSampleRate: 0,
    });
    expect(options.integrations).toBeUndefined(); // no replay, feedback or extra integrations
  });
});

describe("reportRouteError", () => {
  test("reports crashes", async () => {
    const { reportRouteError } = await loadSentry({});
    const error = new Error("boom");
    reportRouteError(error);
    expect(Sentry.captureException).toHaveBeenCalledWith(error);
  });

  test("ignores expected responses like a 404", async () => {
    const { reportRouteError } = await loadSentry({});
    reportRouteError({ status: 404, statusText: "Not Found", internal: true, data: null });
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });
});
