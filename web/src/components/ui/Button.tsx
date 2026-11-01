import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";
import { cx } from "./cx";

// design.md section 10: every button is a pill. Primary = coral fill with a chocolate label (never white).
// The arrow is only for the single primary forward action on a screen.

export type ButtonVariant = "primary" | "secondary" | "tertiary";

type StyleProps = {
  variant?: ButtonVariant;
  /** Adds "→". Only for the one primary forward action on a screen. */
  arrow?: boolean;
  /** Primary buttons are full width on phones by default; set false for inline primaries. */
  fullWidthOnPhone?: boolean;
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-pill text-ui no-underline transition duration-200 ease-calm " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-coral px-5 py-3 text-on-coral hover:shadow-soft",
  secondary: "border border-strong px-5 py-3 text-ink hover:bg-surface-sunken",
  tertiary: "px-1 py-1 text-coral-deep underline-offset-4 hover:underline",
};

export function buttonClasses({ variant = "primary", fullWidthOnPhone = variant === "primary" }: StyleProps): string {
  return cx(base, variants[variant], fullWidthOnPhone && "w-full sm:w-auto");
}

function Label({ children, arrow, variant }: { children: ReactNode; arrow?: boolean; variant: ButtonVariant }) {
  return (
    <>
      {children}
      {arrow && variant === "primary" && <span aria-hidden="true">→</span>}
    </>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  StyleProps & {
    /** Shows the button as busy and blocks clicks while an action runs. */
    loading?: boolean;
  };

export function Button({
  variant = "primary",
  arrow,
  fullWidthOnPhone,
  loading = false,
  disabled,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(buttonClasses({ variant, fullWidthOnPhone }), className)}
      {...props}
    >
      <Label arrow={arrow} variant={variant}>
        {children}
      </Label>
    </button>
  );
}

/** A link that looks like a button (for navigation, e.g. "Meet Priya first"). */
export function ButtonLink({
  variant = "primary",
  arrow,
  fullWidthOnPhone,
  className,
  children,
  ...props
}: LinkProps & StyleProps) {
  return (
    <Link className={cx(buttonClasses({ variant, fullWidthOnPhone }), className)} {...props}>
      <Label arrow={arrow} variant={variant}>
        {children}
      </Label>
    </Link>
  );
}
