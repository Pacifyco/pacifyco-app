import type { ReactNode } from "react";
import { ButtonLink, Card } from "../components/ui";
import {
  SITTER_ORDER,
  SITTER_STEPS,
  firstToDo,
  isLocked,
  stepHref,
  useChecklist,
  type SitterChecklist,
} from "./ProfileChecklist";

// The sitter's eight onboarding steps (Reuben, 2026-11-13): every step page shows where she is and how
// much is done, and a step can't be opened until the ones before it are filled in.

const FINISHED = new Set(["done", "waiting", "approved"]);

/** "Step 3 of 8 · About you" with a bar for how many of the eight are done. */
export function SitterProgress({ step }: { step: string }) {
  const checklist = useChecklist<SitterChecklist>("sitter");
  const items = checklist.data?.items ?? [];
  const done = items.filter((item) => FINISHED.has(item.status)).length;
  const total = SITTER_ORDER.length;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-center text-small text-muted">
        Step {SITTER_ORDER.indexOf(step) + 1} of {total} ·{" "}
        <span className="text-ink">{SITTER_STEPS[step]?.label}</span>
      </p>
      <div
        role="progressbar"
        aria-label="Steps done"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-valuetext={`${done} of ${total} steps done`}
        className="h-1.5 overflow-hidden rounded-pill bg-surface-sunken"
      >
        <div
          className="h-full rounded-pill bg-coral transition-[width] duration-200 ease-calm"
          style={{ width: `${(done / total) * 100}%` }}
        />
      </div>
      <p className="text-center text-caption text-muted">
        {done} of {total} steps done
      </p>
    </div>
  );
}

/** Shows the step only once every step before it is filled in; otherwise, the way to the one to do. */
export function SitterGate({ step, children }: { step: string; children: ReactNode }) {
  const checklist = useChecklist<SitterChecklist>("sitter");
  if (checklist.isPending) return <p className="text-center text-muted">Loading…</p>;
  // If the checklist can't load, the API still checks everything that matters; don't block her.
  if (!checklist.isSuccess || !isLocked(checklist.data.items, step)) return <>{children}</>;
  const open = firstToDo(checklist.data.items)!;
  const label = SITTER_STEPS[open]!.label;
  return (
    <Card as="section" className="flex flex-col items-start gap-3">
      <h2 className="text-h3">Finish "{label}" first</h2>
      <p className="text-small text-muted">Each step opens once the one before it is done.</p>
      <ButtonLink to={stepHref(SITTER_STEPS, open)} arrow>
        Go to {label}
      </ButtonLink>
    </Card>
  );
}
