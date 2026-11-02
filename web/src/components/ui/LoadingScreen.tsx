import type { ReactNode } from "react";

// A calm interstitial for auth transitions (sign-in, joining, moving to your area) so people never
// see a flash of the wrong page. design.md section 9 rules out spin and bounce, so three dots
// breathe in sequence instead; `prefers-reduced-motion` turns that into a steady state (index.css).
export function LoadingScreen({ message = "Loading your account…" }: { message?: ReactNode }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-[40vh] flex-col items-center justify-center gap-5 rounded-lg bg-surface-sunken p-7 text-center"
    >
      <span className="flex gap-2" aria-hidden="true">
        <span className="loading-dot size-3 rounded-pill bg-coral" style={{ animationDelay: "0ms" }} />
        <span className="loading-dot size-3 rounded-pill bg-coral" style={{ animationDelay: "160ms" }} />
        <span className="loading-dot size-3 rounded-pill bg-coral" style={{ animationDelay: "320ms" }} />
      </span>
      <p className="text-muted">{message}</p>
    </div>
  );
}
