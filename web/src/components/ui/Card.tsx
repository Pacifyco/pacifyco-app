import type { HTMLAttributes } from "react";
import { cx } from "./cx";

// design.md section 10: white, radius-lg, shadow-soft, space-5 (compact) or space-6 (roomy) padding.
type CardProps = HTMLAttributes<HTMLElement> & {
  /** "tight": less on phones, so cards inside keep their width (UX review 2026-11-13). */
  padding?: "compact" | "roomy" | "tight";
  as?: "div" | "section" | "article" | "li";
};

export function Card({ padding = "compact", as: Tag = "div", className, ...props }: CardProps) {
  return (
    <Tag
      className={cx(
        "rounded-lg bg-surface-raised shadow-soft",
        padding === "compact" ? "p-5" : padding === "tight" ? "p-4 sm:p-6" : "p-6",
        className,
      )}
      {...props}
    />
  );
}
