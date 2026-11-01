import * as Sentry from "@sentry/react";
import { isRouteErrorResponse } from "react-router";
import { config } from "../config";

/** Turn on Sentry only when VITE_SENTRY_DSN is set. Errors only: no tracing, replay, logs or feedback. */
export function initSentry(): boolean {
  if (!config.sentryDsn) return false;
  Sentry.init({
    dsn: config.sentryDsn,
    environment: config.environment,
    // Collect nothing about parents, children or sitters beyond the error itself. (The Sentry org also
    // refuses to store IP addresses and scrubs passwords and card numbers server-side.)
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
  return true;
}

/** Report a crash from a route's error page. Expected responses (like a 404) aren't crashes. */
export function reportRouteError(error: unknown): void {
  if (isRouteErrorResponse(error) && error.status < 500) return;
  Sentry.captureException(error);
}
