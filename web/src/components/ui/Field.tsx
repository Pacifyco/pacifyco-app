import { ChevronDown, CircleAlert } from "lucide-react";
import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cx } from "./cx";

// design.md section 10: pill inputs (textarea radius-md) on a white surface with a strong border,
// label above, and an error below with an icon and a blame-free message.

type FieldProps = {
  label: string;
  /** Short help shown under the label. */
  hint?: string;
  /** Blame-free message, e.g. "That email doesn't look quite right — could you check it?" */
  error?: string;
  optional?: boolean;
};

const control =
  "w-full border bg-surface-raised text-body text-ink transition-colors duration-200 ease-calm " +
  "placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-60";

function borderFor(error?: string) {
  return error ? "border-2 border-danger" : "border-strong";
}

function FieldShell({
  id,
  label,
  hint,
  error,
  optional,
  children,
}: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-ui text-ink">
        {label}
        {optional && <span className="font-normal text-muted"> (optional)</span>}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="-mt-1 text-small text-muted">
          {hint}
        </p>
      )}
      {children}
      {error && (
        <p id={`${id}-error`} className="flex items-start gap-2 text-small text-danger">
          <CircleAlert aria-hidden="true" size={20} strokeWidth={1.75} className="mt-px shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

function useFieldIds(id: string | undefined, hint?: string, error?: string) {
  const generated = useId();
  const fieldId = id ?? generated;
  const describedBy = [hint && `${fieldId}-hint`, error && `${fieldId}-error`].filter(Boolean).join(" ") || undefined;
  return { fieldId, describedBy };
}

export function TextInput({
  label,
  hint,
  error,
  optional,
  id,
  className,
  ...props
}: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const { fieldId, describedBy } = useFieldIds(id, hint, error);
  return (
    <FieldShell id={fieldId} label={label} hint={hint} error={error} optional={optional}>
      <input
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        required={!optional || undefined}
        className={cx(control, "rounded-pill px-5 py-3", borderFor(error), className)}
        {...props}
      />
    </FieldShell>
  );
}

export function Textarea({
  label,
  hint,
  error,
  optional,
  id,
  className,
  rows = 4,
  ...props
}: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { fieldId, describedBy } = useFieldIds(id, hint, error);
  return (
    <FieldShell id={fieldId} label={label} hint={hint} error={error} optional={optional}>
      <textarea
        id={fieldId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        required={!optional || undefined}
        className={cx(control, "rounded-md px-5 py-3", borderFor(error), className)}
        {...props}
      />
    </FieldShell>
  );
}

export function Select({
  label,
  hint,
  error,
  optional,
  id,
  className,
  children,
  ...props
}: FieldProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const { fieldId, describedBy } = useFieldIds(id, hint, error);
  return (
    <FieldShell id={fieldId} label={label} hint={hint} error={error} optional={optional}>
      <div className="relative">
        <select
          id={fieldId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          required={!optional || undefined}
          className={cx(control, "appearance-none rounded-pill py-3 pr-7 pl-5", borderFor(error), className)}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden="true"
          size={20}
          strokeWidth={1.75}
          className="pointer-events-none absolute top-1/2 right-5 -translate-y-1/2 text-ink"
        />
      </div>
    </FieldShell>
  );
}

/** An unticked-by-default checkbox with its label beside it (design.md 10; radius-sm). */
export function Checkbox({
  label,
  error,
  id,
  className,
  ...props
}: { label: ReactNode; error?: string } & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const generated = useId();
  const boxId = id ?? generated;
  return (
    <div className={cx("flex flex-col gap-2", className)}>
      <label htmlFor={boxId} className="flex cursor-pointer items-start gap-3 text-body text-ink">
        <input
          id={boxId}
          type="checkbox"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${boxId}-error` : undefined}
          className="mt-1 size-5 shrink-0 cursor-pointer rounded-sm border-strong accent-[var(--accent-coral)]"
          {...props}
        />
        <span>{label}</span>
      </label>
      {error && (
        <p id={`${boxId}-error`} className="flex items-start gap-2 text-small text-danger">
          <CircleAlert aria-hidden="true" size={20} strokeWidth={1.75} className="mt-px shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
