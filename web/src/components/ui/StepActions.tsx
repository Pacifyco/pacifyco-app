import { createContext, useContext, type ReactNode } from "react";
import { Button } from "./Button";

// Multi-step forms (the sitter application, "My family"): every step shows "← Back" beside its Continue
// button, so people can go back to the step before if they've made a mistake. The page provides what Back
// does (the step before, or "Your profile" from the first step).
export const StepBackContext = createContext<(() => void) | null>(null);

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
