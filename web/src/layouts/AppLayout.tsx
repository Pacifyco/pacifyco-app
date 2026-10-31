import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "react-router";
import { config } from "../config";
import { apiFetch } from "../lib/api";
import { ThemeToggle } from "../theme/ThemeToggle";

type Health = { status: string; environment: string };

export function AppLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface-raised">
        <div className="mx-auto flex max-w-content items-center justify-between gap-4 px-4 py-3 sm:px-5">
          {/* TODO: logo. Replace with the supplied wordmark SVG from /web/src/assets/brand/ (design.md
              section 6). Never retype the wordmark in Poppins. */}
          <Link to="/" className="text-ui text-ink no-underline">
            Pacify
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
