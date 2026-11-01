import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "react-router";
import wordmarkReversedUrl from "../assets/brand/wordmark-reversed.png";
import wordmarkUrl from "../assets/brand/wordmark.png";
import { useAuth } from "../auth/AuthProvider";
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
          <div className="flex items-center gap-4">
            <AccountLink />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 py-6 sm:px-5 sm:py-7">
        <Outlet />
      </main>

      <footer className="border-t border-line px-4 py-4 sm:px-5">
        <nav aria-label="Legal" className="mx-auto flex max-w-content flex-wrap justify-center gap-5 text-small">
          <Link to="/terms/parent">Family Terms of Use</Link>
          <Link to="/terms/sitter">Sitter Terms of Use</Link>
          <Link to="/privacy">Privacy policy</Link>
        </nav>
      </footer>
      {config.environment !== "production" && <EnvironmentFooter />}
    </div>
  );
}

function AccountLink() {
  const { status, available, signOut } = useAuth();
  if (status === "signed_in") {
    return (
      <button type="button" onClick={signOut} className="text-ui text-coral-deep underline-offset-4 hover:underline">
        Sign out
      </button>
    );
  }
  if (status === "signed_out" && available) {
    return (
      <Link to="/sign-in" className="text-ui">
        Sign in
      </Link>
    );
  }
  return null;
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
