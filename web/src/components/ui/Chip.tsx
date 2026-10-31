import { BadgeCheck } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "./cx";

// design.md section 10: pill, peach or sunken surface, ink text (e.g. "Ages 1–8", "Storytime").
export function Chip({ children, tone = "peach" }: { children: ReactNode; tone?: "peach" | "sunken" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-pill px-3 py-1 text-small text-ink",
        tone === "peach" ? "bg-surface-tint" : "bg-surface-sunken",
      )}
    >
      {children}
    </span>
  );
}

// Only the checks Pacify actually does (CLAUDE.md section 7; design.md section 11). The label is fixed
// per check so copy can never claim something we don't do (no address checks, no Pacify Plus).
export const VERIFIED_LABELS = {
  id_police: "ID & police verified",
  references: "References checked",
  interview: "Interviewed by Pacify",
  first_aid: "First-aid certified",
} as const;

export type VerifiedCheck = keyof typeof VERIFIED_LABELS;

export function VerifiedChip({ check }: { check: VerifiedCheck }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-pill bg-surface-sunken py-1 pr-3 pl-2 text-small text-trust">
      <BadgeCheck aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0" />
      {VERIFIED_LABELS[check]}
    </span>
  );
}
