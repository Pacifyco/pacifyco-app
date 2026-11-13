import { createContext, useContext, type ReactNode } from "react";
import { Button } from "./Button";

// Multi-step forms (the sitter application, "My family"): every step shows "← Back" beside its Continue
// button, so people can go back to the step before if they've made a mistake. The page provides what Back
// does (the step before, or "Your profile" from the first step).
export const StepBackContext = createContext<(() => void) | null>(null);

/** "Step 2 of 3 · Emergency contacts" with a thin progress bar (UX review 2026-11-13). */
export function StepProgress({ step, of, label }: { step: number; of: number; label: string }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-center text-small text-muted">
        Step {step} of {of} · <span className="text-ink">{label}</span>
      </p>
      <div
        role="progressbar"
        aria-label="Progress"
        aria-valuemin={1}
        aria-valuemax={of}
        aria-valuenow={step}
        className="h-1.5 overflow-hidden rounded-pill bg-surface-sunken"
      >
        <div className="h-full rounded-pill bg-coral transition-[width] duration-200 ease-calm" style={{ width: `${(step / of) * 100}%` }} />
      </div>
    </div>
  );
}

export function StepActions({ children }: { children: ReactNode }) {
  const onBack = useContext(StepBackContext);
  return (
    <div className="flex flex-wrap items-center gap-3">
      {onBack && (
        <Button type="button" variant="secondary" fullWidthOnPhone={false} onClick={onBack}>
          ← Back
        </Button>
      )}
      {children}
    </div>
  );
}
