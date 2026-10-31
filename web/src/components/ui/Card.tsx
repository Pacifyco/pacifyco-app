import type { HTMLAttributes } from "react";
import { cx } from "./cx";

// design.md section 10: white, radius-lg, shadow-soft, space-5 (compact) or space-6 (roomy) padding.
type CardProps = HTMLAttributes<HTMLElement> & {
  padding?: "compact" | "roomy";
  as?: "div" | "section" | "article" | "li";
};

export function Card({ padding = "compact", as: Tag = "div", className, ...props }: CardProps) {
  return (
    <Tag
      className={cx(
        "rounded-lg bg-surface-raised shadow-soft",
        padding === "compact" ? "p-5" : "p-6",
        className,
      )}
      {...props}
    />
  );
}
