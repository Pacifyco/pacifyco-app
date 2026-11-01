import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "react-router";
import wordmarkReversedUrl from "../assets/brand/wordmark-reversed.png";
import wordmarkUrl from "../assets/brand/wordmark.png";
import { config } from "../config";
import { apiFetch } from "../lib/api";
import { ThemeToggle } from "../theme/ThemeToggle";

type Health = { status: string; environment: string };

export function AppLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface-raised">
        <div className="mx-auto flex max-w-content items-center justify-between gap-4 px-4 py-3 sm:px-5">
          {/* Wordmark: 24px tall on phones, 28px on desktop; reversed version in dark mode (design.md
              section 6). PNG copies of the supplied files (sources in /assets); swap for SVGs when supplied. */}
          <Link to="/" aria-label="Pacify home" className="inline-flex shrink-0 py-1 no-underline">
            <img src={wordmarkUrl} alt="" width={426} height={112} className="h-6 w-auto sm:h-7 dark:hidden" />
            <img
              src={wordmarkReversedUrl}
              alt=""
              width={426}
              height={112}
              className="hidden h-6 w-auto sm:h-7 dark:block"
            />
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 py-6 sm:px-5 sm:py-7">
        <Outlet />
      </main>

      {config.environment !== "production" && <EnvironmentFooter />}
    </div>
  );
}

// Shown outside production only: which environment this is and whether the API answers.
function EnvironmentFooter() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<Health>("/health"),
    retry: false,
  });

  const apiStatus = health.isPending ? "checking" : health.isSuccess ? "connected" : "not reachable";

  return (
    <footer className="border-t border-line px-4 py-3 text-caption text-muted sm:px-5">
      <p className="mx-auto max-w-content">
        Environment: {config.environment} · API: {apiStatus}
      </p>
    </footer>
  );
}
