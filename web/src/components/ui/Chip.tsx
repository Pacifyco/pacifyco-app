import { BadgeCheck, Check, X } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "./cx";

// design.md section 10: pill, peach or sunken surface, ink text (e.g. "Ages 1–8", "Storytime").
// "outline" for ages and languages, so they don't look like the trust chips (UX review 2026-11-13).
export function Chip({ children, tone = "peach" }: { children: ReactNode; tone?: "peach" | "sunken" | "outline" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-pill px-3 py-1 text-small text-ink",
        tone === "peach" ? "bg-surface-tint" : tone === "sunken" ? "bg-surface-sunken" : "border border-line",
      )}
    >
      {children}
    </span>
  );
}

/** A chip that switches on and off (filters, picking from a list): fills when on and shows a mark
(UX review 2026-11-13). Use the tick for picking from a list, the cross for filters. */
export function ToggleChip({
  on,
  onToggle,
  children,
  mark = "cross",
}: {
  on: boolean;
  onToggle: () => void;
  children: ReactNode;
  mark?: "cross" | "tick";
}) {
  const Mark = mark === "tick" ? Check : X;
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onToggle}
      className={cx(
        "inline-flex min-h-[44px] items-center gap-1 rounded-pill border px-4 py-2 text-small transition-colors duration-200 ease-calm",
        on ? "border-ink bg-ink text-surface-default" : "border-strong bg-surface-raised text-ink hover:bg-surface-sunken",
      )}
    >
      {children}
      {on && <Mark aria-hidden="true" size={16} strokeWidth={1.75} />}
    </button>
  );
}

// Only the checks Pacify actually does (CLAUDE.md section 7; design.md section 11). The label is fixed
// per check so copy can never claim something we don't do (no address checks, no Pacify Plus).
export const VERIFIED_LABELS = {
  id_police: "ID & police verified",
  references: "References checked",
  // Only show once the real questions from a licensed psychologist are live (progress.md phase 15),
  // not while the test runs on placeholder questions.
  psychology: "Psychology screening passed",
  first_aid: "First-aid certified",
} as const;

export type VerifiedCheck = keyof typeof VERIFIED_LABELS;

export function VerifiedChip({ check }: { check: VerifiedCheck }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-pill border border-trust py-1 pr-3 pl-2 text-small font-medium text-trust">
      <BadgeCheck aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0" />
      {VERIFIED_LABELS[check]}
    </span>
  );
}
